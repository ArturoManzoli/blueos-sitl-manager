<script setup lang="ts">
import { BlueExpansiblePanel } from '@bluerobotics/bluevue'
import { onMounted, ref } from 'vue'

import logo from '@/assets/br-logo-white.svg'
import EnvironmentPanel from '@/components/EnvironmentPanel.vue'
import LocationPanel from '@/components/LocationPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import VehiclePanel from '@/components/VehiclePanel.vue'
import { hideLoading, showLoading } from '@/composables/loading'

const statusPanel = ref<InstanceType<typeof StatusPanel> | null>(null)
const vehiclePanel = ref<InstanceType<typeof VehiclePanel> | null>(null)
const locationPanel = ref<InstanceType<typeof LocationPanel> | null>(null)
const environmentPanel = ref<InstanceType<typeof EnvironmentPanel> | null>(null)
const refreshing = ref(false)

// Every panel reads everything it shows, lists included. One entry point rather than a
// cheap refresh and a full load: a list that failed to arrive — the backend was restarting,
// the autopilot was not answering yet — is then repaired by the next refresh instead of
// staying empty until the page is reloaded.
async function reloadAll(): Promise<void> {
  await Promise.all([
    statusPanel.value?.reload(),
    vehiclePanel.value?.reload(),
    locationPanel.value?.reload(),
    environmentPanel.value?.reload(),
  ])
}

// Reading everything waits on the autopilot answering, which it may not do quickly, so the
// values on screen — which belong to the vehicle as it was — are covered until the new ones
// arrive rather than being left there to be read as current. Dismissible, so the wait can be
// waved off to work with whatever has already landed.
async function reloadBehindOverlay(message: string): Promise<void> {
  showLoading(message, true)
  try {
    await reloadAll()
  } finally {
    hideLoading()
  }
}

// A vehicle change moves every field on the page: type, frame, spawn point, conditions.
async function onVehicleChanged(): Promise<void> {
  await reloadBehindOverlay('Reading the new vehicle configuration…')
}

async function refreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await reloadBehindOverlay('Reading the vehicle configuration…')
  } finally {
    refreshing.value = false
  }
}

onMounted(async () => {
  await reloadBehindOverlay('Reading the vehicle configuration…')
})
</script>

<template>
  <v-container
    class="max-w-[615px] text-white pa-0 rounded-[8px] elevation-5 mx-auto mt-6 mb-10 bg-[#363636]"
  >
    <!-- relative so the elevation paints over the body below instead of under it. -->
    <div class="elevation-1 relative flex items-center gap-5 rounded-t-[8px] bg-[#15151577] px-5 py-3">
      <img
        :src="logo"
        alt="Blue Robotics"
        class="h-6 w-6 shrink-0"
      >
      <span class="text-lg font-medium truncate">SITL Manager</span>
      <button
        class="ml-auto shrink-0 rounded-[6px] px-2 py-1 text-[#ffffffaa] hover:text-white transition-colors"
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

      <BlueExpansiblePanel
        title="Vehicle & frame"
        theme="dark"
        :expanded="true"
      >
        <VehiclePanel
          ref="vehiclePanel"
          @changed="onVehicleChanged"
        />
      </BlueExpansiblePanel>

      <BlueExpansiblePanel
        title="Spawn location"
        theme="dark"
        :expanded="true"
      >
        <LocationPanel
          ref="locationPanel"
          @changed="onVehicleChanged"
        />
      </BlueExpansiblePanel>

      <BlueExpansiblePanel
        title="Ambient conditions"
        theme="dark"
        :expanded="true"
      >
        <EnvironmentPanel ref="environmentPanel" />
      </BlueExpansiblePanel>
    </div>
  </v-container>
</template>
