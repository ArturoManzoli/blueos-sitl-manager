from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, status
from fastapi_versioning import versioned_api_route
from loguru import logger

from sitl_manager import autopilot, custom_presets, mavlink
from sitl_manager.api.common import require_sitl, to_http_exception
from sitl_manager.models import (
    Location,
    LocationPreset,
    OperationResult,
    RenamePresetRequest,
)
from sitl_manager.presets import (
    DEFAULT_SPAWN_BY_FIELD,
    LOCATION_PARAM_MAP,
    all_location_presets,
)
from sitl_manager.settings import (
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

# Each of the four spawn parameters is read back and written again if it did not take. A
# PARAM_SET is unacknowledged, so a write lost on the wire is silent, and there are few enough
# of them here that confirming each one properly costs nothing worth counting.
SPAWN_PARAM_ATTEMPTS = 3

VALID_RANGE_BY_FIELD: Dict[str, Tuple[float, float]] = {
    "latitude": (-90.0, 90.0),
    "longitude": (-180.0, 180.0),
    "heading": (0.0, 360.0),
}


# Falls back to the BlueOS default per field, so an unreadable or out-of-range parameter
# yields a sane form value instead of failing the whole read.
def _coerce(field: str, value: Optional[float]) -> float:
    low_high = VALID_RANGE_BY_FIELD.get(field)
    if value is None or (low_high and not low_high[0] <= value <= low_high[1]):
        return DEFAULT_SPAWN_BY_FIELD[field]
    return value


@location_router.get("/presets", response_model=List[LocationPreset], summary="List location presets.")
@to_http_exception
async def list_presets() -> List[LocationPreset]:
    return all_location_presets()


def _builtin_names() -> List[str]:
    return [preset.name for preset in all_location_presets() if preset.builtin]


@location_router.post(
    "/presets",
    response_model=LocationPreset,
    summary="Save a spawn location as a preset, replacing one of the same name.",
)
@to_http_exception
async def save_preset(preset: LocationPreset) -> LocationPreset:
    """Store a named spawn location, whether typed in, picked on the map or imported.

    A built-in name is allowed and shadows the shipped location, which is how a built-in gets
    edited; deleting it later brings the original back.
    """
    custom_presets.ensure_room(custom_presets.LOCATION_STORE, _builtin_names(), preset.name)
    custom_presets.LOCATION_STORE.save(preset)
    return preset


@location_router.post(
    "/presets/{name}/rename",
    response_model=LocationPreset,
    summary="Rename a location preset; renaming a built-in copies it.",
)
@to_http_exception
async def rename_preset(name: str, request: RenamePresetRequest) -> LocationPreset:
    return custom_presets.rename(custom_presets.LOCATION_STORE, all_location_presets(), name, request.name)


@location_router.delete(
    "/presets/{name}",
    response_model=OperationResult,
    summary="Delete a saved location preset, or revert an edited built-in.",
)
@to_http_exception
async def delete_preset(name: str) -> OperationResult:
    detail = custom_presets.remove(custom_presets.LOCATION_STORE, _builtin_names(), name)
    return OperationResult(success=True, detail=detail)


@location_router.get("", response_model=Location, summary="Read the configured SITL spawn location.")
@to_http_exception
async def get_location() -> Location:
    # A real board has no SIM_OPOS_*, so each read would sit out its full timeout before
    # falling back to the same defaults this returns straight away.
    if not autopilot.is_sitl(await autopilot.get_board()):
        return Location(**DEFAULT_SPAWN_BY_FIELD)
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
    await require_sitl("the spawn location only applies to simulated vehicles")
    params = {param: float(getattr(location, field)) for field, param in LOCATION_PARAM_MAP.items()}
    _, unverified = await mavlink.set_params_verified(params, attempts=SPAWN_PARAM_ATTEMPTS)
    if unverified:
        # Some of the four may well have landed, so the vehicle is not where it was and not
        # where it was asked to be either. Say so rather than claiming nothing happened.
        return OperationResult(
            success=False,
            detail=(
                f"Could not confirm {', '.join(unverified)}, so the autopilot was not restarted "
                "and the spawn location may be half applied. Try again."
            ),
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
