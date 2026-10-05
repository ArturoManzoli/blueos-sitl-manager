from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ParamType(str, Enum):
    """MAVLink parameter encodings accepted by mavlink2rest. ArduPilot stores every
    parameter as a float over the wire, so REAL32 is the safe default."""

    REAL32 = "MAV_PARAM_TYPE_REAL32"
    INT32 = "MAV_PARAM_TYPE_INT32"
    UINT8 = "MAV_PARAM_TYPE_UINT8"


class Environment(BaseModel):
    """Ambient SITL conditions. Every field is optional so the frontend can patch a
    single slider without resending the whole state."""

    wind_speed: Optional[float] = Field(None, ge=0, description="SIM_WIND_SPD, m/s")
    wind_direction: Optional[float] = Field(None, ge=0, le=360, description="SIM_WIND_DIR, deg the wind comes from")
    wind_turbulence: Optional[float] = Field(None, ge=0, description="SIM_WIND_TURB")
    wind_elevation: Optional[float] = Field(None, ge=-90, le=90, description="SIM_WIND_DIR_Z, deg above horizontal")
    wind_variation: Optional[float] = Field(None, ge=0, description="SIM_WIND_TC, s for the wind to change")
    wind_profile: Optional[int] = Field(None, ge=0, le=2, description="SIM_WIND_T 0:square law 1:none 2:linear")
    wind_full_altitude: Optional[float] = Field(
        None, ge=0, description="SIM_WIND_T_ALT, m where wind reaches full speed"
    )
    wave_enable: Optional[int] = Field(None, ge=0, le=2, description="SIM_WAVE_ENABLE 0:off 1:roll/pitch 2:+heave")
    wave_amplitude: Optional[float] = Field(None, ge=0, description="SIM_WAVE_AMP, m")
    wave_length: Optional[float] = Field(None, gt=0, description="SIM_WAVE_LENGTH, m")
    wave_direction: Optional[float] = Field(None, ge=0, le=360, description="SIM_WAVE_DIR, deg")
    wave_speed: Optional[float] = Field(None, ge=0, description="SIM_WAVE_SPEED, m/s")
    tide_direction: Optional[float] = Field(None, ge=0, le=360, description="SIM_TIDE_DIR, deg")
    tide_speed: Optional[float] = Field(None, ge=0, description="SIM_TIDE_SPEED, m/s")
    speedup: Optional[float] = Field(None, gt=0, description="SIM_SPEEDUP, simulation rate multiplier")


class BatteryPack(BaseModel):
    """The battery pack the simulated vehicle runs on, and what its electronics cost it.

    The defaults describe the BlueBoat's original power supply: two 4S 18 Ah Li-ion packs in
    parallel, so 14.8 V nominal, 36 Ah and 532 Wh.
    """

    enabled: bool = Field(False, description="Whether the simulated pack drives the vehicle's battery readings")
    cells: int = Field(4, ge=1, le=24, description="Cells in series, which sets the pack voltage")
    packs: int = Field(2, ge=1, le=12, description="Packs wired in parallel")
    capacity_ah: float = Field(18.0, gt=0, le=1000, description="Amp-hours in one pack")
    idle_watts: float = Field(10.0, ge=0, le=1000, description="What the electronics draw with the vehicle still")


class PowerReading(BaseModel):
    """What the simulated pack is doing, as the panel shows it.

    The speed and wind the draw was computed from are reported alongside it, so a reading
    that looks surprising can be traced to the conditions behind it.
    """

    watts: float
    current: float = Field(..., description="Amps, negative while the pack is being charged")
    voltage: float
    charge: float = Field(..., description="Percent of the pack's charge left")
    consumed_mah: float
    water_speed: float = Field(..., description="Speed through the water, m/s")
    headwind: float = Field(..., description="Apparent wind along the hull, m/s; negative is a tailwind")
    charging: bool = False


class PowerSupply(BaseModel):
    """The pack as configured, with its live reading whenever it is the one being simulated."""

    pack: BatteryPack
    reading: Optional[PowerReading] = None


class Location(BaseModel):
    """Where SITL spawns, held in the ArduPilot ``SIM_OPOS_*`` parameters."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(0.0, description="Altitude AMSL, meters")
    heading: float = Field(0.0, ge=0, le=360, description="Initial heading, degrees")


class NamedPreset(BaseModel):
    """Common ground for the preset kinds: a name, and how the API found it.

    ``builtin`` and ``overridden`` are set when listing and left unset on the import and
    export payloads, where they would only describe the install the file came from.
    """

    name: str
    builtin: Optional[bool] = None
    # True on a built-in that a saved preset is currently shadowing. Such a preset cannot be
    # deleted, only reverted to the curated definition, which is a different offer to make.
    overridden: Optional[bool] = None


class EnvironmentPreset(NamedPreset):
    # Optional so a preset file written by hand, or saved from the sliders without a note,
    # still parses; it only ever feeds the tooltip on the preset's button.
    description: str = ""
    environment: Environment


class LocationPreset(NamedPreset):
    location: Location


class Vehicle(str, Enum):
    SUB = "Sub"
    ROVER = "Rover"
    PLANE = "Plane"
    COPTER = "Copter"


class VehicleStatus(BaseModel):
    board: Optional[str] = None
    is_sitl: bool = False
    frame: Optional[str] = None
    firmware_vehicle_type: Optional[str] = None
    firmware_version: Optional[str] = None
    # Whether the autopilot would refuse to arm, and the reason when it gave one. A refusal it
    # has not explained still reaches the panel, because the fact of it is worth knowing.
    arming_blocked: bool = False
    arming_refusal: Optional[str] = None


class VehicleConfigRequest(BaseModel):
    """A vehicle type, a SITL frame, or both, to be brought about in one job.

    Both are optional because either can be left as it is, but a request naming neither has
    nothing to do and is refused.
    """

    vehicle: Optional[Vehicle] = None
    frame: Optional[str] = None


class VehiclePreset(NamedPreset):
    """A ready-to-fly SITL vehicle configuration: the autopilot firmware type, the SITL
    physics frame and the defining ArduPilot parameters (frame/motor mapping, battery,
    basic tuning). The SITL frame supplies the physics; the parameters configure the
    vehicle to behave like the real product."""

    description: str
    vehicle: Vehicle
    frame: str = Field(..., description="SITL --frame model, e.g. 'vectored' or 'motorboat-skid'.")
    parameters: Dict[str, float] = Field(default_factory=dict)


class SavePresetRequest(BaseModel):
    """Capture the running SITL vehicle's current configuration as a named preset."""

    name: str = Field(..., min_length=1)
    description: str = ""


class RenamePresetRequest(BaseModel):
    """Rename a preset. Renaming a built-in copies it, since a built-in cannot be removed."""

    name: str = Field(..., min_length=1)


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApplyStep(BaseModel):
    """One stage of an apply job, as shown on the progress dialog's step bar."""

    key: str
    title: str
    state: StepState = StepState.PENDING
    detail: str = ""


class ParamOutcome(str, Enum):
    """What happened to one parameter during the parameter stage.

    ``UNCHANGED`` means the vehicle already held the wanted value, so nothing was sent.
    ``UNCONFIRMED`` means the write went out for a parameter the vehicle does have, but no
    read-back came: another client reading parameters can carry the answer off, so the value
    most likely landed and simply cannot be proven to have.
    ``UNSUPPORTED`` means the running firmware does not have the parameter at all, which
    is expected when a preset carries values from a different ArduPilot version.
    """

    WRITTEN = "written"
    UNCHANGED = "unchanged"
    UNCONFIRMED = "unconfirmed"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ParamRecord(BaseModel):
    name: str
    value: float
    outcome: ParamOutcome


class JobState(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApplyJob(BaseModel):
    """Progress of a vehicle configuration change.

    Applying a preset takes a firmware install and two autopilot restarts, far longer
    than a request should hold open, so the work runs in the background and the frontend
    polls this snapshot to drive the progress dialog.
    """

    id: int
    title: str
    state: JobState = JobState.RUNNING
    detail: str = ""
    steps: List[ApplyStep] = Field(default_factory=list)
    params_total: int = 0
    params_done: int = 0
    current_param: Optional[str] = None
    records: List[ParamRecord] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict, description="Parameter records grouped by outcome")
    skipped: List[str] = Field(
        default_factory=list, description="Titles of steps the user chose to skip after they failed"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Configuration problems no step failed on, e.g. a frame the outputs deny"
    )
    reported_vehicle: Optional[str] = Field(
        None, description="Vehicle type the autopilot reports over MAVLink once reconfigured"
    )


class ActivePreset(BaseModel):
    """Which vehicle preset (if any) the running SITL currently matches. ``None`` means
    the configuration does not match any known preset, i.e. it is custom."""

    name: Optional[str] = None


class OperationResult(BaseModel):
    success: bool
    detail: str = ""


class AppliedParams(BaseModel):
    """Echo of which parameters were written, useful for the frontend and for debugging."""

    applied: List[str] = Field(default_factory=list)
    # Written but not confirmed: the autopilot either never answered for the name or still
    # reports a different value. Listed so the UI can say the conditions are only partly set
    # instead of reporting a clean success over a simulator that did not change.
    unverified: List[str] = Field(default_factory=list)
