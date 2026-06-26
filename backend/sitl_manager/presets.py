from pathlib import Path
from typing import Dict, List, Tuple

from sitl_manager.models import (
    Environment,
    EnvironmentPreset,
    Location,
    LocationPreset,
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

# Parameter families owned by the ambient-conditions and location features. They are
# stripped from vehicle presets so applying a preset never clobbers the simulated
# environment (wind/waves/tide) or the EKF origin the user set.
PRESET_EXCLUDED_PREFIXES: Tuple[str, ...] = ("SIM_",)


def load_parm_file(path: Path, exclude_prefixes: Tuple[str, ...] = PRESET_EXCLUDED_PREFIXES) -> Dict[str, float]:
    """Parse an ArduPilot ``.parm`` dump into a name->value map.

    Lines are ``NAME   VALUE`` with ``#`` comments; blank lines, comments and any
    parameter whose name starts with an excluded prefix are skipped.
    """
    params: Dict[str, float] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith(exclude_prefixes):
            continue
        try:
            params[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return params


# Maps each Environment field to its ArduPilot SIM_* parameter name.
ENVIRONMENT_PARAM_MAP: Dict[str, str] = {
    "wind_speed": "SIM_WIND_SPD",
    "wind_direction": "SIM_WIND_DIR",
    "wind_turbulence": "SIM_WIND_TURB",
    "wave_enable": "SIM_WAVE_ENABLE",
    "wave_amplitude": "SIM_WAVE_AMP",
    "wave_length": "SIM_WAVE_LENGTH",
    "wave_direction": "SIM_WAVE_DIR",
    "wave_speed": "SIM_WAVE_SPEED",
    "tide_direction": "SIM_TIDE_DIR",
    "tide_speed": "SIM_TIDE_SPEED",
    "speedup": "SIM_SPEEDUP",
}

ENVIRONMENT_PRESETS: List[EnvironmentPreset] = [
    EnvironmentPreset(
        name="Calm pool",
        description="No wind, no waves, no current. A clean baseline for development.",
        environment=Environment(
            wind_speed=0, wind_turbulence=0, wave_enable=0, wave_amplitude=0, tide_speed=0, speedup=1
        ),
    ),
    EnvironmentPreset(
        name="Light chop",
        description="A gentle breeze with small waves, typical of a sheltered harbour.",
        environment=Environment(
            wind_speed=3,
            wind_direction=180,
            wind_turbulence=0.1,
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

LOCATION_PRESETS: List[LocationPreset] = [
    LocationPreset(
        name="Florianópolis (BlueOS default)",
        location=Location(
            latitude=DEFAULT_HOME_LATITUDE,
            longitude=DEFAULT_HOME_LONGITUDE,
            altitude=DEFAULT_HOME_ALTITUDE,
            heading=DEFAULT_HOME_HEADING,
        ),
    ),
    LocationPreset(name="San Francisco Bay", location=Location(latitude=37.8199, longitude=-122.4783, heading=0)),
    LocationPreset(name="Sydney Harbour", location=Location(latitude=-33.8523, longitude=151.2108, heading=0)),
    LocationPreset(name="Equator origin", location=Location(latitude=0.0, longitude=0.0, heading=0)),
]

# ArduPilot servo output functions used by the ROV presets below.
# 33..40 = Motor1..Motor8 (ArduSub), 59/60 = RCIN9/RCIN10 (BlueROV2 lights).
# The SITL --frame supplies the hydrodynamics; the parameters capture the defining
# configuration so the simulated vehicle matches the real product. The BlueBoat set is
# the full reference dump loaded from data/blueboat.parm (minus the SIM_* family); the
# ROV sets remain a curated baseline that is safe to extend.
VEHICLE_PRESETS: List[VehiclePreset] = [
    VehiclePreset(
        name="BlueBoat",
        description="Blue Robotics BlueBoat — surface vehicle (ArduRover), full reference parameters.",
        vehicle=Vehicle.ROVER,
        frame="rover-skid",
        parameters=load_parm_file(DATA_DIR / "blueboat.parm"),
    ),
    VehiclePreset(
        name="BlueROV2",
        description="Blue Robotics BlueROV2 — 6-thruster vectored ROV (ArduSub).",
        vehicle=Vehicle.SUB,
        frame="vectored",
        parameters={
            "FRAME_CONFIG": 1,  # Vectored
            "SERVO1_FUNCTION": 33,  # Motor1
            "SERVO2_FUNCTION": 34,  # Motor2
            "SERVO3_FUNCTION": 35,  # Motor3
            "SERVO4_FUNCTION": 36,  # Motor4
            "SERVO5_FUNCTION": 37,  # Motor5
            "SERVO6_FUNCTION": 38,  # Motor6
            "SERVO9_FUNCTION": 59,  # RCIN9 — lights 1
            "SERVO10_FUNCTION": 60,  # RCIN10 — lights 2
            "BATT_MONITOR": 4,  # Analog voltage and current
            "BATT_CAPACITY": 18000,
            "BATT_VOLT_MULT": 11.0,  # Blue Robotics Power Sense Module
            "BATT_AMP_PERVLT": 37.8788,
        },
    ),
    VehiclePreset(
        name="BlueROV2 Heavy",
        description="Blue Robotics BlueROV2 Heavy — 8-thruster fully vectored 6-DOF ROV (ArduSub).",
        vehicle=Vehicle.SUB,
        frame="vectored_6dof",
        parameters={
            "FRAME_CONFIG": 2,  # Vectored 6DOF
            "SERVO1_FUNCTION": 33,  # Motor1
            "SERVO2_FUNCTION": 34,  # Motor2
            "SERVO3_FUNCTION": 35,  # Motor3
            "SERVO4_FUNCTION": 36,  # Motor4
            "SERVO5_FUNCTION": 37,  # Motor5
            "SERVO6_FUNCTION": 38,  # Motor6
            "SERVO7_FUNCTION": 39,  # Motor7
            "SERVO8_FUNCTION": 40,  # Motor8
            "SERVO9_FUNCTION": 59,  # RCIN9 — lights 1
            "SERVO10_FUNCTION": 60,  # RCIN10 — lights 2
            "BATT_MONITOR": 4,  # Analog voltage and current
            "BATT_CAPACITY": 18000,
            "BATT_VOLT_MULT": 11.0,  # Blue Robotics Power Sense Module
            "BATT_AMP_PERVLT": 37.8788,
        },
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


def is_builtin_preset_name(name: str) -> bool:
    return any(preset.name == name for preset in VEHICLE_PRESETS)


def all_vehicle_presets() -> List[VehiclePreset]:
    """Built-in presets followed by user-saved/imported ones.

    Custom presets that reuse a built-in name are ignored so the curated definitions
    always win; importing under a built-in name is rejected at the API layer.
    """
    # Imported lazily to avoid a circular import: custom_presets reads the models only.
    from sitl_manager.custom_presets import list_custom_presets

    custom = [preset for preset in list_custom_presets() if not is_builtin_preset_name(preset.name)]
    return [*VEHICLE_PRESETS, *custom]
