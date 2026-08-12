import { computed, ref } from 'vue'

import { VehicleApi } from '@/services/api'
import type { VehicleStatus } from '@/types/sitl'

const status = ref<VehicleStatus | null>(null)
let inflight: Promise<VehicleStatus> | null = null

/** What the board last reported: type, frame, firmware and whether it is the simulator. */
export const vehicleStatus = computed(() => status.value)

// Only a board that answered and said it is not SITL locks the controls. Before the first
// read, or after one that failed, the extension stays usable: the backend refuses these
// operations on a real board anyway, and this is the hint rather than the barrier.
export const isSitl = computed(() => status.value?.is_sitl !== false)

/** Read the vehicle status, sharing one request between panels that ask at the same time. */
export async function refreshVehicleStatus(): Promise<VehicleStatus> {
  if (!inflight) {
    inflight = VehicleApi.status().finally(() => {
      inflight = null
    })
  }
  const next = await inflight
  status.value = next
  return next
}
