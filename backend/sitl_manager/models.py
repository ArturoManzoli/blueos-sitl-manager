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
    wave_enable: Optional[int] = Field(None, ge=0, le=2, description="SIM_WAVE_ENABLE 0:off 1:roll/pitch 2:+heave")
    wave_amplitude: Optional[float] = Field(None, ge=0, description="SIM_WAVE_AMP, m")
    wave_length: Optional[float] = Field(None, gt=0, description="SIM_WAVE_LENGTH, m")
    wave_direction: Optional[float] = Field(None, ge=0, le=360, description="SIM_WAVE_DIR, deg")
    wave_speed: Optional[float] = Field(None, ge=0, description="SIM_WAVE_SPEED, m/s")
    tide_direction: Optional[float] = Field(None, ge=0, le=360, description="SIM_TIDE_DIR, deg")
    tide_speed: Optional[float] = Field(None, ge=0, description="SIM_TIDE_SPEED, m/s")
    speedup: Optional[float] = Field(None, gt=0, description="SIM_SPEEDUP, simulation rate multiplier")


class EnvironmentPreset(BaseModel):
    name: str
    description: str
    environment: Environment


class Location(BaseModel):
    """Where SITL spawns, held in the ArduPilot ``SIM_OPOS_*`` parameters."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(0.0, description="Altitude AMSL, meters")
    heading: float = Field(0.0, ge=0, le=360, description="Initial heading, degrees")


class LocationPreset(BaseModel):
    name: str
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


class FrameRequest(BaseModel):
    frame: str


class VehicleTypeRequest(BaseModel):
    vehicle: Vehicle


class VehiclePreset(BaseModel):
    """A ready-to-fly SITL vehicle configuration: the autopilot firmware type, the SITL
    physics frame and the defining ArduPilot parameters (frame/motor mapping, battery,
    basic tuning). The SITL frame supplies the physics; the parameters configure the
    vehicle to behave like the real product."""

    name: str
    description: str
    vehicle: Vehicle
    frame: str = Field(..., description="SITL --frame model, e.g. 'vectored' or 'motorboat-skid'.")
    parameters: Dict[str, float] = Field(default_factory=dict)
    # Set by the API when listing presets: True for curated built-ins, False for the
    # user-saved/imported presets that can be deleted. Unset on import/export payloads.
    builtin: Optional[bool] = None


class SavePresetRequest(BaseModel):
    """Capture the running SITL vehicle's current configuration as a named preset."""

    name: str = Field(..., min_length=1)
    description: str = ""


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
    ``UNSUPPORTED`` means the running firmware does not have the parameter at all, which
    is expected when a preset carries values from a different ArduPilot version.
    """

    WRITTEN = "written"
    UNCHANGED = "unchanged"
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
