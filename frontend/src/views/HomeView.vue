<script setup lang="ts">
import { BlueApp, BlueButton, BlueExpansiblePanel, useBlueLoading } from '@bluerobotics/bluevue'
import { onMounted, ref } from 'vue'

import logo from '@/assets/br-logo-white.svg'
import EnvironmentPanel from '@/components/EnvironmentPanel.vue'
import LocationPanel from '@/components/LocationPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import VehiclePanel from '@/components/VehiclePanel.vue'

const { showLoading, hideLoading } = useBlueLoading()

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
  <BlueApp
    title="SITL Manager"
    :logo="logo"
  >
    <template #actions>
      <BlueButton
        variant="icon"
        icon="mdi-refresh"
        tooltip="Refresh"
        :loading="refreshing"
        @click="refreshAll"
      />
    </template>

    <StatusPanel
      ref="statusPanel"
      class="my-3.5"
    />

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
  </BlueApp>
</template>
