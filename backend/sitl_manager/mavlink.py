import asyncio
import json
import math
from typing import Any, Dict, List, NamedTuple, Optional

import aiohttp
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


async def send_message(
    message: Dict[str, Any], system_id: int = GCS_SYSTEM_ID, component_id: int = GCS_COMPONENT_ID
) -> None:
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


class BulkParamResult(NamedTuple):
    applied: List[str]
    failed: List[str]
    unverified: List[str]
    aborted: bool


async def set_params_bulk(
    params: Dict[str, float],
    system_id: int = DEFAULT_SYSTEM_ID,
    send_delay: float = 0.02,
    settle_delay: float = 1.0,
    verify_timeout: float = 0.25,
    verify_poll: float = 0.05,
    max_consecutive_timeouts: int = 3,
) -> BulkParamResult:
    """Apply many parameters quickly and report which stuck.

    Fires every PARAM_SET first, then reads each back once with a near-instant timeout.
    Verifying a full parameter file one read at a time is slow, and a handful of params
    this firmware ignores never answer a read at all. To avoid blocking the UI on those,
    we abort the read-back pass as soon as ``max_consecutive_timeouts`` parameters in a
    row fail to answer: every parameter was already sent, so the caller can finish in the
    background. ``aborted`` says whether we bailed; ``unverified`` lists the params left.
    """
    for name, value in params.items():
        await set_param(name, float(value), system_id)
        if send_delay:
            await asyncio.sleep(send_delay)

    # Let the burst of writes settle before reading anything back.
    await asyncio.sleep(settle_delay)

    applied: List[str] = []
    failed: List[str] = []
    items = list(params.items())
    consecutive_timeouts = 0
    for index, (name, value) in enumerate(items):
        target = float(value)
        readback = await get_param(name, system_id, timeout=verify_timeout, poll_interval=verify_poll)
        if readback is None:
            failed.append(name)
            logger.warning(f"Could not verify {name}={target} (no response)")
            consecutive_timeouts += 1
            if consecutive_timeouts >= max_consecutive_timeouts:
                unverified = [item_name for item_name, _ in items[index + 1 :]]
                logger.warning(
                    f"Aborting read-back after {consecutive_timeouts} consecutive timeouts; "
                    f"{len(unverified)} parameter(s) left to settle in the background."
                )
                return BulkParamResult(applied, failed, unverified, aborted=True)
            continue

        consecutive_timeouts = 0
        tolerance = max(1e-3, abs(target) * 1e-3)
        if abs(readback - target) <= tolerance:
            applied.append(name)
        else:
            failed.append(name)
            logger.warning(f"Could not verify {name}={target} (read {readback})")
    return BulkParamResult(applied, failed, [], aborted=False)


def _decode_flight_sw_version(encoded: int) -> Optional[str]:
    """AUTOPILOT_VERSION.flight_sw_version packs the version as
    (major << 24) | (minor << 16) | (patch << 8) | type."""
    if not encoded:
        return None
    major = (encoded >> 24) & 0xFF
    minor = (encoded >> 16) & 0xFF
    patch = (encoded >> 8) & 0xFF
    return f"{major}.{minor}.{patch}"


async def get_autopilot_version(
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 2.0,
    poll_interval: float = 0.2,
) -> Optional[str]:
    """Return the running firmware version (e.g. ``4.5.7``), or ``None`` if unavailable.

    AUTOPILOT_VERSION is only emitted on request, so we ask for it and then poll the
    cached message until the autopilot answers.
    """
    await send_message(
        {
            "type": "COMMAND_LONG",
            "command": {"type": "MAV_CMD_REQUEST_MESSAGE"},
            "param1": 148.0,  # AUTOPILOT_VERSION message id
            "param2": 0.0,
            "param3": 0.0,
            "param4": 0.0,
            "param5": 0.0,
            "param6": 0.0,
            "param7": 0.0,
            "confirmation": 0,
            "target_system": system_id,
            "target_component": AUTOPILOT_COMPONENT_ID,
        }
    )

    session = get_session()
    url = f"{MAVLINK2REST_URL}/mavlink/vehicles/{system_id}/components/{AUTOPILOT_COMPONENT_ID}/messages/AUTOPILOT_VERSION"
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    body = await response.json()
                    raw = body.get("message", {}).get("flight_sw_version")
                    if raw:
                        return _decode_flight_sw_version(int(raw))
        except Exception as error:  # noqa: BLE001 - best-effort read, keep polling
            logger.debug(f"AUTOPILOT_VERSION poll failed: {error}")
        await asyncio.sleep(poll_interval)

    logger.warning("Timed out reading the autopilot firmware version")
    return None


async def dump_all_params(
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 30.0,
    idle_timeout: float = 3.0,
) -> Dict[str, float]:
    """Read every onboard parameter the autopilot reports.

    mavlink2rest only caches the latest ``PARAM_VALUE`` over REST, so the burst that
    answers a ``PARAM_REQUEST_LIST`` can only be captured on the websocket stream. We
    open the stream, request the list, and collect values until the autopilot's declared
    ``param_count`` is reached, the stream idles, or the overall timeout elapses.
    """
    ws_url = MAVLINK2REST_URL.replace("http", "ws", 1) + "/ws/mavlink?filter=PARAM_VALUE"
    params: Dict[str, float] = {}
    expected: Optional[int] = None

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as ws_session:
        async with ws_session.ws_connect(ws_url) as ws:
            await send_message(
                {
                    "type": "PARAM_REQUEST_LIST",
                    "target_system": system_id,
                    "target_component": AUTOPILOT_COMPONENT_ID,
                }
            )
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                remaining = min(deadline - asyncio.get_event_loop().time(), idle_timeout)
                try:
                    raw = await ws.receive(timeout=max(remaining, 0.1))
                except asyncio.TimeoutError:
                    break  # stream went quiet; assume the burst is done
                if raw.type is not aiohttp.WSMsgType.TEXT:
                    if raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                    continue
                try:
                    body = json.loads(raw.data)
                except (ValueError, TypeError):
                    continue
                message = body.get("message", body)
                if message.get("type") != "PARAM_VALUE":
                    continue
                header = body.get("header") or {}
                if header.get("component_id") not in (None, AUTOPILOT_COMPONENT_ID):
                    continue
                name = _decode_param_id(message.get("param_id", ""))
                if not name:
                    continue
                try:
                    params[name] = float(message.get("param_value"))
                except (TypeError, ValueError):
                    continue
                count = message.get("param_count")
                if isinstance(count, int) and count > 0:
                    expected = count
                if expected is not None and len(params) >= expected:
                    break

    if expected is not None and len(params) < expected:
        logger.warning(f"Parameter dump captured {len(params)}/{expected} parameters")
    return params


class PositionCheck(NamedTuple):
    """Outcome of waiting for the vehicle to report itself at a requested position.

    ``latitude``/``longitude`` hold the last fix seen, or None when the vehicle never
    reported one (no simulated GPS, or it never acquired a fix).
    """

    reached: bool
    latitude: Optional[float]
    longitude: Optional[float]


NO_FIX_TYPES = ("GPS_FIX_TYPE_NO_GPS", "GPS_FIX_TYPE_NO_FIX")


def _has_gps_fix(raw: Any) -> bool:
    """mavlink2rest serializes GPS_RAW_INT.fix_type as {"type": "GPS_FIX_TYPE_3D_FIX"};
    tolerate the plain numeric encoding too (2 = 2D fix, the first usable value)."""
    if isinstance(raw, dict):
        return str(raw.get("type", "")) not in NO_FIX_TYPES
    try:
        return int(raw) >= 2
    except (TypeError, ValueError):
        return False


def distance_meters(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    earth_radius = 6_371_000.0
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = phi_b - phi_a
    delta_lambda = math.radians(lon_b - lon_a)
    haversine = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 2 * earth_radius * math.asin(min(1.0, math.sqrt(haversine)))


async def wait_until_positioned(
    latitude: float,
    longitude: float,
    radius: float,
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 30.0,
    poll_interval: float = 1.0,
) -> PositionCheck:
    """Wait for the vehicle to report a GPS fix within ``radius`` meters of a position.

    Used to confirm a new spawn location actually took effect. mavlink2rest serves the
    last message it saw, which right after a restart can still be the pre-restart
    position, so we wait for a matching fix instead of trusting the first reading: a
    stale one simply does not match and polling continues.
    """
    session = get_session()
    url = f"{MAVLINK2REST_URL}/mavlink/vehicles/{system_id}/components/{AUTOPILOT_COMPONENT_ID}/messages/GPS_RAW_INT"
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    message = (await response.json()).get("message", {})
                    if _has_gps_fix(message.get("fix_type")):
                        last_latitude = float(message.get("lat", 0)) / 1e7
                        last_longitude = float(message.get("lon", 0)) / 1e7
                        if distance_meters(last_latitude, last_longitude, latitude, longitude) <= radius:
                            return PositionCheck(True, last_latitude, last_longitude)
        except Exception as error:  # noqa: BLE001 - best-effort read, keep polling
            logger.debug(f"GPS_RAW_INT poll failed: {error}")
        await asyncio.sleep(poll_interval)

    logger.warning(f"Vehicle did not report a position near {latitude}, {longitude}")
    return PositionCheck(False, last_latitude, last_longitude)
