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

export interface EnvironmentPreset {
  name: string
  description: string
  environment: Environment
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
// 'unsupported': the running firmware does not have the parameter at all.
export type ParamOutcome = 'written' | 'unchanged' | 'unsupported' | 'failed'

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
  reported_vehicle: string | null
}

export interface OperationResult {
  success: boolean
  detail: string
}
