from pathlib import Path
from typing import Dict, List, Tuple, TypeVar

from sitl_manager.models import (
    Environment,
    EnvironmentPreset,
    Location,
    LocationPreset,
    NamedPreset,
    Vehicle,
    VehiclePreset,
)
from sitl_manager.settings import (
    DEFAULT_HOME_ALTITUDE,
    DEFAULT_HOME_HEADING,
    DEFAULT_HOME_LATITUDE,
    DEFAULT_HOME_LONGITUDE,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
VENDOR_DIR = DATA_DIR / "vendor"

# Parameter families owned by the ambient-conditions and location features. They are
# stripped from vehicle presets so applying a preset never clobbers the simulated
# environment (wind/waves/tide) or the spawn location the user set.
PRESET_EXCLUDED_PREFIXES: Tuple[str, ...] = ("SIM_",)

# Per-board calibration and identity values, which describe the machine a parameter dump
# was taken from rather than the vehicle it configures. Copied verbatim from the vendor
# repository so presets stay in step with what Blue Robotics refuses to transfer.
#
# Applied to vehicle layers only. A SITL layer lists the same accelerometer and compass
# offsets on purpose, as placeholder values that let the simulated vehicle pass the prearm
# 3D-accel check, so filtering them there leaves the vehicle permanently unarmable.
BLACKLIST: Tuple[str, ...] = tuple(
    line.strip() for line in (VENDOR_DIR / "blacklist.txt").read_text().splitlines() if line.strip()
)

# Settings that describe real hardware and would misconfigure or break SITL: IMU
# orientation and position (the simulated IMU sits level at the origin), analog pins and
# scaling for a power sense module SITL simulates itself, I2C/serial buses and scripting
# storage that do not exist, and per-output wiring trims that would reverse a simulated
# thruster. These are dropped from vehicle layers only — a SITL layer that sets one of
# them is stating the value the simulator wants, so it is honoured.
HARDWARE_PARAMS: Tuple[str, ...] = (
    "AHRS_ORIENTATION",
    "BARO_EXT_BUS",
    "BATT_AMP_OFFSET",
    "BATT_AMP_PERVLT",
    "BATT_CURR_PIN",
    "BATT_VOLT_MULT",
    "BATT_VOLT_PIN",
    "EK3_IMU_MASK",
    "GPS_AUTO_SWITCH",
    "GPS_NAVFILTER",
    "GPS_SAVE_CFG",
    "RC_OPTIONS",
    "WNDVN_TYPE",
)
HARDWARE_PREFIXES: Tuple[str, ...] = (
    "BRD_",
    "CAN_",
    "EAHRS_",
    "GPS1_COM",
    "GPS1_POS",
    "INS_POS",
    "MSP_",
    "RELAY",
    "SCR_",
    "SERIAL",
)
HARDWARE_SUFFIXES: Tuple[str, ...] = ("_REVERSED", "_TRIM")

# How the vehicle drives: control gains, navigation speeds and turn geometry. A vehicle
# layer that states one of these keeps it, because a SITL overlay carries ArduPilot's
# tuning for its own generic test vehicle and the two sets are only coherent as a whole.
# Half of each produces a hull that cannot turn tightly enough to fly a mission: a
# BlueBoat given the generic rover's WP_SPEED of 5 m/s while keeping its own
# ATC_TURN_MAX_G of 0.1 g is held to 11 deg/s, a turn radius of about 25 m, so it orbits
# every waypoint instead of reaching it.
DYNAMICS_PARAMS: Tuple[str, ...] = (
    "CRUISE_SPEED",
    "CRUISE_THROTTLE",
    "LOIT_RADIUS",
    "RTL_SPEED",
    "SPEED_MAX",
    "TURN_RADIUS",
)
DYNAMICS_PREFIXES: Tuple[str, ...] = ("ACRO_", "ATC_", "MOT_", "WP_")


# ArduPilot reads an accelerometer whose offsets are all zero and whose scales are all one as
# uncalibrated and refuses to arm on it, which is why every SITL parameter file ArduPilot
# ships carries these placeholders. A firmware install starts the vehicle from empty parameter
# storage, so a configuration that brings no calibration of its own is written these. Only the
# two instances SITL registers are covered, and deliberately: the same check also fails on a
# calibration that exists for an accelerometer the vehicle does not have, so writing a third
# instance leaves the vehicle exactly as unarmable as writing none.
SITL_ACCEL_CALIBRATION: Dict[str, float] = {
    f"INS_ACC{instance}{quantity}_{axis}": value
    for instance in ("", "2")
    for quantity, value in (("OFFS", 0.001), ("SCAL", 1.001))
    for axis in ("X", "Y", "Z")
}


def _is_hardware_param(name: str) -> bool:
    return name in HARDWARE_PARAMS or name.startswith(HARDWARE_PREFIXES) or name.endswith(HARDWARE_SUFFIXES)


def _is_dynamics_param(name: str) -> bool:
    return name in DYNAMICS_PARAMS or name.startswith(DYNAMICS_PREFIXES)


def load_params(path: Path, vehicle_layer: bool = True) -> Dict[str, float]:
    """Parse an ArduPilot parameter file into a name->value map.

    Accepts the shapes the vendor repository uses: ``NAME VALUE``, ``NAME: VALUE,`` and
    ``NAME, VALUE``, with ``#`` or ``//`` comments. ``%include`` directives are ignored
    because callers compose the layers explicitly, which is what makes the precedence
    between a vehicle and its SITL overlay reviewable.

    A vehicle layer is a dump from a real board, so the blacklisted calibration and the
    hardware settings in it are dropped. A SITL layer is a statement of what the simulator
    needs and is taken as written.
    """
    params: Dict[str, float] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].split("//", 1)[0].strip()
        if not line or line.startswith("%include"):
            continue
        parts = line.replace(":", " ").replace(",", " ").split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if name.startswith(PRESET_EXCLUDED_PREFIXES):
            continue
        if vehicle_layer and (any(entry in name for entry in BLACKLIST) or _is_hardware_param(name)):
            continue
        try:
            params[name] = float(parts[1])
        except ValueError:
            continue
    return params


def compose_params(vehicle_layers: List[Path], sitl_layers: List[Path]) -> Dict[str, float]:
    """Merge parameter layers into one set, with the SITL layers applied last.

    Where both define a parameter the SITL value wins, since it is the one the simulator
    was tuned with, except for the driving tune in ``DYNAMICS_PARAMS``, which stays with
    the vehicle that was tuned around it.
    """
    params: Dict[str, float] = {}
    for path in vehicle_layers:
        params.update(load_params(path))
    for path in sitl_layers:
        for name, value in load_params(path, vehicle_layer=False).items():
            if name in params and _is_dynamics_param(name):
                continue
            params[name] = value
    return params


# Maps each Environment field to its ArduPilot SIM_* parameter name.
ENVIRONMENT_PARAM_MAP: Dict[str, str] = {
    "wind_speed": "SIM_WIND_SPD",
    "wind_direction": "SIM_WIND_DIR",
    "wind_turbulence": "SIM_WIND_TURB",
    "wind_elevation": "SIM_WIND_DIR_Z",
    "wind_variation": "SIM_WIND_TC",
    "wind_profile": "SIM_WIND_T",
    "wind_full_altitude": "SIM_WIND_T_ALT",
    "wave_enable": "SIM_WAVE_ENABLE",
    "wave_amplitude": "SIM_WAVE_AMP",
    "wave_length": "SIM_WAVE_LENGTH",
    "wave_direction": "SIM_WAVE_DIR",
    "wave_speed": "SIM_WAVE_SPEED",
    "tide_direction": "SIM_TIDE_DIR",
    "tide_speed": "SIM_TIDE_SPEED",
    "speedup": "SIM_SPEEDUP",
}

# ArduPilot defaults SIM_WIND_T to its square law, which scales wind by the height above ground
# and so leaves none of it at the surface. Every preset therefore pins the profile off: a preset
# that names a wind should deliver it whatever the vehicle, and a boat or rover never climbs.
NO_WIND_PROFILE = 1

ENVIRONMENT_PRESETS: List[EnvironmentPreset] = [
    EnvironmentPreset(
        name="Calm pool",
        description="No wind, no waves, no current. A clean baseline for development.",
        environment=Environment(
            wind_speed=0,
            wind_turbulence=0,
            wind_elevation=0,
            wind_profile=NO_WIND_PROFILE,
            wave_enable=0,
            wave_amplitude=0,
            tide_speed=0,
            speedup=1,
        ),
    ),
    EnvironmentPreset(
        name="Light chop",
        description="A gentle breeze with small waves, typical of a sheltered harbour.",
        environment=Environment(
            wind_speed=3,
            wind_direction=180,
            wind_turbulence=0.1,
            wind_profile=NO_WIND_PROFILE,
            wave_enable=1,
            wave_amplitude=0.2,
            wave_length=8,
            wave_speed=0.5,
            tide_speed=0.2,
            tide_direction=90,
            speedup=1,
        ),
    ),
    EnvironmentPreset(
        name="Open ocean",
        description="Moderate wind, rolling swell and a steady current.",
        environment=Environment(
            wind_speed=8,
            wind_direction=210,
            wind_turbulence=0.3,
            wind_profile=NO_WIND_PROFILE,
            wave_enable=2,
            wave_amplitude=0.8,
            wave_length=20,
            wave_speed=1.5,
            tide_speed=0.6,
            tide_direction=120,
            speedup=1,
        ),
    ),
    EnvironmentPreset(
        name="Storm",
        description="High wind and turbulence with large waves. Stress-test failsafes.",
        environment=Environment(
            wind_speed=18,
            wind_direction=240,
            wind_turbulence=0.8,
            wind_profile=NO_WIND_PROFILE,
            wave_enable=2,
            wave_amplitude=2.0,
            wave_length=30,
            wave_speed=3.0,
            tide_speed=1.2,
            tide_direction=150,
            speedup=1,
        ),
    ),
]

# Maps each Location field to its ArduPilot SIM_OPOS_* parameter name. Since BlueOS
# stopped forcing --home on the SITL binary (bluerobotics/BlueOS#3986) these parameters
# decide where the vehicle spawns, and stored values win over the defaults BlueOS ships.
LOCATION_PARAM_MAP: Dict[str, str] = {
    "latitude": "SIM_OPOS_LAT",
    "longitude": "SIM_OPOS_LNG",
    "altitude": "SIM_OPOS_ALT",
    "heading": "SIM_OPOS_HDG",
}

# Where a vehicle spawns when nothing says otherwise: the location BlueOS ships. Stood in
# for a parameter that cannot be read, and for the zeroes a firmware install leaves behind.
DEFAULT_SPAWN_BY_FIELD: Dict[str, float] = {
    "latitude": DEFAULT_HOME_LATITUDE,
    "longitude": DEFAULT_HOME_LONGITUDE,
    "altitude": DEFAULT_HOME_ALTITUDE,
    "heading": DEFAULT_HOME_HEADING,
}

LOCATION_PRESETS: List[LocationPreset] = [
    LocationPreset(
        name="Florianópolis",
        location=Location(
            latitude=DEFAULT_HOME_LATITUDE,
            longitude=DEFAULT_HOME_LONGITUDE,
            altitude=DEFAULT_HOME_ALTITUDE,
            heading=DEFAULT_HOME_HEADING,
        ),
    ),
    LocationPreset(
        name="AltaSea",
        location=Location(latitude=33.719589, longitude=-118.273179, heading=0),
    ),
    LocationPreset(
        name="Kawaihae",
        location=Location(latitude=20.027301, longitude=-155.830262, heading=0),
    ),
    LocationPreset(
        name="Zandvoort",
        location=Location(latitude=52.391492, longitude=4.523203, heading=0),
    ),
]

THROTTLE_LEFT, THROTTLE_RIGHT = 73, 74
GROUND_STEERING, THROTTLE = 26, 70

# What each SITL frame makes of servo outputs 1 and 3. A skid frame reads them as the left and
# right motors and takes yaw from their difference, a steered one as ground steering and
# throttle, so a vehicle whose outputs are set for the other pairing drives in circles instead
# of holding a heading. Sailboats are left out, since their outputs carry a mainsail too and
# there is no single pairing to state.
FRAME_OUTPUTS: Dict[str, Dict[str, int]] = {
    "motorboat-skid": {"SERVO1_FUNCTION": THROTTLE_LEFT, "SERVO3_FUNCTION": THROTTLE_RIGHT},
    "rover-skid": {"SERVO1_FUNCTION": THROTTLE_LEFT, "SERVO3_FUNCTION": THROTTLE_RIGHT},
    "motorboat": {"SERVO1_FUNCTION": GROUND_STEERING, "SERVO3_FUNCTION": THROTTLE},
    "rover": {"SERVO1_FUNCTION": GROUND_STEERING, "SERVO3_FUNCTION": THROTTLE},
}

# The oldest firmware whose simulation model steers a frame at all, for the frames that were
# broken until a known fix. ArduPilot's skid-steered boats yawed only at exactly zero speed,
# which a boat in water never reaches, and otherwise in proportion to speed and with its sign,
# so a waypoint turn rotated whichever way the hull was drifting; the fix landed on master after
# 4.7 branched. A frame named here is installed with a build new enough to run it, which is the
# development build until the version below is released as stable, and the entry can go then.
FRAME_MINIMUM_FIRMWARE: Dict[str, str] = {"motorboat-skid": "4.8.0"}

# The Blue Robotics presets are composed from the parameter layers Blue Robotics ships in
# bluerobotics/Blueos-Parameter-Repository, vendored under data/vendor. Each vehicle is
# built the way that repository composes it — shared hardware, then the vehicle, then its
# SITL overlay — so the simulated vehicle is configured like the real product wherever the
# simulator does not need something else. The SITL --frame supplies the hydrodynamics.
BLUEBOAT_LAYERS = ([DATA_DIR / "blueboat.params"], [VENDOR_DIR / "rover_sitl.params"])

# Two ways the simulated hull is not the real one. Both describe the thrusters rather than the
# driving tune, so the simulator is told what it actually has and the product's gains still fly it.
SITL_HULL_OVERRIDES: Dict[str, float] = {
    # A T200 pushes about 1.6 times harder forward than in reverse, and MOT_THST_ASYM tells the skid
    # mixer to boost whichever motor is reversing so that the pair still balances. Simulated thrust
    # is linear both ways, so on the reversing side that boost is thrust the hull really gets: a
    # pivot commanded as -100% and +62.5% leaves 37.5% of full thrust pushing astern, and the boat
    # backs out of every waypoint it pivots around, about 11 m off a 30 m leg before it recovers.
    "MOT_THST_ASYM": 1.0,
    # The marine model yaws a skid boat at 0.44 rad/s per unit of steering output, the two throttles
    # spanning 1.6 of the model's units and each unit turning it at pi * 5 deg/s, where the real
    # hull's thrusters are several times stronger. ATC_STR_RAT_FF is the inverse of that gain, so
    # the shipped 0.8 leaves the simulated boat pivoting at 9 deg/s of the 15 WP_PIVOT_RATE asks
    # for, with no integrator to close the gap: 11 s a corner instead of 6, and a metre of extra
    # overshoot leaving it. Feeding forward the gain the simulated hull has pivots at the rate the
    # product asks for.
    "ATC_STR_RAT_FF": 2.3,
}
BLUEROV2_LAYERS = (
    [VENDOR_DIR / "sub_power_sense_module.params", VENDOR_DIR / "sub_base.params", VENDOR_DIR / "sub_standard.params"],
    [VENDOR_DIR / "sub_sitl_standard.params"],
)
BLUEROV2_HEAVY_LAYERS = (
    [VENDOR_DIR / "sub_power_sense_module.params", VENDOR_DIR / "sub_base.params", VENDOR_DIR / "sub_heavy.params"],
    [VENDOR_DIR / "sub_sitl_heavy.params"],
)

VEHICLE_PRESETS: List[VehiclePreset] = [
    VehiclePreset(
        name="BlueBoat",
        description="Blue Robotics BlueBoat — skid-steered surface vehicle (ArduRover).",
        vehicle=Vehicle.ROVER,
        # Marine hydrodynamics with differential thrust, matching the hull's two thrusters.
        frame="motorboat-skid",
        parameters={**compose_params(*BLUEBOAT_LAYERS), **SITL_HULL_OVERRIDES},
    ),
    VehiclePreset(
        name="BlueROV2",
        description="Blue Robotics BlueROV2 — 6-thruster vectored ROV (ArduSub).",
        vehicle=Vehicle.SUB,
        frame="vectored",
        parameters=compose_params(*BLUEROV2_LAYERS),
    ),
    VehiclePreset(
        name="BlueROV2 Heavy",
        description="Blue Robotics BlueROV2 Heavy — 8-thruster fully vectored 6-DOF ROV (ArduSub).",
        vehicle=Vehicle.SUB,
        frame="vectored_6dof",
        parameters=compose_params(*BLUEROV2_HEAVY_LAYERS),
    ),
    # Generic (non Blue Robotics) ArduPilot vehicles for aerial and ground SITL work.
    # FRAME_CLASS keeps each one distinct from the marine presets above: a ground rover
    # is FRAME_CLASS 1 (vs the BlueBoat's boat = 2), and the copter declares its own
    # quad airframe. ArduPlane has no FRAME_CLASS, so the plane preset relies on its
    # SITL frame plus a little cruise tuning.
    VehiclePreset(
        name="UAV",
        description="Generic ArduCopter quadrotor (X airframe) for aerial SITL development.",
        vehicle=Vehicle.COPTER,
        frame="quad",
        parameters={
            "FRAME_CLASS": 1,  # Quad
            "FRAME_TYPE": 1,  # X
        },
    ),
    VehiclePreset(
        name="Ground Rover",
        description="Generic ackermann-steered ground rover (ArduRover, non-skid).",
        vehicle=Vehicle.ROVER,
        frame="rover",
        parameters={
            "FRAME_CLASS": 1,  # Rover (ground), distinct from the BlueBoat's boat hull (2)
            "SERVO1_FUNCTION": 26,  # Ground steering — front wheels (ackermann, not skid)
            "SERVO3_FUNCTION": 70,  # Throttle
            "TURN_RADIUS": 2.0,  # Car-like minimum turning radius, metres
            "CRUISE_SPEED": 2.0,
            "WP_SPEED": 2.0,
            "ATC_SPEED_P": 0.2,
            "ATC_STR_RAT_P": 0.2,
        },
    ),
    VehiclePreset(
        name="Plane",
        description="Generic ArduPlane fixed-wing aircraft for aerial SITL development.",
        vehicle=Vehicle.PLANE,
        frame="plane",
        parameters={
            "TRIM_THROTTLE": 45,  # Cruise throttle, percent
            "THR_MAX": 100,
            "ARSPD_FBW_MIN": 9,  # Stall-safe minimum airspeed, m/s
            "ARSPD_FBW_MAX": 22,
        },
    ),
]


PresetT = TypeVar("PresetT", bound=NamedPreset)


def _merge_presets(builtin: List[PresetT], saved: List[PresetT]) -> List[PresetT]:
    """Built-ins first, in their curated order, then the ones the user added.

    A saved preset named after a built-in takes its place and keeps its slot in the row,
    tagged ``overridden`` so the UI offers to revert it rather than to delete it. Everything
    else the user saved follows, tagged as not built-in and so freely deletable.
    """
    edits = {preset.name: preset for preset in saved}
    merged = [
        edits.get(preset.name, preset).copy(update={"builtin": True, "overridden": preset.name in edits})
        for preset in builtin
    ]
    builtin_names = {preset.name for preset in builtin}
    merged.extend(
        preset.copy(update={"builtin": False, "overridden": False})
        for preset in saved
        if preset.name not in builtin_names
    )
    return merged


def all_vehicle_presets() -> List[VehiclePreset]:
    """Built-in vehicle presets, any edits to them applied, then the user's own."""
    # Imported lazily to avoid a circular import: custom_presets reads the models only.
    from sitl_manager.custom_presets import VEHICLE_STORE

    return _merge_presets(VEHICLE_PRESETS, VEHICLE_STORE.list())


def all_location_presets() -> List[LocationPreset]:
    """Built-in spawn locations, any edits to them applied, then the user's own."""
    from sitl_manager.custom_presets import LOCATION_STORE

    return _merge_presets(LOCATION_PRESETS, LOCATION_STORE.list())


def all_environment_presets() -> List[EnvironmentPreset]:
    """Built-in ambient conditions, any edits to them applied, then the user's own."""
    from sitl_manager.custom_presets import ENVIRONMENT_STORE

    return _merge_presets(ENVIRONMENT_PRESETS, ENVIRONMENT_STORE.list())
