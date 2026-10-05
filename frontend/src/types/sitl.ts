export interface Environment {
  wind_speed?: number | null
  wind_direction?: number | null
  wind_turbulence?: number | null
  wind_elevation?: number | null
  wind_variation?: number | null
  wind_profile?: number | null
  wind_full_altitude?: number | null
  wave_enable?: number | null
  wave_amplitude?: number | null
  wave_length?: number | null
  wave_direction?: number | null
  wave_speed?: number | null
  tide_direction?: number | null
  tide_speed?: number | null
  speedup?: number | null
}

// The battery pack the simulated vehicle runs on. The defaults describe the BlueBoat's original
// supply: two 4S 18 Ah Li-ion packs in parallel, so 14.8 V nominal, 36 Ah and 532 Wh.
export interface BatteryPack {
  enabled: boolean
  cells: number
  packs: number
  capacity_ah: number
  // What the electronics draw with the vehicle still.
  idle_watts: number
}

// What the pack reads now, and the conditions its draw was computed from.
export interface PowerReading {
  watts: number
  current: number
  voltage: number
  // Percent of the pack's charge left.
  charge: number
  consumed_mah: number
  water_speed: number
  // Apparent wind along the hull; negative is a following breeze.
  headwind: number
  charging: boolean
}

export interface PowerSupply {
  pack: BatteryPack
  // Absent unless the simulated pack is the one the vehicle is reporting.
  reading: PowerReading | null
}

export interface AppliedParams {
  applied: string[]
  // Written but not confirmed by a read-back, so the simulator may not be running them.
  unverified: string[]
}

// Where SITL spawns, held in the vehicle's SIM_OPOS_* parameters.
export interface SitlLocation {
  latitude: number
  longitude: number
  altitude: number
  heading: number
}

// Common to both preset kinds. Set by the list endpoints and absent from the files that are
// imported or exported, where they would only describe the install the file came from.
export interface PresetOrigin {
  // True for the presets that ship with the extension, which can be edited but not deleted.
  builtin?: boolean | null
  // True on a built-in a saved preset is currently shadowing, which reverts instead.
  overridden?: boolean | null
}

export interface EnvironmentPreset extends PresetOrigin {
  name: string
  description: string
  environment: Environment
}

export interface LocationPreset extends PresetOrigin {
  name: string
  location: SitlLocation
}

export interface VehicleStatus {
  board: string | null
  is_sitl: boolean
  frame: string | null
  firmware_vehicle_type: string | null
  firmware_version: string | null
  arming_blocked: boolean
  // The autopilot's own words, absent when it refused without explaining itself.
  arming_refusal: string | null
}

export type VehicleType = 'Sub' | 'Rover' | 'Plane' | 'Copter'

export interface VehiclePreset extends PresetOrigin {
  name: string
  description: string
  vehicle: VehicleType
  frame: string
  parameters: Record<string, number>
}

export type StepState = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

export interface ApplyStep {
  key: string
  title: string
  state: StepState
  detail: string
}

// 'unchanged': the vehicle already held the value, so nothing was sent.
// 'unconfirmed': the write went out, but no read-back came to prove it landed.
// 'unsupported': the running firmware does not have the parameter at all.
export type ParamOutcome = 'written' | 'unchanged' | 'unconfirmed' | 'unsupported' | 'failed'

export interface ParamRecord {
  name: string
  value: number
  outcome: ParamOutcome
}

export type JobState = 'running' | 'succeeded' | 'failed'

// Progress of a configuration change, polled while the dialog is open.
export interface ApplyJob {
  id: number
  title: string
  state: JobState
  detail: string
  steps: ApplyStep[]
  params_total: number
  params_done: number
  current_param: string | null
  records: ParamRecord[]
  counts: Partial<Record<ParamOutcome, number>>
  // Titles of the steps the user chose to skip after they failed.
  skipped: string[]
  // Configuration problems no step failed on, e.g. a frame the vehicle's outputs deny.
  warnings: string[]
  reported_vehicle: string | null
}

export interface OperationResult {
  success: boolean
  detail: string
}
