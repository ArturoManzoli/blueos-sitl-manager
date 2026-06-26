import axios from 'axios'

import type {
  Environment,
  EnvironmentPreset,
  FrameRequest,
  LocationPreset,
  OperationResult,
  TeleportRequest,
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
  async setFrame(request: FrameRequest): Promise<OperationResult> {
    return (await api.post<OperationResult>('/vehicle/frame', request)).data
  },
  async setType(vehicle: VehicleType): Promise<OperationResult> {
    return (await api.post<OperationResult>('/vehicle/type', { vehicle })).data
  },
  async restart(): Promise<OperationResult> {
    return (await api.post<OperationResult>('/vehicle/restart')).data
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
  async teleport(request: TeleportRequest): Promise<OperationResult> {
    return (await api.post<OperationResult>('/location/teleport', request)).data
  },
  async luaScript(): Promise<string> {
    return (await api.get<string>('/location/lua-script')).data
  },
}
