from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from sitl_manager.http import get_session
from sitl_manager.models import Vehicle
from sitl_manager.settings import (
    ARDUPILOT_MANAGER_URL,
    FIRMWARE_INSTALL_TIMEOUT,
    FIRMWARE_LIST_TIMEOUT,
    HTTP_TIMEOUT,
)


def _encode_params(params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """aiohttp rejects bool query params; ardupilot-manager expects lowercase strings."""
    if params is None:
        return None
    return {key: (str(value).lower() if isinstance(value, bool) else value) for key, value in params.items()}


def _timeout_kwargs(timeout: Optional[float]) -> Dict[str, Any]:
    """Override the session-wide timeout for a call that is expected to take longer."""
    return {} if timeout is None else {"timeout": aiohttp.ClientTimeout(total=timeout)}


def _timed_out(path: str, timeout: Optional[float]) -> str:
    """A timeout worth reading: which call gave up, and how long it waited.

    These surface verbatim in the progress dialog, where a bare "TimeoutError" says nothing
    about whether the autopilot, the firmware index or the download is the one stalling.
    """
    return f"ArduPilot Manager did not answer {path} within {timeout or HTTP_TIMEOUT:.0f}s."


async def _get(path: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Any:
    session = get_session()
    try:
        async with session.get(
            f"{ARDUPILOT_MANAGER_URL}{path}", params=_encode_params(params), **_timeout_kwargs(timeout)
        ) as response:
            response.raise_for_status()
            return await response.json()
    except TimeoutError as error:
        raise TimeoutError(_timed_out(path, timeout)) from error


async def _post(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Any = None,
    timeout: Optional[float] = None,
) -> Any:
    session = get_session()
    try:
        async with session.post(
            f"{ARDUPILOT_MANAGER_URL}{path}",
            params=_encode_params(params),
            json=json_body,
            **_timeout_kwargs(timeout),
        ) as response:
            response.raise_for_status()
            if response.content_type == "application/json":
                return await response.json()
            return await response.text()
    except TimeoutError as error:
        raise TimeoutError(_timed_out(path, timeout)) from error


async def get_board() -> Optional[Dict[str, Any]]:
    return await _get("/board")


async def get_firmware_vehicle_type() -> Optional[str]:
    try:
        return await _get("/firmware_vehicle_type")
    except Exception as error:  # noqa: BLE001 - unavailable when no board is running
        logger.debug(f"firmware_vehicle_type unavailable: {error}")
        return None


async def get_sitl_frame() -> Optional[str]:
    """The persisted SITL frame. It lives behind its own endpoint, not on the board."""
    try:
        frame = await _get("/sitl_frame")
    except Exception as error:  # noqa: BLE001 - unavailable when no board is running
        logger.debug(f"sitl_frame unavailable: {error}")
        return None
    return str(frame) if frame else None


async def get_vehicle_type() -> Optional[str]:
    """The vehicle type the autopilot reports over MAVLink, e.g. ``Surface Boat``.

    This is what BlueOS and Cockpit use to identify the vehicle, so it is how we confirm a
    reconfigured SITL really came back as the vehicle the preset asked for.
    """
    try:
        vehicle_type = await _get("/vehicle_type")
    except Exception as error:  # noqa: BLE001 - unavailable while the autopilot is booting
        logger.debug(f"vehicle_type unavailable: {error}")
        return None
    return str(vehicle_type) if vehicle_type else None


async def set_sitl_frame(frame: str) -> None:
    # ArduPilot Manager persists the frame; it only takes effect on the next SITL start.
    await _post("/sitl_frame", params={"frame": frame})


async def restart() -> None:
    await _post("/restart")


async def available_firmwares(vehicle: Vehicle) -> List[Dict[str, Any]]:
    # ArduPilot Manager fetches and parses ArduPilot's firmware index for this, over the
    # internet from the vehicle itself: it answers in tens of seconds, not the couple its
    # local endpoints take, so it cannot live within the shared HTTP timeout.
    return await _get("/available_firmwares", params={"vehicle": vehicle.value}, timeout=FIRMWARE_LIST_TIMEOUT)


async def install_firmware_from_url(url: str, make_default: bool = True) -> None:
    # Firmware install is a long download/unpack; override the short default HTTP timeout.
    await _post(
        "/install_firmware_from_url",
        params={"url": url, "make_default": make_default},
        timeout=FIRMWARE_INSTALL_TIMEOUT,
    )


async def latest_stable_firmware(vehicle: Vehicle) -> Dict[str, Any]:
    """The newest stable build offered for a vehicle type.

    Kept apart from installing it because looking it up is the slow half, and the caller has
    a step to report while it waits.

    Raises ValueError when no stable build is offered for the vehicle.
    """
    firmwares = await available_firmwares(vehicle)
    stable = next((fw for fw in firmwares if "STABLE" in str(fw.get("name", "")).upper()), None)
    if stable is None:
        raise ValueError(f"No stable firmware found for {vehicle.value}.")
    return stable


def is_sitl(board: Optional[Dict[str, Any]]) -> bool:
    if not board:
        return False
    platform = str(board.get("platform", "")).lower()
    name = str(board.get("name", "")).lower()
    return "sitl" in platform or name == "sitl"
