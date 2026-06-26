from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route

from sitl_manager import autopilot, mavlink
from sitl_manager.api.common import to_http_exception
from sitl_manager.models import (
    ActivePreset,
    FrameRequest,
    OperationResult,
    Vehicle,
    VehiclePreset,
    VehiclePresetResult,
    VehicleStatus,
    VehicleTypeRequest,
)
from sitl_manager.presets import VEHICLE_PRESETS
from sitl_manager.settings import VEHICLE_READY_TIMEOUT

# The frame-defining parameter that distinguishes the presets of each vehicle family:
# FRAME_CONFIG separates BlueROV2 (1) from BlueROV2 Heavy (2); FRAME_CLASS identifies the
# BlueBoat hull (2). Reading just this is enough to tell which preset a vehicle matches.
FRAME_PARAM_BY_VEHICLE = {Vehicle.SUB: "FRAME_CONFIG", Vehicle.ROVER: "FRAME_CLASS"}


async def _detect_active_preset(vehicle_type: str) -> Optional[str]:
    readings: Dict[str, Optional[float]] = {}
    for preset in VEHICLE_PRESETS:
        if preset.vehicle.value.lower() not in vehicle_type.lower():
            continue
        param = FRAME_PARAM_BY_VEHICLE.get(preset.vehicle)
        expected = preset.parameters.get(param) if param else None
        if param is None or expected is None:
            continue
        if param not in readings:
            readings[param] = await mavlink.get_param(param, timeout=1.5)
        actual = readings[param]
        if actual is not None and round(actual) == round(expected):
            return preset.name
    return None

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
    return VehicleStatus(
        board=board.get("name") if board else None,
        is_sitl=autopilot.is_sitl(board),
        frame=board.get("frame") if board else None,
        firmware_vehicle_type=await autopilot.get_firmware_vehicle_type(),
    )


@vehicle_router.get("/frames", response_model=List[str], summary="List selectable SITL frames.")
@to_http_exception
async def frames() -> List[str]:
    return SITL_FRAMES


@vehicle_router.post("/frame", response_model=OperationResult, summary="Set the SITL frame and optionally restart.")
@to_http_exception
async def set_frame(request: FrameRequest) -> OperationResult:
    await autopilot.set_sitl_frame(request.frame)
    if request.restart:
        await autopilot.restart()
    detail = "Frame set." if not request.restart else "Frame set and autopilot restarted."
    return OperationResult(success=True, detail=detail)


@vehicle_router.post("/type", response_model=OperationResult, summary="Switch the SITL vehicle type (installs firmware).")
@to_http_exception
async def set_type(request: VehicleTypeRequest) -> OperationResult:
    try:
        name = await autopilot.install_stable_firmware(request.vehicle)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return OperationResult(success=True, detail=f"Installing {name}. The autopilot will restart.")


@vehicle_router.post("/restart", response_model=OperationResult, summary="Restart the autopilot.")
@to_http_exception
async def restart() -> OperationResult:
    await autopilot.restart()
    return OperationResult(success=True, detail="Autopilot restarted.")


@vehicle_router.get("/presets", response_model=List[VehiclePreset], summary="List ready-to-fly vehicle presets.")
@to_http_exception
async def list_vehicle_presets() -> List[VehiclePreset]:
    return VEHICLE_PRESETS


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


@vehicle_router.post(
    "/presets/{name}",
    response_model=VehiclePresetResult,
    summary="Apply a vehicle preset: firmware, SITL frame and parameters.",
)
@to_http_exception
async def apply_vehicle_preset(name: str) -> VehiclePresetResult:
    """Bring SITL to a known vehicle configuration.

    Persists the SITL frame, ensures the matching firmware is installed, restarts the
    autopilot, then writes the preset's parameters once it is back online. A final
    restart rebuilds the motor matrix so frame-defining parameters (FRAME_CONFIG /
    FRAME_CLASS) take effect.
    """
    preset = next((item for item in VEHICLE_PRESETS if item.name == name), None)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown vehicle preset '{name}'.")

    await autopilot.set_sitl_frame(preset.frame)

    current_type = await autopilot.get_firmware_vehicle_type()
    needs_install = not current_type or preset.vehicle.value.lower() not in str(current_type).lower()
    if needs_install:
        try:
            await autopilot.install_stable_firmware(preset.vehicle)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    else:
        await autopilot.restart()

    if not await mavlink.wait_until_ready(timeout=VEHICLE_READY_TIMEOUT):
        return VehiclePresetResult(
            success=False,
            detail="The autopilot did not come back online in time; parameters were not applied.",
            failed=list(preset.parameters),
        )

    applied: List[str] = []
    failed: List[str] = []
    for param_name, value in preset.parameters.items():
        if await mavlink.set_param_verified(param_name, float(value)):
            applied.append(param_name)
        else:
            failed.append(param_name)

    await autopilot.restart()

    detail = f"Applied {preset.name}: {len(applied)} parameter(s) set; autopilot restarted to rebuild the frame."
    if failed:
        detail += f" {len(failed)} parameter(s) could not be verified: {', '.join(failed)}."
    return VehiclePresetResult(success=not failed, detail=detail, applied=applied, failed=failed)
