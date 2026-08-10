<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import BlueButtonGroup from '@/components/BlueButtonGroup.vue'
import MapPicker from '@/components/MapPicker.vue'
import { hideLoading, showLoading } from '@/composables/loading'
import { notify, notifyError } from '@/composables/notify'
import { LocationApi } from '@/services/api'
import type { LocationPreset, SitlLocation } from '@/types/sitl'

const emit = defineEmits<{ (event: 'changed'): void }>()

const location = ref<SitlLocation>({ latitude: -27.563, longitude: -48.459, altitude: 0, heading: 270 })
const presets = ref<LocationPreset[]>([])
const busy = ref(false)

const presetButtons = computed(() =>
  presets.value.map((preset) => ({
    name: preset.name,
    onSelected: () => {
      location.value = { ...preset.location }
    },
  })),
)

async function loadPresets(): Promise<void> {
  try {
    presets.value = await LocationApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load location presets')
  }
}

// Show where the vehicle is actually configured to spawn rather than a hardcoded guess.
async function refresh(): Promise<void> {
  try {
    location.value = await LocationApi.get()
  } catch (error) {
    notifyError(error, 'Could not read the spawn location')
  }
}

defineExpose({ refresh })

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

async function applyLocation(): Promise<void> {
  busy.value = true
  showLoading('Applying spawn location… the autopilot will restart, this can take up to a minute.')
  try {
    const result = await LocationApi.set(location.value)
    notify(result.detail, result.success ? 'success' : 'warning')
    emit('changed')
  } catch (error) {
    notifyError(error, 'Could not set the spawn location')
  } finally {
    busy.value = false
    hideLoading()
  }
}

onMounted(() => {
  loadPresets()
  refresh()
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <BlueButtonGroup
      v-if="presetButtons.length"
      label="Presets"
      theme="dark"
      type="switch"
      :disabled="busy"
      :button-items="presetButtons"
      info-tooltip="Applying writes the spawn location to the vehicle's SIM_OPOS_* parameters and restarts the autopilot. SITL then boots here every time, until you change it again."
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

    <div class="flex items-center justify-between gap-2">
      <v-btn
        size="small"
        prepend-icon="mdi-crosshairs-gps"
        :disabled="busy"
        @click="useBrowserLocation"
      >
        Use my location
      </v-btn>
      <v-btn
        color="primary"
        size="small"
        :loading="busy"
        @click="applyLocation"
      >
        Apply and restart
      </v-btn>
    </div>
  </div>
</template>
