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

# Static assets shipped with the backend (the Lua teleport helper script, icons).
ASSETS_DIR = Path(os.environ.get("SITL_ASSETS_DIR", str(Path(__file__).resolve().parent.parent / "assets")))

# Hardcoded SITL spawn used by ArduPilot Manager (Florianópolis, Brazil). The vehicle
# always boots here; the location panel relocates it afterwards over MAVLink.
DEFAULT_HOME_LATITUDE = -27.563
DEFAULT_HOME_LONGITUDE = -48.459
DEFAULT_HOME_ALTITUDE = 0.0
DEFAULT_HOME_HEADING = 270.0

# Shared aiohttp timeout, in seconds, for calls to BlueOS services.
HTTP_TIMEOUT = float(os.environ.get("SITL_HTTP_TIMEOUT", "10"))
