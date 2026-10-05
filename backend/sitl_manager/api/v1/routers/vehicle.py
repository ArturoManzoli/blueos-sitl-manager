from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route

from sitl_manager import apply_job, autopilot, custom_presets, mavlink
from sitl_manager.api.common import require_sitl, to_http_exception
from sitl_manager.models import (
    ActivePreset,
    AppliedParams,
    ApplyJob,
    OperationResult,
    RenamePresetRequest,
    SavePresetRequest,
    Vehicle,
    VehicleConfigRequest,
    VehiclePreset,
    VehicleStatus,
)
from sitl_manager.presets import (
    PRESET_EXCLUDED_PREFIXES,
    SITL_RC_ARMING,
    all_vehicle_presets,
)

# The frame-defining parameter that distinguishes the presets of each vehicle family:
# FRAME_CONFIG separates BlueROV2 (1) from BlueROV2 Heavy (2); FRAME_CLASS identifies the
# BlueBoat hull (2 = boat) versus a ground rover (1) and the copter's quad airframe.
# ArduPlane has no FRAME_CLASS, so planes are matched by vehicle type alone. Reading just
# this parameter is enough to tell which preset a vehicle matches.
FRAME_PARAM_BY_VEHICLE = {
    Vehicle.SUB: "FRAME_CONFIG",
    Vehicle.ROVER: "FRAME_CLASS",
    Vehicle.COPTER: "FRAME_CLASS",
}

# How patiently that parameter is read. Short enough that the panel is not left waiting on a
# firmware which does not have it, repeated enough to ride out an autopilot still settling.
FRAME_PARAM_TIMEOUT = 1.5
FRAME_PARAM_ATTEMPTS = 3

# The arming settings are read on every page load and written only where they differ, so the
# read is asked again rather than given a long timeout: an autopilot that answered late would
# otherwise have the page announce a repair the vehicle did not need.
ARMING_PARAM_TIMEOUT = 1.5
ARMING_PARAM_ATTEMPTS = 3

# ArduPilot Manager reports the firmware type as e.g. "ArduSub"; map it to our enum.
FIRMWARE_TYPE_TO_VEHICLE = {
    Vehicle.SUB: "sub",
    Vehicle.ROVER: "rover",
    Vehicle.PLANE: "plane",
    Vehicle.COPTER: "copter",
}


async def _detect_active_preset(vehicle_type: str) -> Optional[str]:
    readings: Dict[str, Optional[float]] = {}
    for preset in all_vehicle_presets():
        if preset.vehicle.value.lower() not in vehicle_type.lower():
            continue
        param = FRAME_PARAM_BY_VEHICLE.get(preset.vehicle)
        if param is None:
            # No frame-defining parameter for this family (e.g. Plane): the vehicle type
            # alone identifies the preset.
            return preset.name
        expected = preset.parameters.get(param)
        if expected is None:
            continue
        if param not in readings:
            readings[param] = await mavlink.get_param(param, timeout=FRAME_PARAM_TIMEOUT, attempts=FRAME_PARAM_ATTEMPTS)
        actual = readings[param]
        if actual is not None and round(actual) == round(expected):
            return preset.name
    return None


def _vehicle_from_firmware(firmware_type: Optional[str]) -> Optional[Vehicle]:
    if not firmware_type:
        return None
    lowered = firmware_type.lower()
    for vehicle, token in FIRMWARE_TYPE_TO_VEHICLE.items():
        if token in lowered:
            return vehicle
    return None


async def _build_current_config_preset(name: str, description: str) -> VehiclePreset:
    """Snapshot the running SITL vehicle (type, frame and every non-SIM_ parameter)."""
    await require_sitl("there is no simulated configuration to capture")
    vehicle = _vehicle_from_firmware(await autopilot.get_firmware_vehicle_type())
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not determine the running vehicle type.",
        )
    parameters = await mavlink.dump_all_params()
    if not parameters:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timed out reading parameters from the autopilot.",
        )
    parameters = {key: value for key, value in parameters.items() if not key.startswith(PRESET_EXCLUDED_PREFIXES)}
    frame = await autopilot.get_sitl_frame() or ""
    return VehiclePreset(name=name, description=description, vehicle=vehicle, frame=frame, parameters=parameters)


vehicle_router = APIRouter(
    prefix="/vehicle",
    tags=["vehicle"],
    route_class=versioned_api_route(1, 0),
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)

# SITL frames most relevant to marine BlueOS development, grouped by the firmware that can
# run them. The full list lives in ArduPilot Manager's SITLFrame enum; these are the ones
# worth surfacing by default. Each frame is a physics model built into one vehicle's binary,
# so the grouping is not a matter of taste: ArduSub has no idea what a plane is.
SITL_FRAMES: Dict[Vehicle, List[str]] = {
    Vehicle.SUB: ["vectored", "vectored_6dof"],
    Vehicle.ROVER: ["motorboat", "motorboat-skid", "sailboat", "rover", "rover-skid"],
    Vehicle.COPTER: ["quad"],
    Vehicle.PLANE: ["plane"],
}


@vehicle_router.get("/status", response_model=VehicleStatus, summary="Current board, frame and vehicle type.")
@to_http_exception
async def status_() -> VehicleStatus:
    board = await autopilot.get_board()
    is_sitl = autopilot.is_sitl(board)
    return VehicleStatus(
        board=board.get("name") if board else None,
        is_sitl=is_sitl,
        frame=await autopilot.get_sitl_frame(),
        firmware_vehicle_type=await autopilot.get_firmware_vehicle_type(),
        firmware_version=await mavlink.get_autopilot_version() if is_sitl else None,
    )


@vehicle_router.get(
    "/frames",
    response_model=Dict[Vehicle, List[str]],
    summary="List the selectable SITL frames of each vehicle type.",
)
@to_http_exception
async def frames() -> Dict[Vehicle, List[str]]:
    return SITL_FRAMES


def _start_job(start: Callable[[], ApplyJob]) -> ApplyJob:
    try:
        return start()
    except apply_job.JobBusyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except apply_job.NoJobError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@vehicle_router.get(
    "/apply-job",
    response_model=Optional[ApplyJob],
    summary="Progress of the running (or last) configuration change.",
)
@to_http_exception
async def apply_job_status() -> Optional[ApplyJob]:
    return apply_job.current_job()


@vehicle_router.post(
    "/apply-job/retry",
    response_model=ApplyJob,
    summary="Run the step that failed again and carry on from there.",
)
@to_http_exception
async def retry_apply_job() -> ApplyJob:
    return _start_job(apply_job.retry)


@vehicle_router.post(
    "/apply-job/skip",
    response_model=ApplyJob,
    summary="Skip the step that failed and carry on with the rest.",
)
@to_http_exception
async def skip_apply_job() -> ApplyJob:
    return _start_job(apply_job.skip)


@vehicle_router.post(
    "/apply",
    response_model=ApplyJob,
    summary="Apply a vehicle type and/or SITL frame chosen by hand, and restart.",
)
@to_http_exception
async def apply_config(request: VehicleConfigRequest) -> ApplyJob:
    """Start bringing SITL to a configuration that matches no preset.

    Both halves travel together because changing them one at a time would install the
    firmware and restart the autopilot twice over to reach the same place.
    """
    await require_sitl("changing the vehicle type or frame would reflash the connected autopilot")
    if request.vehicle is None and request.frame is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name a vehicle type, a frame, or both.",
        )
    return _start_job(lambda: apply_job.start_config(request.vehicle, request.frame))


@vehicle_router.post("/restart", response_model=OperationResult, summary="Restart the autopilot.")
@to_http_exception
async def restart() -> OperationResult:
    await require_sitl("only the simulated autopilot is restarted from here")
    await autopilot.restart()
    return OperationResult(success=True, detail="Autopilot restarted.")


@vehicle_router.post(
    "/arming-checks",
    response_model=AppliedParams,
    summary="Relax the RC arming checks so the vehicle arms with a gamepad connected.",
)
@to_http_exception
async def relax_arming_checks() -> AppliedParams:
    """Bring a running vehicle to the arming settings a preset now writes.

    These take effect where they are written, so a vehicle configured before the presets
    carried them is repaired in place rather than made to sit through another apply, and one
    that already holds them is left alone: an empty ``applied`` is a vehicle that needed
    nothing, which is what keeps this quiet on every page load after the first.
    """
    await require_sitl("the arming checks of a connected autopilot are not ours to relax")
    differing: Dict[str, float] = {}
    for name, value in SITL_RC_ARMING.items():
        current = await mavlink.get_param(name, timeout=ARMING_PARAM_TIMEOUT, attempts=ARMING_PARAM_ATTEMPTS)
        if current is None or not mavlink.values_match(current, value):
            differing[name] = value
    if not differing:
        return AppliedParams()
    applied, unverified = await mavlink.set_params_verified(differing, attempts=ARMING_PARAM_ATTEMPTS)
    return AppliedParams(applied=applied, unverified=unverified)


@vehicle_router.get("/presets", response_model=List[VehiclePreset], summary="List ready-to-fly vehicle presets.")
@to_http_exception
async def list_vehicle_presets() -> List[VehiclePreset]:
    return all_vehicle_presets()


@vehicle_router.get("/active-preset", response_model=ActivePreset, summary="Which preset the running SITL matches.")
@to_http_exception
async def active_preset() -> ActivePreset:
    board = await autopilot.get_board()
    if not autopilot.is_sitl(board):
        return ActivePreset(name=None)
    vehicle_type = await autopilot.get_firmware_vehicle_type()
    if not vehicle_type:
        return ActivePreset(name=None)
    return ActivePreset(name=await _detect_active_preset(vehicle_type))


@vehicle_router.get(
    "/current-config",
    response_model=VehiclePreset,
    summary="Snapshot the running SITL configuration as a preset (for export).",
)
@to_http_exception
async def current_config() -> VehiclePreset:
    return await _build_current_config_preset(
        name="Current configuration",
        description="Captured from the running SITL vehicle.",
    )


def _builtin_names() -> List[str]:
    return [preset.name for preset in all_vehicle_presets() if preset.builtin]


@vehicle_router.post(
    "/presets/save",
    response_model=VehiclePreset,
    summary="Save the running SITL configuration as a preset, replacing one of the same name.",
)
@to_http_exception
async def save_current_preset(request: SavePresetRequest) -> VehiclePreset:
    """Capture what SITL is running now under a name.

    A built-in name is allowed and shadows the curated definition, which is how a built-in
    gets edited. Reverting it later is a delete away.
    """
    custom_presets.ensure_room(custom_presets.VEHICLE_STORE, _builtin_names(), request.name)
    preset = await _build_current_config_preset(name=request.name, description=request.description)
    custom_presets.VEHICLE_STORE.save(preset)
    return preset


@vehicle_router.post(
    "/presets/import",
    response_model=VehiclePreset,
    summary="Import a vehicle preset from a JSON definition and persist it.",
)
@to_http_exception
async def import_preset(preset: VehiclePreset) -> VehiclePreset:
    custom_presets.ensure_room(custom_presets.VEHICLE_STORE, _builtin_names(), preset.name)
    custom_presets.VEHICLE_STORE.save(preset)
    return preset


@vehicle_router.post(
    "/presets/{name}/rename",
    response_model=VehiclePreset,
    summary="Rename a vehicle preset; renaming a built-in copies it.",
)
@to_http_exception
async def rename_preset(name: str, request: RenamePresetRequest) -> VehiclePreset:
    return custom_presets.rename(custom_presets.VEHICLE_STORE, all_vehicle_presets(), name, request.name)


@vehicle_router.delete(
    "/presets/{name}",
    response_model=OperationResult,
    summary="Delete a saved vehicle preset, or revert an edited built-in.",
)
@to_http_exception
async def delete_preset(name: str) -> OperationResult:
    return OperationResult(
        success=True, detail=custom_presets.remove(custom_presets.VEHICLE_STORE, _builtin_names(), name)
    )


@vehicle_router.post(
    "/presets/{name}/apply",
    response_model=ApplyJob,
    summary="Apply a vehicle preset: firmware, SITL frame and parameters.",
)
@to_http_exception
async def apply_vehicle_preset(name: str) -> ApplyJob:
    """Start bringing SITL to a known vehicle configuration.

    Returns immediately with the job to poll: the work installs the matching firmware,
    persists the SITL frame, writes the parameters that differ from what the vehicle
    already holds, and restarts the autopilot so frame-defining parameters (FRAME_CLASS /
    FRAME_CONFIG) rebuild the motor matrix.
    """
    await require_sitl("applying a preset would reflash and reconfigure the connected autopilot")
    match = next((item for item in all_vehicle_presets() if item.name == name), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown vehicle preset '{name}'.")
    preset = match
    return _start_job(lambda: apply_job.start_preset(preset))
