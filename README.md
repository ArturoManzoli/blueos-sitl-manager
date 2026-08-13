# BlueOS SITL Manager

<!-- Absolute URL because the Extensions Manager renders this file straight from raw
     githubusercontent, where a relative path would not resolve. -->
<img src="https://raw.githubusercontent.com/ArturoManzoli/blueos-sitl-manager/main/assets/extension_logo.png" alt="" width="220" align="right">

A BlueOS extension that gives SITL (Software-In-The-Loop) developers a single place to
configure their simulated vehicle: vehicle type and frame, ambient conditions (wind,
waves, current, simulation speed) and spawn location — without juggling the Autopilot
Firmware page, the Parameter Editor and MAVProxy.

> Status: early scaffold (v0.1.0). Built for development workflows with BlueOS + Cockpit.

## What it does

- **Vehicle presets** — turns SITL into a BlueBoat, BlueROV2 or BlueROV2 Heavy (plus
  generic rover, copter and plane), installing the firmware, setting the SITL frame and
  writing the vehicle's parameters. See below.
- **Vehicle & frame** — the vehicle type (Sub / Rover / Plane / Copter) and SITL frame
  selectors, which move the row to Custom because the combination is yours rather than a
  preset's. The frames offered are only the ones the chosen firmware can run, since each is
  a physics model compiled into one vehicle's binary. Nothing here reaches the vehicle until
  "Apply and restart" is pressed, and that button stays disabled while the section says what
  the vehicle already is.
- **Ambient conditions** — set ArduPilot `SIM_*` parameters (`SIM_WIND_*`, `SIM_WAVE_*`,
  `SIM_TIDE_*`, `SIM_SPEEDUP`) over MAVLink, with presets (calm pool, light chop, open
  ocean, storm) that fill the sliders for "Apply conditions" to write. See below.
- **Spawn location** — pick where SITL boots on a map, then apply. See below.

<img width="1346" height="968" alt="image" src="https://github.com/user-attachments/assets/0cfa3129-3d68-4bc5-b73c-a6638ee69524" />

## Vehicle presets

The Blue Robotics presets are composed from the parameter layers Blue Robotics publishes
in [Blueos-Parameter-Repository](https://github.com/bluerobotics/Blueos-Parameter-Repository),
vendored under `backend/sitl_manager/data/vendor`. Each vehicle is built the way that
repository composes it — shared hardware, then the vehicle, then its SITL overlay — and
where a vehicle layer and a SITL overlay disagree the SITL value wins, since that is the
one the simulator was tuned with. How the vehicle drives is the exception: control gains,
navigation speeds and turn geometry stay with the vehicle, because an overlay carries
ArduPilot's tuning for its own generic test vehicle and each set is only coherent as a
whole. A BlueBoat given the generic rover's 5 m/s while keeping the hull's 0.1 g lateral
limit can only turn at 11 deg/s, a radius of about 25 m, so it orbits waypoints instead of
reaching them.

Vehicle layers are dumps from real boards, so two families of parameters are dropped from
them rather than written. The vendor `blacklist.txt` covers per-board calibration (compass
and accelerometer offsets, device IDs), which describes the machine a dump came from rather
than the vehicle. On top of that, settings that only make sense on real hardware are
stripped: IMU orientation and position, analog pins and scaling for a power sense module
SITL simulates itself, I2C/serial buses, and per-output trims and reversals that would spin
a simulated hull in place. A SITL overlay gets neither filter, since everything in it states
what the simulator needs — including the placeholder accelerometer and compass offsets that
let a simulated vehicle pass the prearm 3D-accel check.

Outputs follow the simulator's wiring rather than the product's where the two differ.
`SIM_Rover` takes output 1 as the left motor and output 3 as the right one and derives yaw
from their difference, while a shipped BlueBoat puts the right thruster on output 1 and
reverses output 3 to suit how it is mounted. Since the reversal is one of the hardware
settings dropped above, keeping the product's order would leave the steering loop inverted
and the boat turning away from every waypoint.

What identifies the vehicle to BlueOS is the frame parameter: `FRAME_CLASS 2` makes
ArduRover report `MAV_TYPE_SURFACE_BOAT`, which is how a BlueBoat shows up as a boat
rather than a ground rover, and `FRAME_CONFIG` separates a BlueROV2 (1, vectored) from a
Heavy (2, vectored 6-DOF). These only rebuild the motor matrix on the next boot, so
applying a preset restarts the autopilot and then confirms the vehicle type it reports
over MAVLink actually matches — a BlueBoat has to come back as a Surface Boat.

Picking a preset only fills the vehicle type and frame selectors with what it describes;
"Apply and restart" is what writes any of it. A selector changed by hand moves the row to
**Custom**, which is the scratch entry: any pairing of vehicle type and frame can be tried
from it, and saving one that worked turns it into a preset of its own and hands Custom back
empty. A preset is never selected on the user's behalf — detection runs once on load, to
name the vehicle that was already there, and only ever answers with a built-in.

Applying runs as a background job because it spans a firmware install and two restarts.
The progress dialog shows a step per stage and, on the parameter stage, every parameter as
it is handled: written, unchanged (the vehicle already held the value, so nothing was
sent), not supported by the running firmware, or rejected. Re-applying a preset is
therefore nearly instant, since a parameter dump up front shows almost everything is
already correct.

Parameters are the only stage that knows how much is left. A firmware download or a restart
takes as long as it takes, so those run an indeterminate bar and report the seconds spent and
what they are still missing rather than a fraction that would sit still. The frame rebuild
brings SITL up on a different frame and so answers slower than a plain reboot, which is why it
waits a minute longer than `SITL_VEHICLE_READY_TIMEOUT` (override with
`SITL_REBUILD_READY_TIMEOUT`). In practice a restart is detected within a few seconds, well
inside either budget.

An autopilot counts as back when two things hold: its heartbeat count is moving, and it answers
a parameter read. The heartbeat has to be moving rather than merely present, because mavlink2rest
keeps serving the last one it saw after the vehicle goes away. The parameter read asks for index
0 instead of a name, since ArduPilot renames parameters between releases — 4.6 turned
`SYSID_THISMAV` into `MAV_SYSID` — and a name the running firmware does not know is never
answered, which is indistinguishable from an autopilot that never came back.

A failure stops the job at the stage that caused it and offers two ways on, both acting on
that stage alone rather than restarting the sequence: **Retry step** runs it again, and
**Skip step** abandons it and continues with the rest. Skipping is worth having because the
work already done still stands — a rebuild restart the simulator is slow to answer leaves the
parameters written either way — so the job can be taken to the end and the vehicle checked.
Skipped stages are named in the summary, since a skipped rebuild can mean the motor matrix is
not live yet.

## Ambient conditions

Wind, waves, current and simulation speed are plain `SIM_*` parameters, so applying them
needs no restart. Each value is read back after it is written and written again if it did
not take: a `PARAM_SET` is unacknowledged, and a burst of them can be dropped in part,
which used to leave the simulator running half a preset while the extension reported
success. Anything that still refuses to stick is named in the snackbar.

Two things decide whether waves and current actually move the vehicle, and neither is ours
to change:

- **The vehicle must be armed.** ArduPilot skips both while disarmed so the gyros can
  initialise on a still platform, so a boat sitting on the surface stays flat and stays put
  no matter what is set. Arm it and the water starts working.
- **The frame must be a boat.** Both live in ArduPilot's sailboat model, which backs the
  `motorboat*` and `sailboat*` frames only.

Wind is just as particular, because the frame picks the simulation model:

- `sailboat*` sails on it, and takes waves and current as well.
- `motorboat*` is that same model with the sail area zeroed, so wind reaches its simulated
  wind vane and never the hull.
- `vectored*` (ArduSub) has no air around it, so ArduPilot reuses the wind vector as the water
  the hull drags through: on a sub, wind *is* the current.
- `rover*` and `balancebot` drive on dry land and are deaf to all of it.
- Everything else flies, and takes wind but no water.

Every slider stays in place whatever the frame; the ones the running model would ignore are
greyed out rather than left as silent dead controls, and a badge above them opens into the
reason when it is clicked.

One catch applies to everything that stays at or below the surface: `SIM_WIND_T` defaults to a
square-law profile that scales wind by height above ground, which leaves none of it where a
boat, rover or sub lives. The **Altitude profile** selector exposes it, the built-in presets
pin it to *None* so a preset that promises wind delivers it, and the panel warns when a profile
is set that would scale the wind away on a frame that never climbs.

Wave mode picks how much of the motion is simulated: roll and pitch only, or those plus
heave (the vertical rise and fall). Both direction sliders, wind and current, say where the
flow *comes from*, matching ArduPilot's own convention. Vertical angle tilts the wind out of
the horizontal (90° is a pure updraft), and variation time is how long a change of wind takes
to arrive.

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

Locations are managed exactly like vehicle presets, described below, except that loading one
only fills the coordinates in: nothing is written to the vehicle until you press **Apply and
restart**.

## Managing profiles

Both preset rows work the same way. The three-dots menu beside a row acts on what is running
or typed in — save it as a preset, export it, import a file — while holding or right-clicking
a preset acts on that preset alone: **reload** it, **save** the current state over it, **rename**
it, **export** it, or **delete** it.

The presets the extension ships with can be edited but never lost. Saving over one stores your
version alongside the shipped definition and shadows it, and the menu then offers **Revert to
built-in** in place of delete, which throws your version away and brings the original back.
Renaming one leaves it where it is and saves a copy under the new name, for the same reason.
Only presets you added yourself can be deleted outright.

A row holds nine presets, built-ins included, which is what fits before the buttons stop being
readable. Past that the backend refuses a save or an import and says so, and the menu items
that would add one are greyed out. Long names ellipsize once the row grows wide, so a full row
still fits without pushing the panel around.

Saved presets are JSON files under the extension's persistent volume — `custom_presets` for
vehicles, `custom_locations` for spawn points — so they survive extension updates and can be
copied between vehicles by hand as well as through import and export.

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
