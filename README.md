# BlueOS SITL Manager

A BlueOS extension that gives SITL (Software-In-The-Loop) developers a single place to
configure their simulated vehicle: vehicle type and frame, ambient conditions (wind,
waves, current, simulation speed) and spawn location — without juggling the Autopilot
Firmware page, the Parameter Editor and MAVProxy.

> Status: early scaffold (v0.1.0). Built for development workflows with BlueOS + Cockpit.

## What it does

- **Vehicle presets** — one click turns SITL into a BlueBoat, BlueROV2 or BlueROV2 Heavy
  (plus generic rover, copter and plane), installing the firmware, setting the SITL frame
  and writing the vehicle's parameters. See below.
- **Vehicle & frame** — the vehicle type (Sub / Rover / Plane / Copter) and SITL frame
  selectors apply on selection, through the same job and progress dialog as a preset.
- **Ambient conditions** — set ArduPilot `SIM_*` parameters (`SIM_WIND_*`, `SIM_WAVE_*`,
  `SIM_TIDE_*`, `SIM_SPEEDUP`) over MAVLink, with one-click presets (calm pool, light
  chop, open ocean, storm).
- **Spawn location** — pick where SITL boots on a map, then apply. See below.

## Vehicle presets

The Blue Robotics presets are composed from the parameter layers Blue Robotics publishes
in [Blueos-Parameter-Repository](https://github.com/bluerobotics/Blueos-Parameter-Repository),
vendored under `backend/sitl_manager/data/vendor`. Each vehicle is built the way that
repository composes it — shared hardware, then the vehicle, then its SITL overlay — and
where a vehicle layer and a SITL overlay disagree the SITL value wins, since that is the
one the simulator was tuned with.

Two families of parameters are dropped rather than written. The vendor `blacklist.txt`
covers per-board calibration (compass and accelerometer offsets, device IDs), which
describes the machine a dump came from rather than the vehicle. On top of that, settings
that only make sense on real hardware are stripped from the vehicle layers: IMU
orientation and position, analog pins and scaling for a power sense module SITL simulates
itself, I2C/serial buses, and per-output trims and reversals that would spin a simulated
hull in place.

What identifies the vehicle to BlueOS is the frame parameter: `FRAME_CLASS 2` makes
ArduRover report `MAV_TYPE_SURFACE_BOAT`, which is how a BlueBoat shows up as a boat
rather than a ground rover, and `FRAME_CONFIG` separates a BlueROV2 (1, vectored) from a
Heavy (2, vectored 6-DOF). These only rebuild the motor matrix on the next boot, so
applying a preset restarts the autopilot and then confirms the vehicle type it reports
over MAVLink actually matches — a BlueBoat has to come back as a Surface Boat.

Applying runs as a background job because it spans a firmware install and two restarts.
The progress dialog shows a step per stage and, on the parameter stage, every parameter as
it is handled: written, unchanged (the vehicle already held the value, so nothing was
sent), not supported by the running firmware, or rejected. Re-applying a preset is
therefore nearly instant, since a parameter dump up front shows almost everything is
already correct.

## Spawn location

BlueOS used to start SITL with a fixed `--home` (Florianópolis, Brazil), which overrode
the `SIM_OPOS_*` parameters and made the spawn point impossible to change without
patching core. Since [bluerobotics/BlueOS#3986](https://github.com/bluerobotics/BlueOS/pull/3986)
that home is supplied as `SIM_OPOS_*` *defaults* instead, and stored parameter values win
over defaults — so the spawn point is now just four parameters.

The panel therefore reads `SIM_OPOS_LAT`/`LNG`/`ALT`/`HDG` to show where the vehicle is
configured to spawn, and "Apply and restart" writes them and restarts the autopilot.
ArduPilot only reads them while building the simulated vehicle, hence the restart; from
then on the vehicle boots there every time.

After the restart the backend waits for the vehicle to report a GPS fix near the
requested point. If it comes up somewhere else, your BlueOS core predates the PR above
and still forces a fixed home — the extension says so instead of silently doing nothing.

Spawn location is untouched by the vehicle presets: they strip every `SIM_` parameter, so
switching vehicle keeps your location (and your ambient conditions).

## Architecture

```
Vue 3 + Vuetify 3 frontend  ──>  FastAPI backend  ──>  host.docker.internal
                                                        ├── /mavlink2rest      (params, position)
                                                        └── /ardupilot-manager (frame, firmware, restart)
```

The backend serves both the API (under `/v1.0/`) and the built frontend, and exposes the
`/register_service` endpoint BlueOS uses to add the extension to its sidebar.

## Development

Backend (Python 3.11):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
BLUEOS_HOST=http://blueos.local SITL_MANAGER_PORT=8000 python main.py
```

Frontend (Vue 3 + Vite):

```bash
cd frontend
yarn install
yarn dev      # proxies /v1.0 to http://localhost:8000
yarn build    # outputs to dist/, copied into the image as /app/static
```

## Build & install

The image is built and published by the GitHub workflow in
`.github/workflows/deploy.yml`, which uses the
[BlueOS Extension Deployment Action](https://github.com/BlueOS-community/Deploy-BlueOS-Extension).
Configure these repository secrets/variables: `DOCKER_USERNAME`, `DOCKER_PASSWORD`,
`MY_NAME`, `MY_EMAIL`, `ORG_NAME`, `ORG_EMAIL`.

To test manually, in BlueOS → **Extensions Manager → +** and enter:

| Field | Value |
|-------|-------|
| Identifier | `<dockeruser>.sitl-manager` |
| Name | `SITL Manager` |
| Docker image | `<dockeruser>/blueos-sitl-manager` |
| Docker tag | the branch or version tag you built |
| Permissions | the contents of the `permissions` label in the `Dockerfile` |

## License

MIT — see [LICENSE](./LICENSE).
