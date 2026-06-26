<script setup lang="ts">
import { ref } from 'vue'

import EnvironmentPanel from '@/components/EnvironmentPanel.vue'
import ExpansiblePanel from '@/components/ExpansiblePanel.vue'
import LocationPanel from '@/components/LocationPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import VehiclePanel from '@/components/VehiclePanel.vue'

const statusPanel = ref<InstanceType<typeof StatusPanel> | null>(null)
const vehiclePanel = ref<InstanceType<typeof VehiclePanel> | null>(null)
const environmentPanel = ref<InstanceType<typeof EnvironmentPanel> | null>(null)
const refreshing = ref(false)

// A vehicle change can move every field (type, frame, conditions), so re-read them all
// from the vehicle rather than trusting the local form state.
async function onVehicleChanged(): Promise<void> {
  await Promise.all([
    statusPanel.value?.refresh(),
    vehiclePanel.value?.refresh(),
    environmentPanel.value?.refresh(),
  ])
}

async function refreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await onVehicleChanged()
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <v-container
    class="max-w-[615px] text-white pa-0 rounded-[8px] elevation-5 mx-auto mt-6 mb-10 bg-[#363636]"
  >
    <div class="flex items-center gap-2 rounded-t-[8px] bg-[#15151577] px-5 py-3">
      <v-icon>mdi-test-tube</v-icon>
      <span class="text-lg font-medium">SITL Manager</span>
      <button
        class="ml-auto rounded-[6px] px-2 py-1 text-[#ffffffaa] hover:text-white transition-colors"
        :class="refreshing ? 'opacity-50 pointer-events-none' : 'cursor-pointer'"
        title="Refresh"
        @click="refreshAll"
      >
        <v-icon :class="refreshing ? 'animate-spin' : ''">
          mdi-refresh
        </v-icon>
      </button>
    </div>

    <div class="px-5 py-4">
      <StatusPanel ref="statusPanel" />

      <ExpansiblePanel
        title="Vehicle & frame"
        theme="dark"
        :expanded="true"
      >
        <VehiclePanel
          ref="vehiclePanel"
          @changed="onVehicleChanged"
        />
      </ExpansiblePanel>

      <ExpansiblePanel
        title="Location"
        theme="dark"
        :expanded="true"
      >
        <LocationPanel />
      </ExpansiblePanel>

      <ExpansiblePanel
        title="Ambient conditions"
        theme="dark"
        :expanded="true"
      >
        <EnvironmentPanel ref="environmentPanel" />
      </ExpansiblePanel>
    </div>
  </v-container>
</template>
