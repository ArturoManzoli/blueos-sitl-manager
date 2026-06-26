from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from sitl_manager.http import get_session
from sitl_manager.models import Vehicle
from sitl_manager.settings import ARDUPILOT_MANAGER_URL, FIRMWARE_INSTALL_TIMEOUT


def _encode_params(params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """aiohttp rejects bool query params; ardupilot-manager expects lowercase strings."""
    if params is None:
        return None
    return {key: (str(value).lower() if isinstance(value, bool) else value) for key, value in params.items()}


async def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    session = get_session()
    async with session.get(f"{ARDUPILOT_MANAGER_URL}{path}", params=_encode_params(params)) as response:
        response.raise_for_status()
        return await response.json()


async def _post(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Any = None,
    timeout: Optional[float] = None,
) -> Any:
    session = get_session()
    extra: Dict[str, Any] = {}
    if timeout is not None:
        extra["timeout"] = aiohttp.ClientTimeout(total=timeout)
    async with session.post(
        f"{ARDUPILOT_MANAGER_URL}{path}", params=_encode_params(params), json=json_body, **extra
    ) as response:
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
    # Firmware install is a long download/unpack; override the short default HTTP timeout.
    await _post(
        "/install_firmware_from_url",
        params={"url": url, "make_default": make_default},
        timeout=FIRMWARE_INSTALL_TIMEOUT,
    )


async def install_stable_firmware(vehicle: Vehicle) -> str:
    """Install the latest stable firmware for a vehicle type and return its name.

    Raises ValueError when no stable build is offered for the vehicle.
    """
    firmwares = await available_firmwares(vehicle)
    stable = next((fw for fw in firmwares if "STABLE" in str(fw.get("name", "")).upper()), None)
    if stable is None:
        raise ValueError(f"No stable firmware found for {vehicle.value}.")
    logger.info(f"Installing {stable['name']} for {vehicle.value}")
    await install_firmware_from_url(stable["url"], make_default=True)
    return str(stable["name"])


def is_sitl(board: Optional[Dict[str, Any]]) -> bool:
    if not board:
        return False
    platform = str(board.get("platform", "")).lower()
    name = str(board.get("name", "")).lower()
    return "sitl" in platform or name == "sitl"
