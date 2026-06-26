from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi_versioning import versioned_api_route

from sitl_manager import mavlink
from sitl_manager.api.common import to_http_exception
from sitl_manager.models import AppliedParams, Environment, EnvironmentPreset
from sitl_manager.presets import ENVIRONMENT_PARAM_MAP, ENVIRONMENT_PRESETS

environment_router = APIRouter(
    prefix="/environment",
    tags=["environment"],
    route_class=versioned_api_route(1, 0),
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)


async def _apply(environment: Environment) -> List[str]:
    applied: List[str] = []
    for field, param_name in ENVIRONMENT_PARAM_MAP.items():
        value = getattr(environment, field)
        if value is None:
            continue
        await mavlink.set_param(param_name, float(value))
        applied.append(param_name)
    return applied


@environment_router.get("", response_model=Environment, summary="Read the current ambient SIM_* parameters.")
@to_http_exception
async def get_environment() -> Environment:
    values: Dict[str, Optional[float]] = {}
    for field, param_name in ENVIRONMENT_PARAM_MAP.items():
        values[field] = await mavlink.get_param(param_name)
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
    return AppliedParams(applied=await _apply(environment))


@environment_router.get("/presets", response_model=List[EnvironmentPreset], summary="List ambient presets.")
@to_http_exception
async def list_presets() -> List[EnvironmentPreset]:
    return ENVIRONMENT_PRESETS


@environment_router.post("/presets/{name}", response_model=AppliedParams, summary="Apply an ambient preset by name.")
@to_http_exception
async def apply_preset(name: str) -> AppliedParams:
    preset = next((preset for preset in ENVIRONMENT_PRESETS if preset.name == name), None)
    if preset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown preset '{name}'.")
    return AppliedParams(applied=await _apply(preset.environment))
