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

export interface TeleportRequest {
  location: SitlLocation
  disable_simulated_gps: boolean
}

export interface VehicleStatus {
  board: string | null
  is_sitl: boolean
  frame: string | null
  firmware_vehicle_type: string | null
  firmware_version: string | null
}

export interface FrameRequest {
  frame: string
  restart: boolean
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

export interface VehiclePresetResult {
  success: boolean
  detail: string
  applied: string[]
  failed: string[]
}

export interface OperationResult {
  success: boolean
  detail: string
}
