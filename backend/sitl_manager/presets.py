from typing import Dict, List

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
            wind_speed=3, wind_direction=180, wind_turbulence=0.1, wave_enable=1, wave_amplitude=0.2,
            wave_length=8, wave_speed=0.5, tide_speed=0.2, tide_direction=90, speedup=1,
        ),
    ),
    EnvironmentPreset(
        name="Open ocean",
        description="Moderate wind, rolling swell and a steady current.",
        environment=Environment(
            wind_speed=8, wind_direction=210, wind_turbulence=0.3, wave_enable=2, wave_amplitude=0.8,
            wave_length=20, wave_speed=1.5, tide_speed=0.6, tide_direction=120, speedup=1,
        ),
    ),
    EnvironmentPreset(
        name="Storm",
        description="High wind and turbulence with large waves. Stress-test failsafes.",
        environment=Environment(
            wind_speed=18, wind_direction=240, wind_turbulence=0.8, wave_enable=2, wave_amplitude=2.0,
            wave_length=30, wave_speed=3.0, tide_speed=1.2, tide_direction=150, speedup=1,
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

# ArduPilot servo output functions used by the marine vehicles below.
# 33..40 = Motor1..Motor8 (ArduSub), 59/60 = RCIN9/RCIN10 (BlueROV2 lights),
# 73/74 = ThrottleLeft/ThrottleRight (ArduRover skid steering).
# The SITL --frame supplies the hydrodynamics; these parameters capture the defining
# configuration (frame class/config, motor mapping, battery, basic tuning) so the
# simulated vehicle matches the real product. They are a curated baseline, not a full
# factory parameter dump, and are safe to extend.
VEHICLE_PRESETS: List[VehiclePreset] = [
    VehiclePreset(
        name="BlueBoat",
        description="Blue Robotics BlueBoat — twin-thruster skid-steered surface vehicle (ArduRover).",
        vehicle=Vehicle.ROVER,
        frame="motorboat-skid",
        parameters={
            "FRAME_CLASS": 2,  # Boat
            "SERVO1_FUNCTION": 73,  # Throttle Left
            "SERVO3_FUNCTION": 74,  # Throttle Right
            "MOT_PWM_TYPE": 0,  # Normal PWM
            "PILOT_STEER_TYPE": 1,  # Two paddles input (skid steering)
            "ATC_STR_RAT_P": 0.2,
            "ATC_STR_RAT_I": 0.2,
            "ATC_STR_RAT_D": 0.0,
            "ATC_SPEED_P": 0.2,
            "ATC_SPEED_I": 0.2,
            "CRUISE_SPEED": 2.0,
            "CRUISE_THROTTLE": 40,
            "WP_SPEED": 2.0,
            "TURN_MAX_G": 0.6,
            "BATT_MONITOR": 4,  # Analog voltage and current
            "BATT_CAPACITY": 18000,
        },
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
]
