export interface Environment {
  wind_speed?: number | null
  wind_direction?: number | null
  wind_turbulence?: number | null
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

// Where SITL spawns, held in the vehicle's SIM_OPOS_* parameters.
export interface SitlLocation {
  latitude: number
  longitude: number
  altitude: number
  heading: number
}

export interface LocationPreset {
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

export interface VehiclePreset {
  name: string
  description: string
  vehicle: VehicleType
  frame: string
  parameters: Record<string, number>
  // Set by the preset list endpoint: true for built-ins, false for deletable customs.
  builtin?: boolean | null
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
  reported_vehicle: string | null
}

export interface OperationResult {
  success: boolean
  detail: string
}
