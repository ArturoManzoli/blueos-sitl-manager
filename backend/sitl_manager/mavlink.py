import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from sitl_manager.http import get_session
from sitl_manager.models import ParamType
from sitl_manager.settings import DEFAULT_SYSTEM_ID, MAVLINK2REST_URL

PARAM_ID_LENGTH = 16
GCS_SYSTEM_ID = 255
GCS_COMPONENT_ID = 0
AUTOPILOT_COMPONENT_ID = 1


def _encode_param_id(name: str) -> List[str]:
    """MAVLink param_id is a fixed 16-char field; mavlink2rest expects it as a list of
    single characters, null-padded, matching the BlueOS frontend encoding."""
    chars = list(name)[:PARAM_ID_LENGTH]
    chars.extend(["\u0000"] * (PARAM_ID_LENGTH - len(chars)))
    return chars


def _decode_param_id(raw: Any) -> str:
    if isinstance(raw, list):
        raw = "".join(str(char) for char in raw)
    return str(raw).replace("\u0000", "").strip()


async def send_message(message: Dict[str, Any], system_id: int = GCS_SYSTEM_ID, component_id: int = GCS_COMPONENT_ID) -> None:
    payload = {
        "header": {"system_id": system_id, "component_id": component_id, "sequence": 0},
        "message": message,
    }
    session = get_session()
    async with session.post(f"{MAVLINK2REST_URL}/mavlink", json=payload) as response:
        response.raise_for_status()


async def set_param(
    name: str,
    value: float,
    system_id: int = DEFAULT_SYSTEM_ID,
    param_type: ParamType = ParamType.REAL32,
) -> None:
    logger.info(f"Setting {name}={value} on system {system_id}")
    await send_message(
        {
            "type": "PARAM_SET",
            "param_value": value,
            "target_system": system_id,
            "target_component": 0,
            "param_id": _encode_param_id(name),
            "param_type": {"type": param_type.value},
        }
    )


async def get_param(
    name: str,
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 3.0,
    poll_interval: float = 0.2,
) -> Optional[float]:
    """Request a single parameter and poll the cached PARAM_VALUE until it matches.

    mavlink2rest only retains the most recent PARAM_VALUE, so we trigger a fresh read
    and wait for the autopilot to answer with the parameter we asked for.
    """
    await send_message(
        {
            "type": "PARAM_REQUEST_READ",
            "param_id": _encode_param_id(name),
            "param_index": -1,
            "target_system": system_id,
            "target_component": 0,
        }
    )

    session = get_session()
    url = f"{MAVLINK2REST_URL}/mavlink/vehicles/{system_id}/components/{AUTOPILOT_COMPONENT_ID}/messages/PARAM_VALUE"
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    body = await response.json()
                    message = body.get("message", {})
                    if _decode_param_id(message.get("param_id", "")) == name:
                        return float(message.get("param_value"))
        except Exception as error:  # noqa: BLE001 - best-effort read, keep polling
            logger.debug(f"PARAM_VALUE poll for {name} failed: {error}")
        await asyncio.sleep(poll_interval)

    logger.warning(f"Timed out reading parameter {name}")
    return None


async def wait_until_ready(
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 120.0,
    poll_interval: float = 2.0,
    probe_param: str = "SYSID_THISMAV",
) -> bool:
    """Block until the autopilot answers a parameter read, i.e. it has finished booting.

    Used after a restart so we only push the preset parameters once SITL is back up and
    its parameter system is serving requests.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await get_param(probe_param, system_id, timeout=2.0) is not None:
            return True
        await asyncio.sleep(poll_interval)
    logger.warning("Timed out waiting for the autopilot to become ready")
    return False


async def set_param_verified(
    name: str,
    value: float,
    system_id: int = DEFAULT_SYSTEM_ID,
    attempts: int = 3,
) -> bool:
    """Set a parameter and confirm it stuck by reading it back, retrying a few times.

    Returns True once the autopilot reports the value within a small tolerance.
    """
    tolerance = max(1e-3, abs(value) * 1e-3)
    for _ in range(attempts):
        await set_param(name, value, system_id)
        readback = await get_param(name, system_id, timeout=2.0)
        if readback is not None and abs(readback - value) <= tolerance:
            return True
        await asyncio.sleep(0.3)
    logger.warning(f"Could not verify {name}={value} after {attempts} attempts")
    return False


async def set_gps_global_origin(
    latitude: float,
    longitude: float,
    altitude: float = 0.0,
    system_id: int = DEFAULT_SYSTEM_ID,
) -> None:
    """Move the EKF origin. Latitude/longitude are sent as degE7 and altitude as mm."""
    await send_message(
        {
            "type": "SET_GPS_GLOBAL_ORIGIN",
            "latitude": round(latitude * 1e7),
            "longitude": round(longitude * 1e7),
            "altitude": round(altitude * 1e3),
            "target_system": system_id,
            "time_usec": 0,
        }
    )
