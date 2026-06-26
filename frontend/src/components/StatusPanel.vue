<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { notifyError } from '@/composables/notify'
import { VehicleApi } from '@/services/api'
import type { VehicleStatus } from '@/types/sitl'

const status = ref<VehicleStatus | null>(null)

const fields = computed(() => [
  { label: 'Board', value: status.value?.board ?? '—' },
  { label: 'Firmware version', value: status.value?.firmware_version ?? '—' },
  { label: 'Frame', value: status.value?.frame ?? '—' },
  { label: 'Vehicle type', value: status.value?.firmware_vehicle_type ?? '—' },
])

async function refresh(): Promise<void> {
  try {
    status.value = await VehicleApi.status()
  } catch (error) {
    notifyError(error, 'Could not read vehicle status')
  }
}

defineExpose({ refresh })
onMounted(refresh)
</script>

<template>
  <!-- px-8 matches ExpansiblePanel's content inset so this row lines up with the panels. -->
  <div class="px-8">
    <div
      v-if="status && !status.is_sitl"
      class="flex items-center gap-2 rounded-[6px] bg-[#FB8C0022] border border-[#FB8C0055] text-[#FFB74D] text-xs px-3 py-2 mb-3"
    >
      <v-icon size="16">
        mdi-alert
      </v-icon>
      The active board is not SITL. Select SITL in the Autopilot Firmware page to use this extension.
    </div>

    <div class="flex flex-wrap items-stretch gap-2">
      <div
        v-for="field in fields"
        :key="field.label"
        class="flex-1 min-w-[120px] rounded-[6px] bg-[#00000022] px-3 py-2"
      >
        <div class="text-[11px] uppercase tracking-wide text-[#ffffff66]">
          {{ field.label }}
        </div>
        <div class="text-sm text-white truncate">
          {{ field.value }}
        </div>
      </div>
    </div>
  </div>
</template>
