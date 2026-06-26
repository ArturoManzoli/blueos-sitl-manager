from typing import List

from fastapi import APIRouter, status
from fastapi.responses import PlainTextResponse
from fastapi_versioning import versioned_api_route
from loguru import logger

from sitl_manager import mavlink
from sitl_manager.api.common import to_http_exception
from sitl_manager.models import LocationPreset, OperationResult, TeleportRequest
from sitl_manager.presets import LOCATION_PRESETS
from sitl_manager.settings import ASSETS_DIR

location_router = APIRouter(
    prefix="/location",
    tags=["location"],
    route_class=versioned_api_route(1, 0),
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)

LUA_TELEPORT_SCRIPT = ASSETS_DIR / "lua" / "sitl_teleport.lua"


@location_router.get("/presets", response_model=List[LocationPreset], summary="List location presets.")
@to_http_exception
async def list_presets() -> List[LocationPreset]:
    return LOCATION_PRESETS


@location_router.post("/teleport", response_model=OperationResult, summary="Relocate the running SITL vehicle.")
@to_http_exception
async def teleport(request: TeleportRequest) -> OperationResult:
    """Move the vehicle's EKF origin to a new location after boot.

    SITL always spawns at the BlueOS default home (Florianópolis) because ArduPilot
    Manager passes a hardcoded ``--home``. While the simulated GPS is active it keeps
    reporting that boot position, so a durable relocation needs the simulated GPS off;
    the EKF then falls back to the origin we set here. For a true GPS-preserving
    teleport, deploy the Lua ``sim:set_pose`` helper (see ``GET /location/lua-script``).
    """
    location = request.location
    if request.disable_simulated_gps:
        # SIM_GPS1_ENABLE is the current name; ignored harmlessly on builds that lack it.
        await mavlink.set_param("SIM_GPS1_ENABLE", 0)

    await mavlink.set_param("ORIGIN_LAT", location.latitude)
    await mavlink.set_param("ORIGIN_LON", location.longitude)
    await mavlink.set_gps_global_origin(location.latitude, location.longitude, location.altitude)

    logger.info(f"Teleported origin to {location.latitude}, {location.longitude}")
    return OperationResult(
        success=True,
        detail="Origin updated. Disable the simulated GPS (default) for the move to persist on the map.",
    )


@location_router.get("/lua-script", response_class=PlainTextResponse, summary="Lua sim:set_pose teleport helper.")
@to_http_exception
async def lua_script() -> str:
    if not LUA_TELEPORT_SCRIPT.exists():
        return "-- Lua teleport helper not bundled in this build."
    return LUA_TELEPORT_SCRIPT.read_text(encoding="utf-8")
