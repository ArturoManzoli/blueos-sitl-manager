# BlueOS SITL Manager

A BlueOS extension that gives SITL (Software-In-The-Loop) developers a single place to
configure their simulated vehicle: vehicle type and frame, ambient conditions (wind,
waves, current, simulation speed) and spawn location — without juggling the Autopilot
Firmware page, the Parameter Editor and MAVProxy.

> Status: early scaffold (v0.1.0). Built for development workflows with BlueOS + Cockpit.

## What it does

- **Vehicle & frame** — switch the SITL vehicle type (Sub / Rover / Plane / Copter) and
  frame (`vectored`, `motorboat`, `sailboat`, …) via the ArduPilot Manager API, with an
  optional autopilot restart.
- **Ambient conditions** — set ArduPilot `SIM_*` parameters (`SIM_WIND_*`, `SIM_WAVE_*`,
  `SIM_TIDE_*`, `SIM_SPEEDUP`) over MAVLink, with one-click presets (calm pool, light
  chop, open ocean, storm).
- **Location** — relocate the running vehicle after boot. See the note below.

## The location caveat (read this)

BlueOS always starts SITL at a hardcoded home (Florianópolis, Brazil) because ArduPilot
Manager passes a fixed `--home` to the SITL binary. That argument wins over the
`SIM_OPOS_*` parameters, so there is no clean, no-core-change way to change the *spawn*
point.

This extension therefore takes the honest approach:

1. **Default ("Apply location")** — moves the EKF origin via `SET_GPS_GLOBAL_ORIGIN`
   (plus `ORIGIN_LAT`/`ORIGIN_LON`) and, by default, disables the simulated GPS so the
   relocation actually sticks on the map. This is the same mechanism BlueOS itself uses
   in the compass coordinate detector.
2. **True teleport (advanced)** — a bundled Lua `sim:set_pose` helper that repositions
   the simulated vehicle while keeping GPS. It requires enabling scripting
   (`SCR_ENABLE = 1`) and dropping the script into the autopilot's `scripts/` folder.
   Open it from the Location panel → "True teleport (Lua)".

## Architecture

```
Vue 3 + Vuetify 3 frontend  ──>  FastAPI backend  ──>  host.docker.internal
                                                        ├── /mavlink2rest      (SIM_* params, origin)
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
