from fastapi import APIRouter, status
from fastapi_versioning import versioned_api_route

from sitl_manager import power
from sitl_manager.api.common import require_sitl, to_http_exception
from sitl_manager.models import BatteryPack, OperationResult, PowerSupply

power_router = APIRouter(
    prefix="/power",
    tags=["power"],
    route_class=versioned_api_route(1, 0),
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}},
)


@power_router.get("", response_model=PowerSupply, summary="Read the simulated battery pack and what it reads now.")
@to_http_exception
async def get_power() -> PowerSupply:
    return power.state()


@power_router.post("", response_model=PowerSupply, summary="Configure the simulated battery pack, or switch it off.")
@to_http_exception
async def set_power(pack: BatteryPack) -> PowerSupply:
    # Switching it off is allowed anywhere, since that is how a vehicle gets its own battery
    # back; it is driving one that has nothing to drive outside the simulator.
    if pack.enabled:
        await require_sitl("a simulated battery pack only exists in the simulator")
    await power.apply(pack)
    return power.state()


@power_router.post("/recharge", response_model=OperationResult, summary="Charge the simulated pack back to full.")
@to_http_exception
async def recharge() -> OperationResult:
    seconds = await power.recharge()
    took = f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.0f} min"
    return OperationResult(
        success=True,
        detail=f"Charging at {power.CHARGE_AMPS:.0f} A: full in about {took} of simulated time.",
    )
