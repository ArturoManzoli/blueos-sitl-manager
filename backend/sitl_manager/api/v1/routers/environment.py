from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route

from sitl_manager import autopilot, mavlink
from sitl_manager.api.common import require_sitl, to_http_exception
from sitl_manager.models import AppliedParams, Environment, EnvironmentPreset
from sitl_manager.presets import ENVIRONMENT_PARAM_MAP, ENVIRONMENT_PRESETS

# Ambient values are few enough that a second write costs nothing worth counting, and each
# one that silently fails to land is a condition the user asked for and did not get.
PARAM_ATTEMPTS = 3

# A parameter the running firmware does not have never answers. Reading the whole map at the
# three-second default would have the panel waiting the best part of a minute for the handful
# a given build lacks, so the read gives up on a silent name quickly; one that exists answers
# on the first poll.
READ_TIMEOUT = 0.8

environment_router = APIRouter(
    prefix="/environment",
    tags=["environment"],
    route_class=versioned_api_route(1, 0),
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)


async def _apply(environment: Environment) -> AppliedParams:
    """Write the ambient parameters the request names, confirming each one.

    These used to be fired off as a burst of unacknowledged PARAM_SETs, which meant a preset
    could land in part — a simulator left with waves enabled but no wind, reported as a
    success. Each value is now read back and written again if it did not take.
    """
    params = {
        param_name: float(getattr(environment, field))
        for field, param_name in ENVIRONMENT_PARAM_MAP.items()
        if getattr(environment, field) is not None
    }
    applied, unverified = await mavlink.set_params_verified(params, attempts=PARAM_ATTEMPTS)
    return AppliedParams(applied=applied, unverified=unverified)


@environment_router.get("", response_model=Environment, summary="Read the current ambient SIM_* parameters.")
@to_http_exception
async def get_environment() -> Environment:
    # SIM_* exists only in the simulator, so on a real board every name would go unanswered
    # and the panel would wait out a timeout apiece to learn nothing.
    if not autopilot.is_sitl(await autopilot.get_board()):
        return Environment()
    values: Dict[str, Optional[float]] = {}
    for field, param_name in ENVIRONMENT_PARAM_MAP.items():
        values[field] = await mavlink.get_param(param_name, timeout=READ_TIMEOUT)
    # The model only accepts these two fields when positive (they are meaningless at 0).
    # SITL legitimately reports them as defaults like SIM_SPEEDUP = -1 ("no override"),
    # so treat a non-positive read as "unset" instead of failing the whole read.
    for field in ("speedup", "wave_length"):
        value = values.get(field)
        if value is not None and value <= 0:
            values[field] = None
    return Environment(**values)


@environment_router.post("", response_model=AppliedParams, summary="Set one or more ambient SIM_* parameters.")
@to_http_exception
async def set_environment(environment: Environment) -> AppliedParams:
    await require_sitl("ambient conditions only exist in the simulator")
    return await _apply(environment)


@environment_router.get("/presets", response_model=List[EnvironmentPreset], summary="List ambient presets.")
@to_http_exception
async def list_presets() -> List[EnvironmentPreset]:
    return ENVIRONMENT_PRESETS


@environment_router.post("/presets/{name}", response_model=AppliedParams, summary="Apply an ambient preset by name.")
@to_http_exception
async def apply_preset(name: str) -> AppliedParams:
    await require_sitl("ambient conditions only exist in the simulator")
    preset = next((preset for preset in ENVIRONMENT_PRESETS if preset.name == name), None)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown preset '{name}'.")
    return await _apply(preset.environment)
