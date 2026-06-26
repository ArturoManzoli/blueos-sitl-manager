from typing import Any, Dict, List, Optional

from loguru import logger

from sitl_manager.http import get_session
from sitl_manager.models import Vehicle
from sitl_manager.settings import ARDUPILOT_MANAGER_URL


async def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    session = get_session()
    async with session.get(f"{ARDUPILOT_MANAGER_URL}{path}", params=params) as response:
        response.raise_for_status()
        return await response.json()


async def _post(path: str, params: Optional[Dict[str, Any]] = None, json_body: Any = None) -> Any:
    session = get_session()
    async with session.post(f"{ARDUPILOT_MANAGER_URL}{path}", params=params, json=json_body) as response:
        response.raise_for_status()
        if response.content_type == "application/json":
            return await response.json()
        return await response.text()


async def get_board() -> Optional[Dict[str, Any]]:
    return await _get("/board")


async def get_firmware_vehicle_type() -> Optional[str]:
    try:
        return await _get("/firmware_vehicle_type")
    except Exception as error:  # noqa: BLE001 - unavailable when no board is running
        logger.debug(f"firmware_vehicle_type unavailable: {error}")
        return None


async def set_sitl_frame(frame: str) -> None:
    # ArduPilot Manager persists the frame; it only takes effect on the next SITL start.
    await _post("/sitl_frame", params={"frame": frame})


async def restart() -> None:
    await _post("/restart")


async def available_firmwares(vehicle: Vehicle) -> List[Dict[str, Any]]:
    return await _get("/available_firmwares", params={"vehicle": vehicle.value})


async def install_firmware_from_url(url: str, make_default: bool = True) -> None:
    await _post("/install_firmware_from_url", params={"url": url, "make_default": make_default})


def is_sitl(board: Optional[Dict[str, Any]]) -> bool:
    if not board:
        return False
    platform = str(board.get("platform", "")).lower()
    name = str(board.get("name", "")).lower()
    return "sitl" in platform or name == "sitl"
