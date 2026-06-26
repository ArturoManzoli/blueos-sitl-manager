from typing import List

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route
from loguru import logger

from sitl_manager import autopilot
from sitl_manager.api.common import to_http_exception
from sitl_manager.models import FrameRequest, OperationResult, VehicleStatus, VehicleTypeRequest

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
    firmwares = await autopilot.available_firmwares(request.vehicle)
    stable = next((firmware for firmware in firmwares if "STABLE" in firmware.get("name", "").upper()), None)
    if stable is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stable firmware found for {request.vehicle.value}.",
        )
    logger.info(f"Installing {stable['name']} for {request.vehicle.value}")
    await autopilot.install_firmware_from_url(stable["url"], make_default=True)
    return OperationResult(success=True, detail=f"Installing {stable['name']}. The autopilot will restart.")


@vehicle_router.post("/restart", response_model=OperationResult, summary="Restart the autopilot.")
@to_http_exception
async def restart() -> OperationResult:
    await autopilot.restart()
    return OperationResult(success=True, detail="Autopilot restarted.")
