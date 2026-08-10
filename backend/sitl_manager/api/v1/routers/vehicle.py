from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route

from sitl_manager import apply_job, autopilot, mavlink
from sitl_manager.api.common import to_http_exception
from sitl_manager import custom_presets
from sitl_manager.models import (
    ActivePreset,
    ApplyJob,
    FrameRequest,
    OperationResult,
    SavePresetRequest,
    Vehicle,
    VehiclePreset,
    VehicleStatus,
    VehicleTypeRequest,
)
from sitl_manager.presets import (
    PRESET_EXCLUDED_PREFIXES,
    all_vehicle_presets,
    is_builtin_preset_name,
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
            readings[param] = await mavlink.get_param(param, timeout=1.5)
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
    board = await autopilot.get_board()
    if not autopilot.is_sitl(board):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The active board is not SITL; cannot capture a configuration.",
        )
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

# SITL frames most relevant to marine BlueOS development. The full list lives in
# ArduPilot Manager's SITLFrame enum; these are the ones worth surfacing by default.
SITL_FRAMES: List[str] = [
    "vectored",
    "vectored_6dof",
    "motorboat",
    "motorboat-skid",
    "sailboat",
    "rover",
    "rover-skid",
    "quad",
    "plane",
]


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


@vehicle_router.get("/frames", response_model=List[str], summary="List selectable SITL frames.")
@to_http_exception
async def frames() -> List[str]:
    return SITL_FRAMES


def _start_job(start: Callable[[], ApplyJob]) -> ApplyJob:
    try:
        return start()
    except apply_job.JobBusyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@vehicle_router.get(
    "/apply-job",
    response_model=Optional[ApplyJob],
    summary="Progress of the running (or last) configuration change.",
)
@to_http_exception
async def apply_job_status() -> Optional[ApplyJob]:
    return apply_job.current_job()


@vehicle_router.post("/frame", response_model=ApplyJob, summary="Set the SITL frame and restart.")
@to_http_exception
async def set_frame(request: FrameRequest) -> ApplyJob:
    return _start_job(lambda: apply_job.start_frame(request.frame))


@vehicle_router.post("/type", response_model=ApplyJob, summary="Switch the SITL vehicle type (installs firmware).")
@to_http_exception
async def set_type(request: VehicleTypeRequest) -> ApplyJob:
    return _start_job(lambda: apply_job.start_vehicle(request.vehicle))


@vehicle_router.post("/restart", response_model=OperationResult, summary="Restart the autopilot.")
@to_http_exception
async def restart() -> OperationResult:
    await autopilot.restart()
    return OperationResult(success=True, detail="Autopilot restarted.")


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


@vehicle_router.post(
    "/presets/save",
    response_model=VehiclePreset,
    summary="Save the running SITL configuration as a named custom preset.",
)
@to_http_exception
async def save_current_preset(request: SavePresetRequest) -> VehiclePreset:
    if is_builtin_preset_name(request.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{request.name}' is a built-in preset name; choose another.",
        )
    preset = await _build_current_config_preset(name=request.name, description=request.description)
    custom_presets.save_custom_preset(preset)
    return preset


@vehicle_router.post(
    "/presets/import",
    response_model=VehiclePreset,
    summary="Import a vehicle preset from a JSON definition and persist it.",
)
@to_http_exception
async def import_preset(preset: VehiclePreset) -> VehiclePreset:
    if is_builtin_preset_name(preset.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{preset.name}' is a built-in preset name; rename it before importing.",
        )
    custom_presets.save_custom_preset(preset)
    return preset


@vehicle_router.delete(
    "/presets/{name}",
    response_model=OperationResult,
    summary="Delete a user-saved custom vehicle preset.",
)
@to_http_exception
async def delete_preset(name: str) -> OperationResult:
    if is_builtin_preset_name(name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{name}' is a built-in preset and cannot be deleted.",
        )
    if not custom_presets.delete_custom_preset(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown custom preset '{name}'.")
    return OperationResult(success=True, detail=f"Deleted preset '{name}'.")


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
    match = next((item for item in all_vehicle_presets() if item.name == name), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown vehicle preset '{name}'.")
    preset = match
    return _start_job(lambda: apply_job.start_preset(preset))
