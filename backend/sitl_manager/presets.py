from typing import Dict, List

from sitl_manager.models import Environment, EnvironmentPreset, Location, LocationPreset
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
