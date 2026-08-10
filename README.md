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
- **Spawn location** — pick where SITL boots on a map, then apply. See below.

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
