"""A simulated battery pack: what the vehicle reports drawing, and the charge it has left.

SITL's own battery is a straight line through the throttle stick, 50 A wide open and nothing
at rest, which says little about what a boat spends pushing a hull through water and nothing
at all about pushing it against a stream or a headwind. This drives the readings instead, from
the power curve Cockpit's mission estimates were fitted to.

They reach the ground station through the autopilot's own battery monitor rather than as
messages of this service's own, because Cockpit takes voltage, current and charge from
SYS_STATUS, which only the autopilot sends. SITL puts its simulated pack on analog pins, so
pointing the monitor's current pin at one the simulator leaves at zero volts turns the reading
into ``(0 - BATT_AMP_OFFSET) * BATT_AMP_PERVLT``, an amperage named outright from here, and
BATT_MONITOR still does the rest of the work: integrating the charge spent, deriving the
percentage from BATT_CAPACITY, running its failsafes. Voltage is the SIM_BATT_VOLTAGE knob,
which the simulator sags a little further under throttle.
"""

import asyncio
import json
import math
from typing import Dict, Mapping, Optional, Tuple

from loguru import logger

from sitl_manager import autopilot, mavlink
from sitl_manager.models import BatteryPack, PowerReading, PowerSupply
from sitl_manager.presets import ENVIRONMENT_PARAM_MAP
from sitl_manager.settings import POWER_PACK_FILE

# What a BlueBoat spends pushing its hull through water: the curve Cockpit's mission estimates
# were fitted to over field-test data, 19.13 W at 1 m/s rising with the cube and a third of it.
HULL_WATTS = 19.13
HULL_EXPONENT = 3.33

# The boat's windage, as electrical watts per (m/s)² of headwind per m/s of way: 1.5 m/s into a
# 5 m/s breeze costs some 14 W on top of the hull's 74 W. One number for the air's drag and the
# thrusters' efficiency together, both of which the hull curve above already carries for water.
WINDAGE_WATTS = 0.37

# Resting voltage of one Li-ion cell against the fraction of its charge left, which is what
# turns a pack being spent into a voltage falling on screen.
CELL_CURVE: Tuple[Tuple[float, float], ...] = (
    (0.00, 3.00),
    (0.05, 3.30),
    (0.10, 3.42),
    (0.20, 3.55),
    (0.40, 3.69),
    (0.60, 3.82),
    (0.80, 3.96),
    (0.90, 4.05),
    (1.00, 4.15),
)

# The monitor this service reports through, and the pins it reads. Current comes off a pin the
# simulator does not drive, so the reading is the offset alone; voltage stays on SITL's own pin.
CALIBRATION: Dict[str, float] = {
    "BATT_MONITOR": 4.0,
    "BATT_VOLT_PIN": 13.0,
    "BATT_VOLT_MULT": 10.1,
    "BATT_CURR_PIN": 3.0,
    "BATT_AMP_PERVLT": 17.0,
}

# Without these the pack cannot be reported at all, so an enable that fails to write one of
# them has to say so rather than leave a panel claiming a pack that is not there.
ESSENTIAL = ("BATT_CURR_PIN", "BATT_AMP_PERVLT", "BATT_CAPACITY")

# What the simulator boots with, put back when the simulated pack is switched off.
SITL_DEFAULTS: Dict[str, float] = {
    "BATT_CURR_PIN": 12.0,
    "BATT_AMP_OFFSET": 0.0,
    "BATT_CAPACITY": 3300.0,
    "SIM_BATT_VOLTAGE": 12.6,
}

AMP_PER_VOLT = CALIBRATION["BATT_AMP_PERVLT"]

# Charging is the only way to put the charge back: the autopilot resets a spent pack on a
# command mavlink2rest cannot express, but it does subtract a negative current from what it has
# counted. Held under the 327 A that SYS_STATUS can carry as centiamps.
CHARGE_AMPS = 300.0

TICK_SECONDS = 1.0

# Ambient conditions change when somebody moves a slider, which is rare next to the tick rate.
AMBIENT_TICKS = 10
AMBIENT_READ_TIMEOUT = 0.8

# Applying a vehicle preset writes BATT_MONITOR and BATT_CAPACITY of its own, and restarting the
# autopilot puts every driven value back to what the preset holds, so the monitor is set up again
# every so often rather than only when the pack is. Clearing the deadband cache along with it is
# what makes the next reading land: the vehicle's values moved without this service writing them.
REASSERT_TICKS = 30

# How far a reading has to move to be worth a parameter write, keeping a steady cruise from
# rewriting the same amperage every second.
CURRENT_STEP = 0.05
VOLTAGE_STEP = 0.02

# The draw is a hull curve fitted to a boat, so the pack is only reported while the vehicle is one.
# A preset that turns SITL into an ROV leaves the loop idle with the simulator's own battery back,
# and the pack is taken up again when a boat is, without anyone having to switch it off and on.
BOAT = "Surface Boat"
VEHICLE_TICKS = 10

_task: Optional["asyncio.Task[None]"] = None
_pack: Optional[BatteryPack] = None
_reading: Optional[PowerReading] = None
_charging: bool = False
_written: Dict[str, float] = {}


def cell_voltage(charge: float) -> float:
    """Resting voltage of one cell at a fraction of its charge, between the curve's rows."""
    charge = min(max(charge, 0.0), 1.0)
    for (low_charge, low_volts), (high_charge, high_volts) in zip(CELL_CURVE, CELL_CURVE[1:]):
        if charge <= high_charge:
            reach = (charge - low_charge) / (high_charge - low_charge)
            return low_volts + reach * (high_volts - low_volts)
    return CELL_CURVE[-1][1]


def draw_watts(water_speed: float, headwind: float, idle_watts: float) -> float:
    """Electrical power the boat draws at a speed through the water, against a headwind.

    The wind term is this service's own, because SITL puts no wind force on a motorboat hull: a
    boat punching into a breeze would otherwise spend nothing extra on it. A tailwind subtracts,
    and the electronics draw their share whether the vehicle is moving or not.
    """
    hull = HULL_WATTS * math.pow(water_speed, HULL_EXPONENT)
    wind = WINDAGE_WATTS * headwind * abs(headwind) * water_speed
    return idle_watts + max(0.0, hull + wind)


def _flow_from(bearing_deg: float, speed: float) -> Tuple[float, float]:
    """Velocity of air or water that comes *from* a bearing, north and east.

    Both SIM_WIND_DIR and SIM_TIDE_DIR name where the flow comes from, so it travels the
    opposite way.
    """
    angle = math.radians(bearing_deg)
    return (-speed * math.cos(angle), -speed * math.sin(angle))


def conditions(
    velocity: Tuple[float, float],
    heading_deg: float,
    ambient: Mapping[str, float],
) -> Tuple[float, float]:
    """Speed through the water and apparent headwind, from the vehicle's motion over ground.

    ``ambient`` holds the wind and tide by their ``Environment`` field names, and anything it
    leaves out is calm. A stream shows up as water moving under the hull: holding 1.5 m/s over
    the ground against half a metre of current costs what 2 m/s costs, since half of it is spent
    standing still. The headwind is the apparent wind along the hull, so a following breeze comes
    back negative.
    """
    tide = _flow_from(ambient.get("tide_direction", 0.0), ambient.get("tide_speed", 0.0))
    air = _flow_from(ambient.get("wind_direction", 0.0), ambient.get("wind_speed", 0.0))
    water_speed = math.hypot(velocity[0] - tide[0], velocity[1] - tide[1])
    heading = math.radians(heading_deg)
    headwind = (velocity[0] - air[0]) * math.cos(heading) + (velocity[1] - air[1]) * math.sin(heading)
    return water_speed, headwind


def capacity_mah(pack: BatteryPack) -> float:
    return pack.packs * pack.capacity_ah * 1000.0


def _calibration(pack: BatteryPack) -> Dict[str, float]:
    return {**CALIBRATION, "BATT_CAPACITY": capacity_mah(pack)}


async def _write(name: str, value: float, step: float) -> None:
    """Write a driven parameter, skipping a value that has barely moved.

    Unconfirmed on purpose: a reading is only ever as good as the next second's, and a dropped
    write costs one tick of an amperage that is about to be sent again anyway. Reading each one
    back would instead spend the parameter channel the apply job and the panels share.
    """
    previous = _written.get(name)
    if previous is not None and abs(previous - value) < step:
        return
    await mavlink.set_param(name, value)
    _written[name] = value


async def _velocity_and_heading() -> Tuple[Tuple[float, float], float]:
    """The vehicle's ground velocity in m/s north and east, and where its bow points.

    A vehicle that reports no heading (no compass yet, or none at all) is taken to point where
    it is going, which is true of a boat under way and harmless when it is not moving.
    """
    message = (await mavlink.read_message("GLOBAL_POSITION_INT") or {}).get("message") or {}
    north = float(message.get("vx") or 0) / 100.0
    east = float(message.get("vy") or 0) / 100.0
    raw = message.get("hdg")
    if isinstance(raw, (int, float)) and raw != 65535:
        return (north, east), float(raw) / 100.0
    return (north, east), math.degrees(math.atan2(east, north))


async def _consumed_mah() -> Optional[float]:
    """Charge the autopilot has counted as spent, or None when it does not report any."""
    message = (await mavlink.read_message("BATTERY_STATUS") or {}).get("message") or {}
    consumed = message.get("current_consumed")
    return float(consumed) if isinstance(consumed, (int, float)) else None


async def _read_ambient() -> Dict[str, float]:
    values: Dict[str, float] = {}
    for field in ("wind_speed", "wind_direction", "tide_speed", "tide_direction"):
        value = await mavlink.get_param(ENVIRONMENT_PARAM_MAP[field], timeout=AMBIENT_READ_TIMEOUT)
        if value is not None:
            values[field] = value
    return values


async def _assert_calibration(pack: BatteryPack) -> None:
    """Point the monitor back at the pack, after anything that may have moved it."""
    _written.clear()
    for name, value in _calibration(pack).items():
        await mavlink.set_param(name, value)


async def _tick(pack: BatteryPack, ambient: Dict[str, float], tick: int) -> None:
    """One reading: what the pack is spending, and how far down that has left it."""
    global _charging, _reading

    if tick % AMBIENT_TICKS == 0:
        # A read that fails leaves the conditions as they were, which is nearer the truth than
        # a calm sea nobody asked for.
        ambient.update(await _read_ambient())
    if tick % REASSERT_TICKS == 0:
        await _assert_calibration(pack)

    consumed = await _consumed_mah() or 0.0
    charge = min(max(1.0 - consumed / capacity_mah(pack), 0.0), 1.0)
    voltage = pack.cells * cell_voltage(charge)

    if _charging and consumed <= 0.0:
        _charging = False
    if _charging:
        # The last tick charges only what is still missing, so a pack finishes full rather than
        # overfilled: the autopilot counts charge spent and would carry a negative count.
        tops_up = consumed / 1000.0 * 3600.0 / TICK_SECONDS
        water_speed, headwind, watts = 0.0, 0.0, 0.0
        current = -min(CHARGE_AMPS, tops_up)
    else:
        velocity, heading = await _velocity_and_heading()
        water_speed, headwind = conditions(velocity, heading, ambient)
        watts = draw_watts(water_speed, headwind, pack.idle_watts)
        current = watts / voltage

    await _write("SIM_BATT_VOLTAGE", voltage, VOLTAGE_STEP)
    await _write("BATT_AMP_OFFSET", -current / AMP_PER_VOLT, CURRENT_STEP / AMP_PER_VOLT)
    _reading = PowerReading(
        watts=watts,
        current=current,
        voltage=voltage,
        charge=charge * 100.0,
        consumed_mah=consumed,
        water_speed=water_speed,
        headwind=headwind,
        charging=_charging,
    )


async def _run(pack: BatteryPack) -> None:
    global _reading

    ambient: Dict[str, float] = {}
    tick, driving = 0, True
    while True:
        try:
            if tick % VEHICLE_TICKS == 0:
                aboard = await autopilot.get_vehicle_type()
                # A vehicle that is not saying, because it is booting, is left as it was.
                wanted = driving if aboard is None else aboard == BOAT
                if wanted != driving:
                    driving = wanted
                    if driving:
                        await _assert_calibration(pack)
                    else:
                        _reading = None
                        await mavlink.set_params_verified(SITL_DEFAULTS, attempts=2)
            if driving:
                await _tick(pack, ambient, tick)
        except Exception as error:  # noqa: BLE001 - a missed reading is not worth ending the loop over
            logger.warning(f"Simulated battery reading failed: {error}")
        tick += 1
        await asyncio.sleep(TICK_SECONDS)


def _load() -> BatteryPack:
    try:
        return BatteryPack(**json.loads(POWER_PACK_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return BatteryPack()
    except Exception as error:  # noqa: BLE001 - an unreadable file is an unconfigured pack
        logger.warning(f"Ignoring invalid battery pack file {POWER_PACK_FILE}: {error}")
        return BatteryPack()


def _store(wanted: BatteryPack) -> None:
    POWER_PACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    POWER_PACK_FILE.write_text(wanted.json(indent=2), encoding="utf-8")


def _configured() -> BatteryPack:
    """The pack as configured, read from disk the first time it is asked for."""
    global _pack
    if _pack is None:
        _pack = _load()
    return _pack


def reading() -> Optional[PowerReading]:
    """The last reading the loop produced, or None when nothing is being simulated."""
    return _reading if _task is not None and not _task.done() else None


def state() -> PowerSupply:
    """The configured pack and what it reads now, which is what a panel shows."""
    return PowerSupply(pack=_configured(), reading=reading())


async def _start(wanted: BatteryPack) -> None:
    global _task

    applied, unverified = await mavlink.set_params_verified(_calibration(wanted), attempts=2)
    missing = [name for name in ESSENTIAL if name not in applied]
    if missing:
        raise RuntimeError(
            f"The autopilot did not take {', '.join(missing)}, so the simulated pack cannot be reported."
        )
    if unverified:
        logger.warning(f"Simulated pack left {', '.join(unverified)} unconfirmed")
    _written.clear()
    _task = asyncio.create_task(_run(wanted))


async def _stop_task() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None


async def apply(wanted: BatteryPack) -> None:
    """Store the pack and make the vehicle report it, or hand the simulator its own back.

    Restarting the loop on every change keeps one pack being simulated at a time and lets the
    new capacity reach the autopilot before the next reading is written against it.
    """
    global _pack, _charging, _reading

    await _stop_task()
    _pack = wanted
    _store(wanted)
    _charging = False

    if wanted.enabled:
        await _start(wanted)
        return

    _reading = None
    # Confirmed, unlike the readings: a restore that goes missing leaves the vehicle reporting
    # the last amperage this service wrote, with nothing left running to move it again.
    _, unverified = await mavlink.set_params_verified(SITL_DEFAULTS, attempts=2)
    if unverified:
        logger.warning(f"The simulator's own battery is not fully back: {', '.join(unverified)} unconfirmed")


async def recharge() -> float:
    """Put the charge back by charging: the loop draws a charger's current until the pack is full.

    Returns how many seconds of simulated time that takes, which is what a caller can tell the
    user; SIM_SPEEDUP buys the rest.
    """
    global _charging

    spent = reading()
    if spent is None:
        raise RuntimeError("There is no simulated pack to charge.")
    _charging = True
    return max(0.0, spent.consumed_mah) / 1000.0 / CHARGE_AMPS * 3600.0


async def resume() -> None:
    """Pick the stored pack back up when the service starts.

    The autopilot is left reporting the last amperage written to it, so a pack that was being
    simulated has to be taken up again rather than left frozen at whatever it read.
    """
    wanted = _configured()
    if not wanted.enabled:
        return
    try:
        await _start(wanted)
        logger.info(f"Simulating a {wanted.packs}x{wanted.cells}S {wanted.capacity_ah} Ah pack")
    except Exception as error:  # noqa: BLE001 - a vehicle that is not up yet must not stop the service
        logger.warning(f"Could not resume the simulated battery pack: {error}")


async def shutdown() -> None:
    """Stop driving the readings, leaving the pack installed for the next start."""
    await _stop_task()


if __name__ == "__main__":
    # The model is worth a check that runs: its terms are only correct against each other.
    assert abs(cell_voltage(1.0) - 4.15) < 1e-6 and abs(cell_voltage(0.0) - 3.0) < 1e-6
    assert abs(cell_voltage(0.5) - 3.755) < 1e-6, cell_voltage(0.5)
    assert abs(cell_voltage(-1) - 3.0) < 1e-6 and abs(cell_voltage(2) - 4.15) < 1e-6

    # A boat still in still water spends its electronics and nothing else.
    assert abs(draw_watts(0.0, 0.0, 10.0) - 10.0) < 1e-6
    # The hull curve at 1 m/s is the field-test figure, and a headwind adds to it.
    assert abs(draw_watts(1.0, 0.0, 0.0) - HULL_WATTS) < 1e-6
    assert draw_watts(1.5, 5.0, 0.0) > draw_watts(1.5, 0.0, 0.0) > draw_watts(1.5, -5.0, 0.0)
    # No amount of tailwind turns the draw into a supply.
    assert draw_watts(1.0, -40.0, 5.0) == 5.0

    # Motoring north at 1.5 m/s into a stream from the north: the water runs 0.5 m/s southward,
    # so the hull sees 2 m/s of it, and only 1 m/s with the stream behind.
    north_at_1_5 = ((1.5, 0.0), 0.0)
    assert abs(conditions(*north_at_1_5, {"tide_speed": 0.5})[0] - 2.0) < 1e-6
    assert abs(conditions(*north_at_1_5, {"tide_speed": 0.5, "tide_direction": 180.0})[0] - 1.0) < 1e-6
    # A 5 m/s wind out of the north is 6.5 m/s of apparent headwind at that speed, and a wind
    # out of the south is 3.5 m/s of tailwind.
    assert abs(conditions(*north_at_1_5, {"wind_speed": 5.0})[1] - 6.5) < 1e-6
    assert abs(conditions(*north_at_1_5, {"wind_speed": 5.0, "wind_direction": 180.0})[1] + 3.5) < 1e-6
    # A crosswind adds nothing along the hull, leaving the boat's own way through the air, and a
    # stream across the bow still has to be pushed through.
    assert abs(conditions(*north_at_1_5, {"wind_speed": 5.0, "wind_direction": 90.0})[1] - 1.5) < 1e-6
    assert abs(conditions(*north_at_1_5, {"tide_speed": 2.0, "tide_direction": 90.0})[0] - 2.5) < 1e-6

    print("power model checks pass")
