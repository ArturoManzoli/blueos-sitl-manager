import axios from 'axios'

import type {
  AppliedParams,
  ApplyJob,
  Environment,
  EnvironmentPreset,
  LocationPreset,
  OperationResult,
  SitlLocation,
  VehiclePreset,
  VehicleStatus,
  VehicleType,
} from '@/types/sitl'

// The extension and its backend are served from the same origin, so the API lives
// under the versioned prefix relative to wherever BlueOS mounts the extension.
const api = axios.create({ baseURL: 'v1.0' })

// How many presets a row holds, built-ins included. The backend enforces this and refuses a
// save past it; the panels only mirror it to grey the menu items out before that happens.
export const MAX_PRESETS = 9

export const VehicleApi = {
  async status(): Promise<VehicleStatus> {
    return (await api.get<VehicleStatus>('/vehicle/status')).data
  },
  // Grouped by vehicle type, since a frame is a physics model built into one firmware.
  async frames(): Promise<Partial<Record<VehicleType, string[]>>> {
    return (await api.get<Partial<Record<VehicleType, string[]>>>('/vehicle/frames')).data
  },
  // Configuration changes run as a background job on the backend; these start one and
  // return its first snapshot, which callers then poll through applyJob().
  //
  // Vehicle type and frame go together in one job: a combination chosen by hand often moves
  // both, and sending them separately would install firmware and restart twice to get there.
  async applyConfig(config: { vehicle?: VehicleType; frame?: string }): Promise<ApplyJob> {
    return (await api.post<ApplyJob>('/vehicle/apply', config)).data
  },
  async applyPreset(name: string): Promise<ApplyJob> {
    return (await api.post<ApplyJob>(`/vehicle/presets/${encodeURIComponent(name)}/apply`)).data
  },
  async applyJob(): Promise<ApplyJob | null> {
    return (await api.get<ApplyJob | null>('/vehicle/apply-job')).data
  },
  // Both act on the step that failed and then carry the same job on through the remaining
  // steps; neither restarts the sequence from the beginning.
  async retryApplyJob(): Promise<ApplyJob> {
    return (await api.post<ApplyJob>('/vehicle/apply-job/retry')).data
  },
  async skipApplyJob(): Promise<ApplyJob> {
    return (await api.post<ApplyJob>('/vehicle/apply-job/skip')).data
  },
  async restart(): Promise<OperationResult> {
    return (await api.post<OperationResult>('/vehicle/restart')).data
  },
  async presets(): Promise<VehiclePreset[]> {
    return (await api.get<VehiclePreset[]>('/vehicle/presets')).data
  },
  async activePreset(): Promise<string | null> {
    return (await api.get<{ name: string | null }>('/vehicle/active-preset')).data.name
  },
  // Snapshots the live vehicle (full parameter dump); slow, so callers show a loader.
  async currentConfig(): Promise<VehiclePreset> {
    return (await api.get<VehiclePreset>('/vehicle/current-config')).data
  },
  async savePreset(name: string, description: string): Promise<VehiclePreset> {
    return (await api.post<VehiclePreset>('/vehicle/presets/save', { name, description })).data
  },
  async importPreset(preset: VehiclePreset): Promise<VehiclePreset> {
    return (await api.post<VehiclePreset>('/vehicle/presets/import', preset)).data
  },
  // Renaming a built-in copies it, since a built-in cannot be removed.
  async renamePreset(name: string, newName: string): Promise<VehiclePreset> {
    return (await api.post<VehiclePreset>(`/vehicle/presets/${encodeURIComponent(name)}/rename`, { name: newName })).data
  },
  // Deletes a saved preset, or reverts a built-in that a saved one was shadowing.
  async deletePreset(name: string): Promise<OperationResult> {
    return (await api.delete<OperationResult>(`/vehicle/presets/${encodeURIComponent(name)}`)).data
  },
}

export const EnvironmentApi = {
  async get(): Promise<Environment> {
    return (await api.get<Environment>('/environment')).data
  },
  async set(environment: Environment): Promise<AppliedParams> {
    return (await api.post<AppliedParams>('/environment', environment)).data
  },
  async presets(): Promise<EnvironmentPreset[]> {
    return (await api.get<EnvironmentPreset[]>('/environment/presets')).data
  },
  async applyPreset(name: string): Promise<AppliedParams> {
    return (await api.post<AppliedParams>(`/environment/presets/${encodeURIComponent(name)}`)).data
  },
}

export const LocationApi = {
  async presets(): Promise<LocationPreset[]> {
    return (await api.get<LocationPreset[]>('/location/presets')).data
  },
  async get(): Promise<SitlLocation> {
    return (await api.get<SitlLocation>('/location')).data
  },
  // Restarts the autopilot and waits for it to report the new position; callers show a
  // loader for it.
  async set(location: SitlLocation): Promise<OperationResult> {
    return (await api.post<OperationResult>('/location', location)).data
  },
  // One endpoint for saving and for importing: both amount to storing a named location.
  async savePreset(preset: LocationPreset): Promise<LocationPreset> {
    return (await api.post<LocationPreset>('/location/presets', preset)).data
  },
  async renamePreset(name: string, newName: string): Promise<LocationPreset> {
    return (await api.post<LocationPreset>(`/location/presets/${encodeURIComponent(name)}/rename`, { name: newName })).data
  },
  async deletePreset(name: string): Promise<OperationResult> {
    return (await api.delete<OperationResult>(`/location/presets/${encodeURIComponent(name)}`)).data
  },
}
