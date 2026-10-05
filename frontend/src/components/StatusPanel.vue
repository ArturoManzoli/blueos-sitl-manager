<script setup lang="ts">
import { BlueBanner, BlueStat, useBlueSnackbar } from '@bluerobotics/bluevue'
import { computed } from 'vue'

import { refreshVehicleStatus, vehicleStatus } from '@/composables/vehicleStatus'

const { notifyError } = useBlueSnackbar()

// What the autopilot said when the status was last read, which the refresh button asks again.
// Worth a banner of its own because what blocks arming is often nothing this extension writes:
// a disk with no room left for the dataflash log refuses every arm command in the same way.
const armingText = computed(() =>
  vehicleStatus.value?.arming_refusal
    ? `The autopilot is refusing to arm: ${vehicleStatus.value.arming_refusal}`
    : 'The autopilot is refusing to arm, without saying why.'
)

const fields = computed(() => [
  { label: 'Board', value: vehicleStatus.value?.board },
  { label: 'Firmware', value: vehicleStatus.value?.firmware_version },
  { label: 'Frame', value: vehicleStatus.value?.frame },
  { label: 'Vehicle type', value: vehicleStatus.value?.firmware_vehicle_type },
])

async function reload(): Promise<void> {
  try {
    await refreshVehicleStatus()
  } catch (error) {
    notifyError(error, 'Could not read vehicle status')
  }
}

defineExpose({ reload })
</script>

<template>
  <div class="px-8">
    <BlueBanner
      v-if="vehicleStatus && !vehicleStatus.is_sitl"
      class="mb-3"
      severity="warning"
      text="The active board is not SITL, so everything that writes to the vehicle is disabled.
        Select SITL in the Autopilot Firmware page to use this extension."
    />

    <BlueBanner
      v-if="vehicleStatus?.arming_blocked"
      class="mb-3"
      severity="warning"
      :text="armingText"
    />

    <div class="flex flex-wrap items-stretch gap-2">
      <BlueStat
        v-for="field in fields"
        :key="field.label"
        :label="field.label"
        :value="field.value"
      />
    </div>
  </div>
</template>
