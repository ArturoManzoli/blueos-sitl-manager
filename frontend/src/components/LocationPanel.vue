<script setup lang="ts">
import { onMounted, ref } from 'vue'

import MapPicker from '@/components/MapPicker.vue'
import { notify, notifyError } from '@/composables/notify'
import { LocationApi } from '@/services/api'
import type { LocationPreset, SitlLocation } from '@/types/sitl'

const location = ref<SitlLocation>({ latitude: -27.563, longitude: -48.459, altitude: 0, heading: 270 })
const presets = ref<LocationPreset[]>([])
const disableSimulatedGps = ref(true)
const busy = ref(false)
const showLua = ref(false)
const luaScript = ref('')

async function loadPresets(): Promise<void> {
  try {
    presets.value = await LocationApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load location presets')
  }
}

function applyPreset(preset: LocationPreset): void {
  location.value = { ...preset.location }
}

function useBrowserLocation(): void {
  if (!navigator.geolocation) {
    notify('Geolocation is not available in this browser.', 'warning')
    return
  }
  navigator.geolocation.getCurrentPosition(
    (position) => {
      location.value = {
        ...location.value,
        latitude: Number(position.coords.latitude.toFixed(6)),
        longitude: Number(position.coords.longitude.toFixed(6)),
      }
      notify('Filled coordinates from your browser location.', 'info')
    },
    (error) => notify(`Could not get browser location: ${error.message}`, 'warning'),
  )
}

async function teleport(): Promise<void> {
  busy.value = true
  try {
    const result = await LocationApi.teleport({
      location: location.value,
      disable_simulated_gps: disableSimulatedGps.value,
    })
    notify(result.detail, 'success')
  } catch (error) {
    notifyError(error, 'Teleport failed')
  } finally {
    busy.value = false
  }
}

async function openLua(): Promise<void> {
  try {
    luaScript.value = await LocationApi.luaScript()
    showLua.value = true
  } catch (error) {
    notifyError(error, 'Could not load the Lua helper')
  }
}

onMounted(loadPresets)
</script>

<template>
  <v-card>
    <v-card-title>
      <v-icon class="mr-2">
        mdi-map-marker
      </v-icon>
      Location
    </v-card-title>
    <v-card-text>
      <v-alert
        type="info"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        SITL always boots at the BlueOS default home (Florianópolis). This relocates the
        running vehicle afterwards by moving its EKF origin.
      </v-alert>

      <div class="text-subtitle-2 mb-2">
        Presets
      </div>
      <div class="d-flex flex-wrap ga-2 mb-4">
        <v-btn
          v-for="preset in presets"
          :key="preset.name"
          size="small"
          variant="tonal"
          @click="applyPreset(preset)"
        >
          {{ preset.name }}
        </v-btn>
      </div>

      <MapPicker
        v-model:latitude="location.latitude"
        v-model:longitude="location.longitude"
        :heading="location.heading"
        class="mb-4"
      />

      <v-row dense>
        <v-col cols="6">
          <v-text-field
            v-model.number="location.latitude"
            label="Latitude"
            type="number"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            v-model.number="location.longitude"
            label="Longitude"
            type="number"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            v-model.number="location.altitude"
            label="Altitude (m AMSL)"
            type="number"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            v-model.number="location.heading"
            label="Heading (°)"
            type="number"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
      </v-row>

      <v-checkbox
        v-model="disableSimulatedGps"
        label="Disable simulated GPS so the move sticks on the map"
        density="compact"
        hide-details
        class="mt-2"
      />

      <div class="d-flex ga-2 mt-2">
        <v-btn
          size="small"
          variant="text"
          prepend-icon="mdi-crosshairs-gps"
          @click="useBrowserLocation"
        >
          Use my location
        </v-btn>
        <v-btn
          size="small"
          variant="text"
          prepend-icon="mdi-language-lua"
          @click="openLua"
        >
          True teleport (Lua)
        </v-btn>
      </div>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn
        color="primary"
        :loading="busy"
        @click="teleport"
      >
        Apply location
      </v-btn>
    </v-card-actions>

    <v-dialog
      v-model="showLua"
      max-width="760"
    >
      <v-card>
        <v-card-title>Lua sim:set_pose teleport helper</v-card-title>
        <v-card-text>
          <p class="mb-3 text-body-2">
            For a GPS-preserving teleport, enable scripting (<code>SCR_ENABLE = 1</code>),
            drop this script into the autopilot's <code>scripts/</code> folder, and restart.
            The extension writes <code>SIM_OPOS_*</code> over MAVLink for the script to read.
          </p>
          <pre class="lua-block">{{ luaScript }}</pre>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            variant="text"
            @click="showLua = false"
          >
            Close
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<style scoped>
.lua-block {
  background: rgba(0, 0, 0, 0.35);
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
