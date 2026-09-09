"""Background engine that brings SITL to a requested vehicle configuration.

Reconfiguring a simulated vehicle means installing firmware, persisting the SITL frame,
writing parameters and restarting the autopilot twice — minutes of work that no HTTP
request should hold open. The work therefore runs as a single background job whose
progress the frontend polls to drive its dialog.

Only one job runs at a time: there is one autopilot, and two concurrent reconfigurations
would fight over it.
"""

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, NamedTuple, Optional, Set, Tuple

from loguru import logger

from sitl_manager import autopilot, mavlink
from sitl_manager.models import (
    ApplyJob,
    ApplyStep,
    JobState,
    ParamOutcome,
    ParamRecord,
    StepState,
    Vehicle,
    VehiclePreset,
)
from sitl_manager.presets import (
    DEFAULT_SPAWN_BY_FIELD,
    FRAME_MINIMUM_FIRMWARE,
    FRAME_OUTPUTS,
    LOCATION_PARAM_MAP,
    SITL_ACCEL_CALIBRATION,
    unclaimed_assignments,
)
from sitl_manager.settings import REBUILD_READY_TIMEOUT, VEHICLE_READY_TIMEOUT

STEP_VEHICLE = "vehicle"
STEP_FRAME = "frame"
STEP_BOOT = "boot"
STEP_PARAMETERS = "parameters"
STEP_REBUILD = "rebuild"
STEP_VERIFY = "verify"

# What the progress dialog labels each step on its step bar.
STEP_TITLES = {
    STEP_VEHICLE: "Vehicle type",
    STEP_FRAME: "SITL frame",
    STEP_BOOT: "Autopilot restart",
    STEP_PARAMETERS: "Parameters",
    STEP_REBUILD: "Frame rebuild",
    STEP_VERIFY: "Verification",
}

# How many times a parameter is written before it is called a failure. A second write only
# happens when the first one demonstrably did not take, so this costs nothing on a good link.
PARAM_ATTEMPTS = 2

# Long enough for the autopilot being replaced to fall silent before its successor is looked for.
RESTART_SETTLE = 2.0

# Reading a parameter here holds up a vehicle change that is about to take minutes, so each one
# gets a short wait — asked again a few times, since an answer lost to another client's read is
# not a parameter without a value — before it is treated as unreadable. An autopilot that
# answers for none of the four spawn parameters spends eighteen seconds of that change here.
PARAM_READ_TIMEOUT = 1.5
PARAM_READ_ATTEMPTS = 3


class _Request(NamedTuple):
    """What was asked for, kept so a failed job can be run again from the same inputs."""

    title: str
    vehicle: Optional[Vehicle]
    frame: Optional[str]
    params: Dict[str, float]
    # A preset describes a whole vehicle, so a binding it leaves out is one the vehicle should
    # not have. A vehicle or frame chosen by hand says nothing about wiring and leaves it be.
    from_preset: bool = False


@dataclass
class _Progress:
    """What the earlier stages worked out, for the later ones that depend on it.

    ``forced`` names the step a retry asked to run again. Steps that would otherwise decide
    they have nothing to do — the two restarts, which normally only run when something
    upstream changed — run anyway when named here, because the user is asking for that step
    rather than for the conditions that usually trigger it.
    """

    installed: bool = False
    frame_changed: bool = False
    written: int = 0
    forced: Optional[str] = None

    def wanted(self, key: str, condition: bool) -> bool:
        return condition or self.forced == key


_StageFn = Callable[[ApplyJob, _Request, _Progress], Awaitable[None]]


_job: Optional[ApplyJob] = None
_request: Optional[_Request] = None
# What a firmware install takes away and the parameter step has to put back: the spawn location
# read off the outgoing firmware, and the placeholder accelerometer calibration that empty
# parameter storage lacks. Belongs to the job rather than to a single run of it, so a retry that
# resumes at the parameters step still writes it back.
_carried: Dict[str, float] = {}
_task: Optional["asyncio.Task[None]"] = None
_tasks: Set["asyncio.Task[None]"] = set()
_next_id = 1


class JobBusyError(RuntimeError):
    """Raised when a configuration change is requested while another is still running."""


class NoJobError(RuntimeError):
    """Raised when a retry is requested before anything has been applied."""


def current_job() -> Optional[ApplyJob]:
    return _job


def is_running() -> bool:
    return _job is not None and _job.state is JobState.RUNNING


def _spawn(work: Awaitable[None]) -> None:
    global _task  # noqa: PLW0603 - one autopilot, one job
    _task = asyncio.ensure_future(work)
    _tasks.add(_task)
    _task.add_done_callback(_tasks.discard)


def _step(job: ApplyJob, key: str) -> ApplyStep:
    return next(step for step in job.steps if step.key == key)


def _begin(job: ApplyJob, key: str, detail: str = "") -> None:
    step = _step(job, key)
    step.state = StepState.RUNNING
    step.detail = detail


def _finish(job: ApplyJob, key: str, detail: str = "", state: StepState = StepState.DONE) -> None:
    step = _step(job, key)
    step.state = state
    step.detail = detail


def _record(job: ApplyJob, name: str, value: float, outcome: ParamOutcome) -> None:
    job.records.append(ParamRecord(name=name, value=value, outcome=outcome))
    job.counts[outcome.value] = job.counts.get(outcome.value, 0) + 1
    job.params_done = len(job.records)


async def _read_spawn() -> Dict[str, float]:
    """Where the vehicle currently spawns, as parameters ready to be written back.

    Zero is not a place anyone chose: it is what SIM_OPOS_* read as before they have been
    set, and the position Cockpit draws for a vehicle that never had a fix. A vehicle sitting
    on it — or a parameter that would not answer — gets the BlueOS default instead, so no
    path through this leaves the simulator adrift off West Africa.
    """
    spawn: Dict[str, float] = {}
    for field_name, param in LOCATION_PARAM_MAP.items():
        value = await mavlink.get_param(param, timeout=PARAM_READ_TIMEOUT, attempts=PARAM_READ_ATTEMPTS)
        spawn[param] = DEFAULT_SPAWN_BY_FIELD[field_name] if value is None else value

    latitude, longitude = LOCATION_PARAM_MAP["latitude"], LOCATION_PARAM_MAP["longitude"]
    if not spawn[latitude] and not spawn[longitude]:
        logger.info("Spawn location reads as 0, 0; carrying the BlueOS default across instead")
        return {param: DEFAULT_SPAWN_BY_FIELD[name] for name, param in LOCATION_PARAM_MAP.items()}
    return spawn


async def _new_enough(minimum: Optional[str]) -> bool:
    """Whether the running firmware carries a fix that the frame about to run needs.

    An unreadable version counts as too old: reinstalling costs a download, while keeping a
    build whose simulation model cannot steer costs a vehicle that does not navigate.
    """
    if minimum is None:
        return True
    running = await mavlink.get_autopilot_version()
    if autopilot.is_at_least(running, minimum):
        return True
    logger.info(f"The vehicle runs {running}, older than the {minimum} this frame needs")
    return False


async def _apply_vehicle(job: ApplyJob, vehicle: Vehicle, frame: Optional[str]) -> bool:
    """Install the firmware for a vehicle type. Returns whether anything was installed.

    Looking up the build is reported apart from fetching it because the lookup goes out to
    ArduPilot's firmware index and can take the best part of a minute on its own, which is
    otherwise a long silence on a step that claims to be downloading.
    """
    _begin(job, STEP_VEHICLE, f"Checking the installed {vehicle.value} firmware")
    # A request only names the frame when it is changing, so what decides which build is needed
    # is the frame the vehicle ends up on: one whose model was broken until a known release
    # needs the build that fixes it even when the frame itself is staying where it is.
    minimum = FRAME_MINIMUM_FIRMWARE.get(frame or await autopilot.get_sitl_frame() or "")
    current = await autopilot.get_firmware_vehicle_type()
    if current and vehicle.value.lower() in str(current).lower() and await _new_enough(minimum):
        _finish(job, STEP_VEHICLE, f"Already running {current}", state=StepState.SKIPPED)
        return False
    # Read before installing: the new firmware gets its own parameter storage, so the spawn
    # location the user picked is about to revert to SIM_OPOS's zeroes, and the accelerometer
    # calibration that lets a simulated vehicle arm at all is about to be gone with it. Both
    # are written back with the preset's own parameters below, where the rebuild restart is
    # what brings the vehicle up in the right place.
    global _carried  # noqa: PLW0603 - one autopilot, one job
    _carried = {**SITL_ACCEL_CALIBRATION, **await _read_spawn()}
    _begin(job, STEP_VEHICLE, f"Looking up the {vehicle.value} build to install")
    firmware = await autopilot.firmware_to_install(vehicle, minimum)
    name = str(firmware["name"])
    logger.info(f"Installing {name} for {vehicle.value}")
    _begin(job, STEP_VEHICLE, f"Downloading and installing {name}")
    await autopilot.install_firmware_from_url(firmware["url"], make_default=True)
    _finish(job, STEP_VEHICLE, f"Installed {name}")
    return True


async def _apply_frame(job: ApplyJob, frame: str) -> bool:
    """Persist the SITL frame. Returns whether it changed."""
    _begin(job, STEP_FRAME, f"Setting the SITL frame to {frame}")
    if await autopilot.get_sitl_frame() == frame:
        _finish(job, STEP_FRAME, f"Already set to {frame}", state=StepState.SKIPPED)
        return False
    await autopilot.set_sitl_frame(frame)
    _finish(job, STEP_FRAME, f"Frame set to {frame}")
    return True


async def _boot(job: ApplyJob, key: str, restart: bool, detail: str, timeout: float = VEHICLE_READY_TIMEOUT) -> None:
    """Wait for the autopilot to serve parameters again, restarting it first if asked.

    A firmware install restarts the autopilot itself, so callers skip the restart in that
    case and only wait for it to come back. How long a restart takes is unknowable, so the
    step reports the seconds spent and what it is still missing instead of a fraction, giving
    the dialog something that visibly moves while it waits.
    """
    _begin(job, key, detail)
    if restart:
        await autopilot.restart()
        # Readiness is judged from the heartbeat resuming, and the outgoing autopilot can get
        # one more out after the restart call returns. Waiting it out means the heartbeat that
        # ends this step belongs to the process we are about to write parameters to.
        await asyncio.sleep(RESTART_SETTLE)
    ready = await mavlink.wait_until_ready(
        timeout=timeout,
        on_wait=lambda waited, missing: _begin(job, key, f"{detail} — {missing} ({waited:.0f}s of {timeout:.0f}s)"),
    )
    if not ready:
        raise TimeoutError("The autopilot did not come back online in time.")
    _finish(job, key, "Autopilot online")


def _changed(counts: Dict[str, int]) -> int:
    """How many parameters the vehicle did not already hold and was therefore written.

    What the rebuild restart exists for, so a write whose read-back went missing counts here:
    the value it carried is not the one the vehicle had, and a restart that hinged on an answer
    another client can carry off would skip the rebuild the new values need.
    """
    return counts.get(ParamOutcome.WRITTEN.value, 0) + counts.get(ParamOutcome.UNCONFIRMED.value, 0)


async def _apply_params(job: ApplyJob, params: Dict[str, float], clear_unclaimed: bool = False) -> int:
    """Write the parameters that differ from what the vehicle already holds.

    One parameter dump up front tells us which values are already correct, which is far
    quicker than reading them back one at a time and makes re-applying a preset almost
    instant. A dump can drop packets, so a name it does not mention is read on its own rather
    than assumed missing — only a parameter that answers neither the dump, nor that read, nor
    the write that follows is reported as unsupported by this firmware.
    """
    # Cleared rather than appended to, so retrying this step reports one pass, not two.
    job.records.clear()
    job.counts.clear()
    job.params_done = 0
    _begin(job, STEP_PARAMETERS, "Reading current parameters")
    onboard = await mavlink.dump_all_params()
    if not onboard:
        logger.warning("Parameter dump came back empty; every parameter will be written and verified")

    if clear_unclaimed:
        stale = unclaimed_assignments(params, onboard)
        if stale:
            logger.info(f"Clearing bindings the preset does not claim: {', '.join(sorted(stale))}")
            params = {**params, **stale}
    job.params_total = len(params)

    for name, value in params.items():
        target = float(value)
        job.current_param = name
        _begin(job, STEP_PARAMETERS, f"Sending parameter {job.params_done + 1}/{job.params_total}: {name}")

        current = onboard.get(name)
        if current is None:
            # A name the dump dropped is one nothing is known about yet, so it is asked for
            # before being written: a value that already matches then costs neither a write nor
            # the restart that a write would earn, and silence here is the first sign of a
            # firmware that does not have the parameter at all.
            current = await mavlink.get_param(name, timeout=PARAM_READ_TIMEOUT, attempts=PARAM_READ_ATTEMPTS)
        if current is not None and mavlink.values_match(current, target):
            _record(job, name, target, ParamOutcome.UNCHANGED)
            continue

        readback = await mavlink.set_param_verified(name, target, attempts=PARAM_ATTEMPTS)
        if readback is None:
            # Only the write's own echo can settle that read, and a vehicle with nothing to
            # change may send none, so silence alone does not mean the name is missing. What
            # does is silence from a name that answered neither the dump nor a read of its own.
            missing = current is None
            _record(job, name, target, ParamOutcome.UNSUPPORTED if missing else ParamOutcome.UNCONFIRMED)
            continue
        if mavlink.values_match(readback, target):
            _record(job, name, target, ParamOutcome.WRITTEN)
        else:
            logger.warning(f"{name} read back as {readback} after writing {target}")
            _record(job, name, target, ParamOutcome.FAILED)

    job.current_param = None
    summary = ", ".join(f"{count} {outcome}" for outcome, count in sorted(job.counts.items()))
    _finish(job, STEP_PARAMETERS, summary or "No parameters to send")
    return _changed(job.counts)


def _expected_vehicle_type(vehicle: Optional[Vehicle], params: Dict[str, float]) -> Optional[str]:
    """What the autopilot should report over MAVLink once the frame parameters are live.

    ArduRover derives this from FRAME_CLASS, which is what separates a BlueBoat from a
    ground rover. Copters vary with their airframe, so they are not pinned down here.
    """
    if vehicle is Vehicle.SUB:
        return "Submarine"
    if vehicle is Vehicle.PLANE:
        return "Fixed Wing"
    if vehicle is Vehicle.ROVER:
        return "Surface Boat" if params.get("FRAME_CLASS") == 2 else "Ground Rover"
    return None


async def _output_mismatch(frame: Optional[str]) -> Optional[str]:
    """What is wrong between a frame and the outputs it drives, or None when they agree.

    Nothing enforces this pairing: the frame decides what the simulator makes of outputs 1 and
    3, the SERVO*_FUNCTION parameters decide what the autopilot puts on them, and a
    configuration that gets them the wrong way round drives in circles while every step of the
    job reports success. A frame chosen by hand is exactly how that happens, since it changes
    the physics without touching the parameters.
    """
    wanted = FRAME_OUTPUTS.get(frame or "")
    if wanted is None:
        return None
    try:
        actual = {
            name: await mavlink.get_param(name, timeout=PARAM_READ_TIMEOUT, attempts=PARAM_READ_ATTEMPTS)
            for name in wanted
        }
    except Exception as error:  # noqa: BLE001 - an advisory read must not fail the job
        logger.debug(f"Could not read the output functions: {error}")
        return None
    wrong = ", ".join(
        f"{name} is {round(value)} rather than {wanted[name]}"
        for name, value in actual.items()
        if value is not None and round(value) != wanted[name]
    )
    if not wrong:
        return None
    return f"{frame} does not match the vehicle's outputs ({wrong}), so it will not steer. A preset sets them."


async def _verify(job: ApplyJob, expected: Optional[str]) -> None:
    """Confirm what the autopilot now reports itself as over MAVLink.

    This is what BlueOS and Cockpit read to identify the vehicle, so it is the real proof
    that the frame parameters took effect: a BlueBoat has to come back as a Surface Boat.
    """
    _begin(job, STEP_VERIFY, "Reading the reported vehicle type")
    reported = await autopilot.get_vehicle_type()
    job.reported_vehicle = reported
    if not reported:
        _finish(job, STEP_VERIFY, "The autopilot did not report a vehicle type", state=StepState.FAILED)
        return
    if expected and reported.lower() != expected.lower():
        _finish(job, STEP_VERIFY, f"Reported as {reported}, expected {expected}", state=StepState.FAILED)
        return
    _finish(job, STEP_VERIFY, f"Reported as {reported}")


async def _stage_vehicle(job: ApplyJob, request: "_Request", progress: "_Progress") -> None:
    if request.vehicle is None:
        _finish(job, STEP_VEHICLE, "Unchanged", state=StepState.SKIPPED)
        return
    progress.installed = await _apply_vehicle(job, request.vehicle, request.frame)


async def _stage_frame(job: ApplyJob, request: "_Request", progress: "_Progress") -> None:
    if request.frame is None:
        _finish(job, STEP_FRAME, "Unchanged", state=StepState.SKIPPED)
        return
    progress.frame_changed = await _apply_frame(job, request.frame)


async def _stage_boot(job: ApplyJob, request: "_Request", progress: "_Progress") -> None:
    if not progress.wanted(STEP_BOOT, progress.installed or progress.frame_changed):
        _finish(job, STEP_BOOT, "No restart needed", state=StepState.SKIPPED)
        return
    # A firmware install restarts the autopilot on its own, but it does so before the step
    # above persisted the frame, and ArduPilot Manager only reads the frame while starting
    # SITL. A frame that changed therefore needs a restart of its own even then, or the
    # simulator keeps running the model the user just replaced.
    restart = progress.frame_changed or not progress.installed
    await _boot(job, STEP_BOOT, restart=restart, detail="Waiting for the autopilot to come back")


async def _stage_parameters(job: ApplyJob, request: "_Request", progress: "_Progress") -> None:
    # What the install took away rides along with the preset's parameters: each is a parameter
    # like any other, and sending them here means the rebuild restart is what applies them,
    # rather than a third reboot. Already-correct values cost nothing, since the write only
    # happens where the vehicle disagrees.
    params = {**request.params, **_carried}
    if not params:
        _finish(job, STEP_PARAMETERS, "No parameters to send", state=StepState.SKIPPED)
        return
    progress.written = await _apply_params(job, params, clear_unclaimed=request.from_preset)


async def _stage_rebuild(job: ApplyJob, request: "_Request", progress: "_Progress") -> None:
    if not progress.wanted(STEP_REBUILD, bool(progress.written)):
        _finish(job, STEP_REBUILD, "Nothing changed, no rebuild needed", state=StepState.SKIPPED)
        return
    # FRAME_CLASS/FRAME_CONFIG only rebuild the motor matrix on the next boot.
    await _boot(
        job,
        STEP_REBUILD,
        restart=True,
        detail="Restarting to rebuild the motor matrix",
        timeout=REBUILD_READY_TIMEOUT,
    )


async def _stage_verify(job: ApplyJob, request: "_Request", progress: "_Progress") -> None:
    # Cleared rather than appended to, so retrying this step reports one pass, not two.
    job.warnings.clear()
    await _verify(job, _expected_vehicle_type(request.vehicle, request.params))
    mismatch = await _output_mismatch(await autopilot.get_sitl_frame())
    if mismatch is not None:
        logger.warning(mismatch)
        job.warnings.append(mismatch)


# In dependency order: firmware, then the frame it runs, then the reboot that loads both,
# then the parameters, then the reboot that rebuilds the motor matrix from them, then the
# check that the autopilot now calls itself what the preset says it is. A job runs this
# from the top; a retry or a skip runs it from one step in.
_STAGES: Tuple[Tuple[str, "_StageFn"], ...] = (
    (STEP_VEHICLE, _stage_vehicle),
    (STEP_FRAME, _stage_frame),
    (STEP_BOOT, _stage_boot),
    (STEP_PARAMETERS, _stage_parameters),
    (STEP_REBUILD, _stage_rebuild),
    (STEP_VERIFY, _stage_verify),
)


def _settle(job: ApplyJob) -> None:
    """Decide the job's outcome from the state its steps ended in.

    Parameters the autopilot rejected fail the parameter step itself, so that a failed job
    always has exactly one step for a retry or a skip to act on.
    """
    rejected = job.counts.get(ParamOutcome.FAILED.value, 0)
    parameters = _step(job, STEP_PARAMETERS)
    if rejected and parameters.state is StepState.DONE:
        parameters.state = StepState.FAILED
        parameters.detail = f"{rejected} parameter(s) rejected by the autopilot"

    failed = next((step for step in job.steps if step.state is StepState.FAILED), None)
    if failed is not None:
        job.state = JobState.FAILED
        job.detail = f"{job.title}: {failed.detail}."
        return

    job.state = JobState.SUCCEEDED
    job.detail = f"{job.title} applied."
    if job.skipped:
        job.detail = f"{job.title} applied, skipped: {', '.join(job.skipped)}."
    if job.warnings:
        job.detail = " ".join([job.detail, *job.warnings])


async def _run(job: ApplyJob, request: "_Request", progress: "_Progress", start: int = 0) -> None:
    """Walk the pipeline from ``start``, stopping at the first step that fails.

    The step that raised is the one marked failed, rather than whichever step happened to be
    running, so a failed job always offers retry and skip a single unambiguous target.
    """
    for key, stage in _STAGES[start:]:
        try:
            await stage(job, request, progress)
        except Exception as error:  # noqa: BLE001 - surfaced to the UI through the job
            logger.error(f"{job.title} failed on {key}: {error}")
            reason = str(error) or error.__class__.__name__
            _finish(job, key, reason, state=StepState.FAILED)
            job.state = JobState.FAILED
            job.detail = reason
            return
    _settle(job)


def _start(
    title: str,
    vehicle: Optional[Vehicle],
    frame: Optional[str],
    params: Dict[str, float],
    from_preset: bool = False,
) -> ApplyJob:
    global _job, _request, _task, _next_id, _carried  # noqa: PLW0603 - one autopilot, one job

    if is_running():
        raise JobBusyError("Another configuration change is still running.")

    # Belongs to the job about to start, not to the one before it.
    _carried = {}

    job = ApplyJob(
        id=_next_id,
        title=title,
        steps=[ApplyStep(key=key, title=STEP_TITLES[key]) for key, _ in _STAGES],
    )
    # Marked up front so the snapshot handed back to the frontend already shows what this
    # request leaves alone, before the first stage has had a chance to run.
    if vehicle is None:
        _finish(job, STEP_VEHICLE, "Unchanged", state=StepState.SKIPPED)
    if frame is None:
        _finish(job, STEP_FRAME, "Unchanged", state=StepState.SKIPPED)

    _next_id += 1
    _job = job
    _request = _Request(title, vehicle, frame, params, from_preset)
    _spawn(_run(job, _request, _Progress()))
    return job


def _pending() -> Tuple[ApplyJob, int]:
    """The job waiting on a decision, and the index of the step that failed."""
    if is_running():
        raise JobBusyError("Another configuration change is still running.")
    if _job is None or _request is None:
        raise NoJobError("There is no configuration change to resume.")
    for index, (key, _) in enumerate(_STAGES):
        if _step(_job, key).state is StepState.FAILED:
            return _job, index
    raise NoJobError("The last configuration change has no failed step.")


def _resume(job: ApplyJob, start: int) -> ApplyJob:
    """Carry the current job on from ``start``, leaving the steps before it as they are."""
    assert _request is not None  # guaranteed by _pending
    progress = _Progress(
        # A restart triggered by an install in the previous run has already been waited on,
        # so a restart step running now has to issue its own.
        installed=False,
        frame_changed=_step(job, STEP_FRAME).state is StepState.DONE,
        written=_changed(job.counts),
        forced=_STAGES[start][0] if start < len(_STAGES) else None,
    )
    for key, _ in _STAGES[start:]:
        step = _step(job, key)
        step.state = StepState.PENDING
        step.detail = ""
    job.state = JobState.RUNNING
    job.detail = ""
    _spawn(_run(job, _request, progress, start))
    return job


def retry() -> ApplyJob:
    """Run the step that failed again, then carry on with the ones after it.

    The steps that already succeeded are left untouched, so this repeats only the work that
    did not land — the usual case being a restart that took longer than the autopilot was
    given.
    """
    job, index = _pending()
    return _resume(job, index)


def skip() -> ApplyJob:
    """Give up on the step that failed and carry on with the ones after it.

    For when the step is not worth waiting on: a rebuild restart that the simulator is slow
    to answer still leaves the parameters written, so the job can be taken to the end and
    the vehicle checked. The skipped step is named in the job's summary, since skipping the
    rebuild can mean the motor matrix is not live yet.
    """
    job, index = _pending()
    step = _step(job, _STAGES[index][0])
    step.state = StepState.SKIPPED
    step.detail = "Skipped on request"
    job.skipped.append(step.title)
    return _resume(job, index + 1)


def start_preset(preset: VehiclePreset) -> ApplyJob:
    # An imported or older saved preset can carry no frame; leave the running one alone.
    return _start(preset.name, preset.vehicle, preset.frame or None, dict(preset.parameters), from_preset=True)


def start_config(vehicle: Optional[Vehicle], frame: Optional[str]) -> ApplyJob:
    """Bring about a vehicle type, a SITL frame, or the two together.

    One job for both, since a combination chosen by hand usually changes both at once and
    running them separately would mean two firmware installs and two restarts to reach it.
    """
    title = " + ".join(part for part in (vehicle.value if vehicle else None, frame) if part)
    return _start(title, vehicle, frame, {})
