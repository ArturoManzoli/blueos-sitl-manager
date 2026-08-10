import axios from 'axios'

import type {
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

export const VehicleApi = {
  async status(): Promise<VehicleStatus> {
    return (await api.get<VehicleStatus>('/vehicle/status')).data
  },
  async frames(): Promise<string[]> {
    return (await api.get<string[]>('/vehicle/frames')).data
  },
  // Configuration changes run as a background job on the backend; these start one and
  // return its first snapshot, which callers then poll through applyJob().
  async setFrame(frame: string): Promise<ApplyJob> {
    return (await api.post<ApplyJob>('/vehicle/frame', { frame })).data
  },
  async setType(vehicle: VehicleType): Promise<ApplyJob> {
    return (await api.post<ApplyJob>('/vehicle/type', { vehicle })).data
  },
  async applyPreset(name: string): Promise<ApplyJob> {
    return (await api.post<ApplyJob>(`/vehicle/presets/${encodeURIComponent(name)}/apply`)).data
  },
  async applyJob(): Promise<ApplyJob | null> {
    return (await api.get<ApplyJob | null>('/vehicle/apply-job')).data
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
  async deletePreset(name: string): Promise<OperationResult> {
    return (await api.delete<OperationResult>(`/vehicle/presets/${encodeURIComponent(name)}`)).data
  },
}

export const EnvironmentApi = {
  async get(): Promise<Environment> {
    return (await api.get<Environment>('/environment')).data
  },
  async set(environment: Environment): Promise<{ applied: string[] }> {
    return (await api.post<{ applied: string[] }>('/environment', environment)).data
  },
  async presets(): Promise<EnvironmentPreset[]> {
    return (await api.get<EnvironmentPreset[]>('/environment/presets')).data
  },
  async applyPreset(name: string): Promise<{ applied: string[] }> {
    return (await api.post<{ applied: string[] }>(`/environment/presets/${encodeURIComponent(name)}`)).data
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
}
