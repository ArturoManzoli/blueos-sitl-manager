<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import BlueButtonGroup from '@/components/BlueButtonGroup.vue'
import BlueSwitch from '@/components/BlueSwitch.vue'
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

const presetButtons = computed(() =>
  presets.value.map((preset) => ({
    name: preset.name,
    onSelected: () => applyPreset(preset),
  })),
)

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
  <div class="flex flex-col gap-4">
    <div class="flex items-start gap-2 rounded-[6px] bg-[#0B508733] border border-[#0B508766] text-[#9ecbf0] text-xs px-3 py-2">
      <v-icon size="16">
        mdi-information-outline
      </v-icon>
      <span>
        SITL always boots at the BlueOS default home (Florianópolis). This relocates the
        running vehicle afterwards by moving its EKF origin.
      </span>
    </div>

    <BlueButtonGroup
      v-if="presetButtons.length"
      label="Presets"
      theme="dark"
      type="switch"
      :button-items="presetButtons"
    />

    <MapPicker
      v-model:latitude="location.latitude"
      v-model:longitude="location.longitude"
      :heading="location.heading"
    />

    <div class="grid grid-cols-2 gap-3">
      <v-text-field
        v-model.number="location.latitude"
        label="Latitude"
        type="number"
        density="compact"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="location.longitude"
        label="Longitude"
        type="number"
        density="compact"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="location.altitude"
        label="Altitude (m AMSL)"
        type="number"
        density="compact"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="location.heading"
        label="Heading (°)"
        type="number"
        density="compact"
        variant="outlined"
        hide-details
      />
    </div>

    <BlueSwitch
      v-model="disableSimulatedGps"
      name="disable-simulated-gps"
      label="Disable simulated GPS so the move sticks on the map"
      theme="dark"
      label-on="Yes"
      label-off="No"
    />

    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex gap-2">
        <v-btn
          size="small"
          prepend-icon="mdi-crosshairs-gps"
          @click="useBrowserLocation"
        >
          Use my location
        </v-btn>
        <v-btn
          size="small"
          prepend-icon="mdi-language-lua"
          @click="openLua"
        >
          True teleport (Lua)
        </v-btn>
      </div>
      <v-btn
        color="primary"
        size="small"
        :loading="busy"
        @click="teleport"
      >
        Apply location
      </v-btn>
    </div>

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
  </div>
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
