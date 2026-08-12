<script setup lang="ts">
import { computed } from 'vue'

import { notifyError } from '@/composables/notify'
import { refreshVehicleStatus, vehicleStatus } from '@/composables/vehicleStatus'

const fields = computed(() => [
  { label: 'Board', value: vehicleStatus.value?.board ?? '—' },
  { label: 'Firmware', value: vehicleStatus.value?.firmware_version ?? '—' },
  { label: 'Frame', value: vehicleStatus.value?.frame ?? '—' },
  { label: 'Vehicle type', value: vehicleStatus.value?.firmware_vehicle_type ?? '—' },
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
  <!-- px-8 matches ExpansiblePanel's content inset so this row lines up with the panels. -->
  <div class="px-8">
    <div
      v-if="vehicleStatus && !vehicleStatus.is_sitl"
      class="flex items-center gap-2 rounded-[6px] bg-[#FB8C0022] border border-[#FB8C0055] text-[#FFB74D] text-xs px-3 py-2 mb-3"
    >
      <v-icon size="16">
        mdi-alert
      </v-icon>
      The active board is not SITL, so everything that writes to the vehicle is disabled.
      Select SITL in the Autopilot Firmware page to use this extension.
    </div>

    <div class="flex flex-wrap items-stretch gap-2">
      <div
        v-for="field in fields"
        :key="field.label"
        class="elevation-1 flex-1 min-w-[120px] rounded-[6px] bg-[#00000022] px-3 py-2"
      >
        <div class="text-[11px] uppercase tracking-wide text-[#ffffff66] truncate">
          {{ field.label }}
        </div>
        <div
          class="text-sm text-white truncate"
          :title="String(field.value)"
        >
          {{ field.value }}
        </div>
      </div>
    </div>
  </div>
</template>
