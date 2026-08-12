import os
from pathlib import Path

SERVICE_NAME = "sitl-manager"

# Port the backend serves on inside the container. The Dockerfile exposes 80 and the
# extension `permissions` label maps it to a free host port.
PORT = int(os.environ.get("SITL_MANAGER_PORT", "80"))

# BlueOS services are reached through the host nginx reverse-proxy. From inside an
# extension container that is `host.docker.internal` (requires the ExtraHosts entry in
# the `permissions` label). Overridable for local development against a remote vehicle.
BLUEOS_HOST = os.environ.get("BLUEOS_HOST", "http://host.docker.internal").rstrip("/")
MAVLINK2REST_URL = f"{BLUEOS_HOST}/mavlink2rest"
ARDUPILOT_MANAGER_URL = f"{BLUEOS_HOST}/ardupilot-manager/v1.0"

# ArduPilot vehicle MAVLink system id. The autopilot defaults to 1 on BlueOS.
DEFAULT_SYSTEM_ID = int(os.environ.get("SITL_SYSTEM_ID", "1"))

# Built frontend assets, copied here by the Dockerfile.
STATIC_DIR = Path(os.environ.get("SITL_STATIC_DIR", str(Path(__file__).resolve().parent.parent / "static")))

# Where user-saved and imported vehicle presets are stored as JSON. Defaults to a folder
# next to the backend for local development; the Dockerfile points it at a bind-mounted
# path so presets survive extension updates on a real BlueOS install.
CUSTOM_PRESETS_DIR = Path(
    os.environ.get("SITL_CUSTOM_PRESETS_DIR", str(Path(__file__).resolve().parent / "data" / "custom_presets"))
)

# The spawn location BlueOS ships as SIM_OPOS_* defaults (Florianópolis, Brazil). Stored
# parameter values take precedence over those defaults, which is what lets the location
# panel move the spawn point. Also used as a fallback when a parameter cannot be read.
DEFAULT_HOME_LATITUDE = -27.563
DEFAULT_HOME_LONGITUDE = -48.459
DEFAULT_HOME_ALTITUDE = 0.0
DEFAULT_HOME_HEADING = 270.0

# Shared aiohttp timeout, in seconds, for calls to BlueOS services.
HTTP_TIMEOUT = float(os.environ.get("SITL_HTTP_TIMEOUT", "10"))

# How long to wait for the autopilot to come back online after a restart or firmware
# install before giving up on applying a vehicle preset's parameters.
VEHICLE_READY_TIMEOUT = float(os.environ.get("SITL_VEHICLE_READY_TIMEOUT", "120"))

# Installing firmware downloads and unpacks a SITL binary, which takes far longer than a
# normal API call; it needs its own timeout so it is not killed by HTTP_TIMEOUT.
FIRMWARE_INSTALL_TIMEOUT = float(os.environ.get("SITL_FIRMWARE_INSTALL_TIMEOUT", "300"))

# Listing the builds for a vehicle sends ArduPilot Manager to ArduPilot's firmware index
# over the internet, which measured 14 to 41 seconds from a Raspberry Pi. Generous enough to
# survive a slow link, since giving up here fails the whole vehicle change.
FIRMWARE_LIST_TIMEOUT = float(os.environ.get("SITL_FIRMWARE_LIST_TIMEOUT", "120"))

# How long to wait, after the autopilot restarts, for the simulated GPS to report a fix at
# the requested spawn location before reporting that the move could not be confirmed.
SPAWN_VERIFY_TIMEOUT = float(os.environ.get("SITL_SPAWN_VERIFY_TIMEOUT", "30"))

# How far the vehicle may come up from the requested spawn point and still count as
# having moved there, in meters. Wide enough to absorb GPS noise, tight enough to catch a
# vehicle that ignored the request and booted at the BlueOS default instead.
SPAWN_VERIFY_RADIUS = float(os.environ.get("SITL_SPAWN_VERIFY_RADIUS", "1000"))
