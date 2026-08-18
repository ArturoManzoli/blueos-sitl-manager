from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route

from sitl_manager import autopilot, custom_presets, mavlink
from sitl_manager.api.common import require_sitl, to_http_exception
from sitl_manager.models import (
    AppliedParams,
    Environment,
    EnvironmentPreset,
    OperationResult,
    RenamePresetRequest,
)
from sitl_manager.presets import ENVIRONMENT_PARAM_MAP, all_environment_presets

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

    A PARAM_SET is unacknowledged, so without a read-back a preset can land in part — a
    simulator left with waves enabled but no wind — and still be reported as a success. Each
    value is read back, and written again if it did not take.
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
    return all_environment_presets()


def _builtin_names() -> List[str]:
    return [preset.name for preset in all_environment_presets() if preset.builtin]


@environment_router.post(
    "/presets",
    response_model=EnvironmentPreset,
    summary="Save ambient conditions as a preset, replacing one of the same name.",
)
@to_http_exception
async def save_preset(preset: EnvironmentPreset) -> EnvironmentPreset:
    """Store named ambient conditions, whether set on the sliders or imported.

    A built-in name is allowed and shadows the shipped conditions, which is how a built-in gets
    edited; deleting it later brings the original back.
    """
    custom_presets.ensure_room(custom_presets.ENVIRONMENT_STORE, _builtin_names(), preset.name)
    custom_presets.ENVIRONMENT_STORE.save(preset)
    return preset


@environment_router.post(
    "/presets/{name}/rename",
    response_model=EnvironmentPreset,
    summary="Rename an ambient preset; renaming a built-in copies it.",
)
@to_http_exception
async def rename_preset(name: str, request: RenamePresetRequest) -> EnvironmentPreset:
    return custom_presets.rename(custom_presets.ENVIRONMENT_STORE, all_environment_presets(), name, request.name)


@environment_router.delete(
    "/presets/{name}",
    response_model=OperationResult,
    summary="Delete a saved ambient preset, or revert an edited built-in.",
)
@to_http_exception
async def delete_preset(name: str) -> OperationResult:
    detail = custom_presets.remove(custom_presets.ENVIRONMENT_STORE, _builtin_names(), name)
    return OperationResult(success=True, detail=detail)


@environment_router.post("/presets/{name}", response_model=AppliedParams, summary="Apply an ambient preset by name.")
@to_http_exception
async def apply_preset(name: str) -> AppliedParams:
    await require_sitl("ambient conditions only exist in the simulator")
    preset = next((preset for preset in all_environment_presets() if preset.name == name), None)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown preset '{name}'.")
    return await _apply(preset.environment)
