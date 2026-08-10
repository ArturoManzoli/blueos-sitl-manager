"""Background engine that brings SITL to a requested vehicle configuration.

Reconfiguring a simulated vehicle means installing firmware, persisting the SITL frame,
writing parameters and restarting the autopilot twice — minutes of work that no HTTP
request should hold open. The work therefore runs as a single background job whose
progress the frontend polls to drive its dialog.

Only one job runs at a time: there is one autopilot, and two concurrent reconfigurations
would fight over it.
"""

import asyncio
from typing import Dict, Optional, Set

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
from sitl_manager.settings import VEHICLE_READY_TIMEOUT

STEP_VEHICLE = "vehicle"
STEP_FRAME = "frame"
STEP_BOOT = "boot"
STEP_PARAMETERS = "parameters"
STEP_REBUILD = "rebuild"
STEP_VERIFY = "verify"

# A parameter write is echoed back by the autopilot, so the read-back that confirms it
# normally lands on the first poll. This only has to cover a busy simulator.
VERIFY_TIMEOUT = 0.6
VERIFY_POLL = 0.05
SEND_DELAY = 0.02

_job: Optional[ApplyJob] = None
_task: Optional["asyncio.Task[None]"] = None
_tasks: Set["asyncio.Task[None]"] = set()
_next_id = 1


class JobBusyError(RuntimeError):
    """Raised when a configuration change is requested while another is still running."""


def current_job() -> Optional[ApplyJob]:
    return _job


def is_running() -> bool:
    return _job is not None and _job.state is JobState.RUNNING


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


def _matches(readback: float, target: float) -> bool:
    return abs(readback - target) <= max(1e-3, abs(target) * 1e-3)


async def _apply_vehicle(job: ApplyJob, vehicle: Vehicle) -> bool:
    """Install the firmware for a vehicle type. Returns whether anything was installed."""
    _begin(job, STEP_VEHICLE, f"Checking the installed {vehicle.value} firmware")
    current = await autopilot.get_firmware_vehicle_type()
    if current and vehicle.value.lower() in str(current).lower():
        _finish(job, STEP_VEHICLE, f"Already running {current}", state=StepState.SKIPPED)
        return False
    _begin(job, STEP_VEHICLE, f"Downloading and installing {vehicle.value} firmware")
    name = await autopilot.install_stable_firmware(vehicle)
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


async def _boot(job: ApplyJob, key: str, restart: bool, detail: str) -> None:
    """Wait for the autopilot to serve parameters again, restarting it first if asked.

    A firmware install restarts the autopilot itself, so callers skip the restart in that
    case and only wait for it to come back.
    """
    _begin(job, key, detail)
    if restart:
        await autopilot.restart()
    if not await mavlink.wait_until_ready(timeout=VEHICLE_READY_TIMEOUT):
        raise TimeoutError("The autopilot did not come back online in time.")
    _finish(job, key, "Autopilot online")


async def _apply_params(job: ApplyJob, params: Dict[str, float]) -> int:
    """Write the parameters that differ from what the vehicle already holds.

    One parameter dump up front tells us which values are already correct, which is far
    quicker than reading them back one at a time and makes re-applying a preset almost
    instant. A dump can drop packets, so a name it does not mention is still written and
    read back rather than assumed missing — only a parameter that never answers a read is
    reported as unsupported by this firmware.
    """
    job.params_total = len(params)
    _begin(job, STEP_PARAMETERS, "Reading current parameters")
    onboard = await mavlink.dump_all_params()
    if not onboard:
        logger.warning("Parameter dump came back empty; every parameter will be written and verified")

    written = 0
    for name, value in params.items():
        target = float(value)
        job.current_param = name
        _begin(job, STEP_PARAMETERS, f"Sending parameter {job.params_done + 1}/{job.params_total}: {name}")

        current = onboard.get(name)
        if current is not None and _matches(current, target):
            _record(job, name, target, ParamOutcome.UNCHANGED)
            continue

        await mavlink.set_param(name, target)
        await asyncio.sleep(SEND_DELAY)
        readback = await mavlink.get_param(name, timeout=VERIFY_TIMEOUT, poll_interval=VERIFY_POLL)
        if readback is None:
            _record(job, name, target, ParamOutcome.UNSUPPORTED)
            continue
        if _matches(readback, target):
            written += 1
            _record(job, name, target, ParamOutcome.WRITTEN)
        else:
            logger.warning(f"{name} read back as {readback} after writing {target}")
            _record(job, name, target, ParamOutcome.FAILED)

    job.current_param = None
    summary = ", ".join(f"{count} {outcome}" for outcome, count in sorted(job.counts.items()))
    _finish(job, STEP_PARAMETERS, summary or "No parameters to send")
    return written


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


async def _run(
    job: ApplyJob,
    vehicle: Optional[Vehicle],
    frame: Optional[str],
    params: Dict[str, float],
) -> None:
    try:
        installed = await _apply_vehicle(job, vehicle) if vehicle else False
        frame_changed = await _apply_frame(job, frame) if frame else False

        if installed or frame_changed:
            # A firmware install restarts the autopilot on its own.
            await _boot(job, STEP_BOOT, restart=not installed, detail="Waiting for the autopilot to come back")
        else:
            _finish(job, STEP_BOOT, "No restart needed", state=StepState.SKIPPED)

        if params:
            written = await _apply_params(job, params)
        else:
            written = 0
            _finish(job, STEP_PARAMETERS, "No parameters to send", state=StepState.SKIPPED)

        if written:
            # FRAME_CLASS/FRAME_CONFIG only rebuild the motor matrix on the next boot.
            await _boot(job, STEP_REBUILD, restart=True, detail="Restarting to rebuild the motor matrix")
        else:
            _finish(job, STEP_REBUILD, "Nothing changed, no rebuild needed", state=StepState.SKIPPED)

        await _verify(job, _expected_vehicle_type(vehicle, params))

        verify_failed = _step(job, STEP_VERIFY).state is StepState.FAILED
        failed = job.counts.get(ParamOutcome.FAILED.value, 0)
        if verify_failed:
            job.state = JobState.FAILED
            job.detail = f"{job.title}: {_step(job, STEP_VERIFY).detail}."
        elif failed:
            job.state = JobState.FAILED
            job.detail = f"{job.title} applied, {failed} parameter(s) rejected."
        else:
            job.state = JobState.SUCCEEDED
            job.detail = f"{job.title} applied."
    except Exception as error:  # noqa: BLE001 - surfaced to the UI through the job
        logger.error(f"{job.title} failed: {error}")
        for step in job.steps:
            if step.state is StepState.RUNNING:
                step.state = StepState.FAILED
        job.state = JobState.FAILED
        job.detail = str(error) or error.__class__.__name__


def _start(
    title: str,
    vehicle: Optional[Vehicle],
    frame: Optional[str],
    params: Dict[str, float],
) -> ApplyJob:
    global _job, _task, _next_id  # noqa: PLW0603 - one autopilot, one job

    if is_running():
        raise JobBusyError("Another configuration change is still running.")

    job = ApplyJob(
        id=_next_id,
        title=title,
        steps=[
            ApplyStep(key=STEP_VEHICLE, title="Vehicle type"),
            ApplyStep(key=STEP_FRAME, title="SITL frame"),
            ApplyStep(key=STEP_BOOT, title="Autopilot restart"),
            ApplyStep(key=STEP_PARAMETERS, title="Parameters"),
            ApplyStep(key=STEP_REBUILD, title="Frame rebuild"),
            ApplyStep(key=STEP_VERIFY, title="Verification"),
        ],
    )
    if vehicle is None:
        _finish(job, STEP_VEHICLE, "Unchanged", state=StepState.SKIPPED)
    if frame is None:
        _finish(job, STEP_FRAME, "Unchanged", state=StepState.SKIPPED)

    _next_id += 1
    _job = job
    _task = asyncio.create_task(_run(job, vehicle, frame, params))
    _tasks.add(_task)
    _task.add_done_callback(_tasks.discard)
    return job


def start_preset(preset: VehiclePreset) -> ApplyJob:
    # An imported or older saved preset can carry no frame; leave the running one alone.
    return _start(preset.name, preset.vehicle, preset.frame or None, dict(preset.parameters))


def start_vehicle(vehicle: Vehicle) -> ApplyJob:
    return _start(f"{vehicle.value} firmware", vehicle, None, {})


def start_frame(frame: str) -> ApplyJob:
    return _start(f"{frame} frame", None, frame, {})
