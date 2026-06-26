<script setup lang="ts">
import { ref } from 'vue'

import EnvironmentPanel from '@/components/EnvironmentPanel.vue'
import LocationPanel from '@/components/LocationPanel.vue'
import StatusPanel from '@/components/StatusPanel.vue'
import VehiclePanel from '@/components/VehiclePanel.vue'
import { snackbar } from '@/composables/notify'

const statusPanel = ref<InstanceType<typeof StatusPanel> | null>(null)

function onVehicleChanged(): void {
  statusPanel.value?.refresh()
}
</script>

<template>
  <v-app>
    <v-app-bar
      color="surface"
      density="comfortable"
      flat
    >
      <v-icon class="mx-3">
        mdi-test-tube
      </v-icon>
      <v-app-bar-title>SITL Manager</v-app-bar-title>
    </v-app-bar>

    <v-main>
      <v-container
        fluid
        class="pa-4"
      >
        <v-row>
          <v-col cols="12">
            <StatusPanel ref="statusPanel" />
          </v-col>
          <v-col
            cols="12"
            md="6"
          >
            <VehiclePanel @changed="onVehicleChanged" />
          </v-col>
          <v-col
            cols="12"
            md="6"
          >
            <LocationPanel />
          </v-col>
          <v-col cols="12">
            <EnvironmentPanel />
          </v-col>
        </v-row>
      </v-container>
    </v-main>

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      location="bottom right"
      :timeout="4000"
    >
      {{ snackbar.text }}
    </v-snackbar>
  </v-app>
</template>
