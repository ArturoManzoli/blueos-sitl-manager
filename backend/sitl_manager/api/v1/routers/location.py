from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route
from loguru import logger

from sitl_manager import autopilot, mavlink
from sitl_manager.api.common import to_http_exception
from sitl_manager.models import Location, LocationPreset, OperationResult
from sitl_manager.presets import LOCATION_PARAM_MAP, LOCATION_PRESETS
from sitl_manager.settings import (
    DEFAULT_HOME_ALTITUDE,
    DEFAULT_HOME_HEADING,
    DEFAULT_HOME_LATITUDE,
    DEFAULT_HOME_LONGITUDE,
    SPAWN_VERIFY_RADIUS,
    SPAWN_VERIFY_TIMEOUT,
    VEHICLE_READY_TIMEOUT,
)

location_router = APIRouter(
    prefix="/location",
    tags=["location"],
    route_class=versioned_api_route(1, 0),
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)

# Falls back to the BlueOS defaults per field, so an unreadable or out-of-range parameter
# yields a sane form value instead of failing the whole read.
DEFAULTS_BY_FIELD: Dict[str, float] = {
    "latitude": DEFAULT_HOME_LATITUDE,
    "longitude": DEFAULT_HOME_LONGITUDE,
    "altitude": DEFAULT_HOME_ALTITUDE,
    "heading": DEFAULT_HOME_HEADING,
}

VALID_RANGE_BY_FIELD: Dict[str, Tuple[float, float]] = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
    "heading": (0.0, 360.0),
}


def _coerce(field: str, value: Optional[float]) -> float:
    low_high = VALID_RANGE_BY_FIELD.get(field)
    if value is None or (low_high and not low_high[0] <= value <= low_high[1]):
        return DEFAULTS_BY_FIELD[field]
    return value


@location_router.get("/presets", response_model=List[LocationPreset], summary="List location presets.")
@to_http_exception
async def list_presets() -> List[LocationPreset]:
    return LOCATION_PRESETS


@location_router.get("", response_model=Location, summary="Read the configured SITL spawn location.")
@to_http_exception
async def get_location() -> Location:
    values = {field: await mavlink.get_param(param) for field, param in LOCATION_PARAM_MAP.items()}
    return Location(**{field: _coerce(field, value) for field, value in values.items()})


@location_router.post("", response_model=OperationResult, summary="Set the SITL spawn location and restart.")
@to_http_exception
async def set_location(location: Location) -> OperationResult:
    """Move where SITL spawns by writing SIM_OPOS_* and restarting the autopilot.

    ArduPilot only reads these parameters while building the simulated vehicle, so the
    restart is what makes the new location take effect; it then persists across reboots.
    Requires a BlueOS core that no longer forces --home on the SITL binary
    (bluerobotics/BlueOS#3986), which is what the position check below detects.
    """
    board = await autopilot.get_board()
    if not autopilot.is_sitl(board):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The active board is not SITL; the spawn location only applies to simulated vehicles.",
        )

    params = {param: float(getattr(location, field)) for field, param in LOCATION_PARAM_MAP.items()}
    result = await mavlink.set_params_bulk(params)
    if result.failed:
        return OperationResult(
            success=False,
            detail=f"Could not write {', '.join(result.failed)}; the spawn location is unchanged.",
        )

    await autopilot.restart()
    if not await mavlink.wait_until_ready(timeout=VEHICLE_READY_TIMEOUT):
        return OperationResult(
            success=False,
            detail="Spawn location saved, but the autopilot did not come back online in time to confirm it.",
        )

    check = await mavlink.wait_until_positioned(
        location.latitude,
        location.longitude,
        radius=SPAWN_VERIFY_RADIUS,
        timeout=SPAWN_VERIFY_TIMEOUT,
    )
    if check.reached:
        logger.info(f"SITL now spawns at {location.latitude}, {location.longitude}")
        return OperationResult(
            success=True,
            detail=f"SITL now spawns at {location.latitude}, {location.longitude} and will boot there from now on.",
        )
    if check.latitude is None:
        return OperationResult(
            success=False,
            detail=(
                "Spawn location saved and the autopilot restarted, but the vehicle reported no GPS fix, "
                "so the move could not be confirmed. Check that the simulated GPS is enabled."
            ),
        )
    return OperationResult(
        success=False,
        detail=(
            f"Spawn location saved, but the vehicle came up at {check.latitude:.5f}, {check.longitude:.5f}. "
            "This BlueOS version still forces a fixed home on SITL; update BlueOS to spawn elsewhere."
        ),
    )
