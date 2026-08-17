import asyncio
import json
import math
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

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


# How close a value has to be to count as the one that was asked for: enough to absorb a
# float32 round trip, which keeps seven significant digits, and no more. A wider margin also
# decides that a parameter needs no writing, and the values a simulator turns on can be finer
# than that: ArduPilot reads an accelerometer whose offsets are zero and whose scales are one
# as uncalibrated and refuses to arm, so the 0.001 and 1.001 placeholders that make a simulated
# vehicle armable have to count as values a zeroed vehicle does not already hold.
PARAM_EPSILON = 1e-6


def values_match(readback: float, target: float) -> bool:
    """Whether a parameter read back counts as holding the value that was written.

    Parameters travel as float32 and several are stored as integers, so an exact
    comparison would call a correct write a failure.
    """
    return abs(readback - target) <= max(PARAM_EPSILON, abs(target) * PARAM_EPSILON)


# A parameter write is echoed by the autopilot, so the read-back that confirms it normally
# lands on the first poll; these only have to cover a busy simulator.
VERIFY_TIMEOUT = 0.6
VERIFY_POLL = 0.05
SEND_DELAY = 0.02

# mavlink2rest keeps one PARAM_VALUE per vehicle, so any other client reading parameters —
# Cockpit opening its parameter editor, BlueOS refreshing — overwrites the slot our read-back
# is watching, and the answer we are waiting for is gone. A write that has to be confirmed
# rather than merely attempted therefore waits several times longer than a quiet link needs,
# so a value that did land is not reported as unwritten.
NAMED_SET_VERIFY_TIMEOUT = 3.0

# The other client reading parameters is usually this one: the page loads every panel at once,
# and each panel reads its own handful. Held from a request until its answer lands, so two of
# our own reads queue instead of carrying each other's answers off — the one kind of loss that
# is ours to prevent rather than to survive.
_param_lock = asyncio.Lock()


async def set_param_verified(
    name: str,
    value: float,
    system_id: int = DEFAULT_SYSTEM_ID,
    attempts: int = 1,
    timeout: float = VERIFY_TIMEOUT,
    poll_interval: float = VERIFY_POLL,
    retry_on_silence: bool = False,
) -> Optional[float]:
    """Write a parameter and read it back, returning what the autopilot reports.

    A PARAM_SET is unacknowledged, so a dropped write is silent: the autopilot simply keeps
    the old value, and reading back is the only way to find out. An answer that still shows
    the old value is exactly that signal, so it is worth writing again.

    What silence means depends on the caller. Writing a preset's hundreds of parameters, it
    means this firmware does not have the name, which no amount of asking will change — the
    asymmetry that keeps retries from costing anything on the usual unsupported handful. For
    a name known to exist, it means the answer went missing, which is worth another go, and
    ``retry_on_silence`` says which of the two the caller is dealing with.
    """
    readback: Optional[float] = None
    for attempt in range(1, attempts + 1):
        # The write and its read-back are one exchange: another read starting in between would
        # take the echo, and this would write again over a value that had landed.
        async with _param_lock:
            # Counted before the write so the autopilot's own echo of it can settle the
            # read-back, while a value cached from before the write still cannot.
            since = await param_value_count(system_id)
            await set_param(name, value, system_id)
            await asyncio.sleep(SEND_DELAY)
            readback = await _read_param_once(name, system_id, timeout, poll_interval, since)
        if readback is not None and values_match(readback, value):
            return readback
        if readback is None and not retry_on_silence:
            return None
        if attempt < attempts:
            logger.warning(f"{name} reads {readback} after writing {value}; writing again")
    return readback


async def read_message(name: str, system_id: int = DEFAULT_SYSTEM_ID) -> Optional[Dict[str, Any]]:
    """The last message of a type mavlink2rest saw, wrapped in the status envelope it adds."""
    session = get_session()
    url = f"{MAVLINK2REST_URL}/mavlink/vehicles/{system_id}/components/{AUTOPILOT_COMPONENT_ID}/messages/{name}"
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            body: Optional[Dict[str, Any]] = await response.json()
            return body if isinstance(body, dict) else None
    except Exception as error:  # noqa: BLE001 - best-effort read, callers keep polling
        logger.debug(f"{name} read failed: {error}")
        return None


def _message_counter(body: Optional[Dict[str, Any]]) -> Optional[int]:
    """How many of this message type mavlink2rest has seen, from its status envelope."""
    counter = ((body or {}).get("status") or {}).get("time", {}).get("counter")
    return int(counter) if isinstance(counter, (int, float)) else None


async def _await_param_value(
    match: Callable[[Dict[str, Any]], bool],
    system_id: int,
    timeout: float,
    poll_interval: float,
    since: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Poll the cached PARAM_VALUE for an answer satisfying ``match``.

    mavlink2rest retains only the most recent PARAM_VALUE, so a read is a request followed by
    watching that one slot. ``since`` is the message count taken before the request was sent:
    the answer has to be newer than that, otherwise the value sitting in the slot from an
    earlier read would be taken for a reply to this one.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        body = await read_message("PARAM_VALUE", system_id)
        counter = _message_counter(body)
        fresh = since is None or counter is None or counter > since
        message: Dict[str, Any] = (body or {}).get("message") or {}
        if fresh and message and match(message):
            return message
        await asyncio.sleep(poll_interval)
    return None


async def param_value_count(system_id: int = DEFAULT_SYSTEM_ID) -> Optional[int]:
    """How many PARAM_VALUEs mavlink2rest has seen, for callers that read back a write."""
    return _message_counter(await read_message("PARAM_VALUE", system_id))


async def _read_param_once(
    name: str,
    system_id: int,
    timeout: float,
    poll_interval: float,
    since: Optional[int],
) -> Optional[float]:
    """One request for a parameter and the wait for its answer, the caller holding the lock.

    ``since`` is a PARAM_VALUE count from before the caller did something the autopilot answers
    unprompted — a write, which it echoes — so that the echo counts as the answer instead of
    being dismissed as stale. None takes the count at the time of the request.
    """
    if since is None:
        since = await param_value_count(system_id)
    await send_message(
        {
            "type": "PARAM_REQUEST_READ",
            "param_id": _encode_param_id(name),
            "param_index": -1,
            "target_system": system_id,
            "target_component": 0,
        }
    )

    message = await _await_param_value(
        lambda answer: _decode_param_id(answer.get("param_id", "")) == name,
        system_id,
        timeout,
        poll_interval,
        since,
    )
    if message is None:
        return None
    value = message.get("param_value")
    return float(value) if isinstance(value, (int, float)) else None


async def get_param(
    name: str,
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 3.0,
    poll_interval: float = 0.2,
    attempts: int = 1,
) -> Optional[float]:
    """Read one parameter by name, or None when the autopilot does not answer for it.

    ``attempts`` asks again when nothing comes back, and is worth spending wherever a missing
    answer would otherwise pass for a missing value: an autopilot still settling after a restart
    answers late rather than not at all, and a client outside this process — Cockpit's parameter
    editor, BlueOS refreshing — can still carry an answer off the one slot that holds it.
    """
    async with _param_lock:
        for attempt in range(1, attempts + 1):
            value = await _read_param_once(name, system_id, timeout, poll_interval, None)
            if value is not None:
                return value
            if attempt < attempts:
                logger.debug(f"No answer for parameter {name}; asking again")
    logger.warning(f"Timed out reading parameter {name}")
    return None


async def get_param_by_index(
    index: int,
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 3.0,
    poll_interval: float = 0.2,
) -> Optional[str]:
    """Read a parameter by its position in the table, returning the name that answered.

    A PARAM_REQUEST_READ with a param_index of 0 or more selects by index and ignores the
    name, which is the only way to ask a question every ArduPilot version answers the same.
    """
    async with _param_lock:
        since = _message_counter(await read_message("PARAM_VALUE", system_id))
        await send_message(
            {
                "type": "PARAM_REQUEST_READ",
                "param_id": _encode_param_id(""),
                "param_index": index,
                "target_system": system_id,
                "target_component": 0,
            }
        )

        message = await _await_param_value(
            lambda answer: answer.get("param_index") == index,
            system_id,
            timeout,
            poll_interval,
            since,
        )
    return _decode_param_id(message.get("param_id", "")) if message else None


async def heartbeat_count(system_id: int = DEFAULT_SYSTEM_ID) -> Optional[int]:
    """How many HEARTBEATs mavlink2rest has seen, or None if it has never seen one."""
    return _message_counter(await read_message("HEARTBEAT", system_id))


# Which parameter the readiness probe asks for, by position rather than by name. Names are
# not stable across ArduPilot releases — 4.6 renamed SYSID_THISMAV to MAV_SYSID — and a name
# the running firmware does not know is simply never answered, which looks exactly like an
# autopilot that never came back.
READY_PROBE_INDEX = 0
READY_PROBE_TIMEOUT = 3.0


async def wait_until_ready(
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 120.0,
    poll_interval: float = 1.0,
    on_wait: Optional[Callable[[float, str], None]] = None,
) -> bool:
    """Block until the autopilot is heartbeating again and serving parameter reads.

    Both halves matter after a restart: the heartbeat says the process is back, and a
    parameter read says the part we are about to use is up. Liveness is taken from the
    heartbeat count moving rather than from the message being there, because mavlink2rest
    keeps serving the last heartbeat it saw long after the vehicle went away.

    ``on_wait`` is called with the seconds spent so far and what is still missing, so a caller
    driving a progress dialog can show that a restart is in flight rather than hung.
    """
    loop = asyncio.get_event_loop()
    started = loop.time()
    before = await heartbeat_count(system_id)

    while loop.time() - started < timeout:
        count = await heartbeat_count(system_id)
        beating = count is not None and (before is None or count > before)
        if beating and await get_param_by_index(READY_PROBE_INDEX, system_id, READY_PROBE_TIMEOUT) is not None:
            return True
        if on_wait is not None:
            on_wait(loop.time() - started, "no heartbeat yet" if not beating else "waiting for parameters")
        await asyncio.sleep(poll_interval)

    logger.warning("Timed out waiting for the autopilot to become ready")
    return False


async def set_params_verified(
    params: Dict[str, float],
    system_id: int = DEFAULT_SYSTEM_ID,
    attempts: int = 1,
    timeout: float = NAMED_SET_VERIFY_TIMEOUT,
) -> Tuple[List[str], List[str]]:
    """Write a handful of parameters, confirming each one. Returns (applied, unverified).

    For the small named sets — the spawn location, the ambient conditions — where every value
    matters, every name is one a SITL build has, and there are few enough that reading each
    one back properly costs nothing. This is deliberately not how the preset's hundreds of
    parameters are written: those go one at a time through the job engine, which has a
    progress dialog to report each on and expects some names to be missing.
    """
    applied: List[str] = []
    unverified: List[str] = []
    for name, value in params.items():
        target = float(value)
        readback = await set_param_verified(
            name, target, system_id, attempts=attempts, timeout=timeout, retry_on_silence=True
        )
        if readback is not None and values_match(readback, target):
            applied.append(name)
        else:
            logger.warning(f"{name} did not take {target} (read back {readback})")
            unverified.append(name)
    return applied, unverified


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


async def _collect_param_burst(
    ws: aiohttp.ClientWebSocketResponse,
    params: Dict[str, float],
    deadline: float,
    idle_timeout: float,
) -> Optional[int]:
    """Collect a ``PARAM_REQUEST_LIST`` burst off the stream into ``params``.

    Returns the table size the autopilot declared, or None if it never said. Stops on a
    complete table, on the stream going quiet for ``idle_timeout``, or on ``deadline``.
    """
    expected: Optional[int] = None
    loop = asyncio.get_event_loop()
    while loop.time() < deadline:
        remaining = min(deadline - loop.time(), idle_timeout)
        try:
            raw = await ws.receive(timeout=max(remaining, 0.1))
        except asyncio.TimeoutError:
            return expected  # the stream went quiet
        if raw.type is not aiohttp.WSMsgType.TEXT:
            if raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                return expected
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
            return expected
    return expected


# How many times the parameter list is asked for before the dump gives up on completing it. A
# burst that stops short is not a finished burst: an autopilot fresh from a restart can answer
# the first few names and then go quiet for longer than a settled one ever does, and a dump
# taken as complete at that point reports parameters the vehicle holds as ones it does not.
# Asking again costs nothing once the table is in, since a complete dump returns before this.
DUMP_REQUESTS = 3


async def dump_all_params(
    system_id: int = DEFAULT_SYSTEM_ID,
    timeout: float = 30.0,
    idle_timeout: float = 3.0,
) -> Dict[str, float]:
    """Read every onboard parameter the autopilot reports.

    mavlink2rest only caches the latest ``PARAM_VALUE`` over REST, so the burst that
    answers a ``PARAM_REQUEST_LIST`` can only be captured on the websocket stream. We
    open the stream, request the list, and collect values until the autopilot's declared
    ``param_count`` is reached, the overall timeout elapses, or the stream has gone quiet
    short of the table that many times.
    """
    ws_url = MAVLINK2REST_URL.replace("http", "ws", 1) + "/ws/mavlink?filter=PARAM_VALUE"
    params: Dict[str, float] = {}
    expected: Optional[int] = None

    # The burst overwrites the cached PARAM_VALUE hundreds of times over, so a read running
    # alongside it would find everything except its own answer: they take turns instead.
    async with _param_lock:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as ws_session:
            async with ws_session.ws_connect(ws_url) as ws:
                deadline = asyncio.get_event_loop().time() + timeout
                for attempt in range(1, DUMP_REQUESTS + 1):
                    await send_message(
                        {
                            "type": "PARAM_REQUEST_LIST",
                            "target_system": system_id,
                            "target_component": AUTOPILOT_COMPONENT_ID,
                        }
                    )
                    declared = await _collect_param_burst(ws, params, deadline, idle_timeout)
                    if declared is not None:
                        expected = declared
                    if expected is not None and len(params) >= expected:
                        break
                    if asyncio.get_event_loop().time() >= deadline:
                        break
                    if attempt < DUMP_REQUESTS:
                        logger.warning(f"Parameter burst stopped at {len(params)}/{expected}; asking again")

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
