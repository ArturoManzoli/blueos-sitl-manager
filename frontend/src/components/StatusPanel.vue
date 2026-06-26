<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { notifyError } from '@/composables/notify'
import { VehicleApi } from '@/services/api'
import type { VehicleStatus } from '@/types/sitl'

const status = ref<VehicleStatus | null>(null)
const loading = ref(false)

const fields = computed(() => [
  { label: 'Board', value: status.value?.board ?? '—' },
  { label: 'Is SITL', value: status.value ? (status.value.is_sitl ? 'Yes' : 'No') : '—' },
  { label: 'Frame', value: status.value?.frame ?? '—' },
  { label: 'Vehicle type', value: status.value?.firmware_vehicle_type ?? '—' },
])

async function refresh(): Promise<void> {
  loading.value = true
  try {
    status.value = await VehicleApi.status()
  } catch (error) {
    notifyError(error, 'Could not read vehicle status')
  } finally {
    loading.value = false
  }
}

defineExpose({ refresh })
onMounted(refresh)
</script>

<template>
  <div>
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
      <button
        class="rounded-[6px] bg-[#00000022] px-3 text-[#ffffffaa] hover:text-white transition-colors"
        :class="loading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'"
        title="Refresh status"
        @click="refresh"
      >
        <v-icon :class="loading ? 'animate-spin' : ''">
          mdi-refresh
        </v-icon>
      </button>
    </div>
  </div>
</template>
