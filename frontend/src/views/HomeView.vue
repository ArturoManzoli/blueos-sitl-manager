<script setup lang="ts">
import { ref } from 'vue'

import EnvironmentPanel from '@/components/EnvironmentPanel.vue'
import ExpansiblePanel from '@/components/ExpansiblePanel.vue'
import LocationPanel from '@/components/LocationPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import VehiclePanel from '@/components/VehiclePanel.vue'

const statusPanel = ref<InstanceType<typeof StatusPanel> | null>(null)

function onVehicleChanged(): void {
  statusPanel.value?.refresh()
}
</script>

<template>
  <v-container
    class="max-w-[820px] text-white pa-0 rounded-[8px] elevation-5 mx-auto mt-6 mb-10 bg-[#363636]"
  >
    <div class="flex items-center gap-2 rounded-t-[8px] bg-[#15151577] px-5 py-3">
      <v-icon>mdi-test-tube</v-icon>
      <span class="text-lg font-medium">SITL Manager</span>
    </div>

    <div class="px-5 py-4">
      <StatusPanel ref="statusPanel" />

      <ExpansiblePanel
        title="Vehicle & frame"
        theme="dark"
      >
        <VehiclePanel @changed="onVehicleChanged" />
      </ExpansiblePanel>

      <ExpansiblePanel
        title="Location"
        theme="dark"
      >
        <LocationPanel />
      </ExpansiblePanel>

      <ExpansiblePanel
        title="Ambient conditions"
        theme="dark"
      >
        <EnvironmentPanel />
      </ExpansiblePanel>
    </div>
  </v-container>
</template>
