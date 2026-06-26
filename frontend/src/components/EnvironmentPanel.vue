<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { notify, notifyError } from '@/composables/notify'
import { EnvironmentApi } from '@/services/api'
import type { Environment, EnvironmentPreset } from '@/types/sitl'

// Form state keeps every field as a concrete number so it binds cleanly to sliders.
type EnvironmentForm = { [K in keyof Environment]-?: number }

const environment = ref<EnvironmentForm>({
  wind_speed: 0,
  wind_direction: 180,
  wind_turbulence: 0,
  wave_enable: 0,
  wave_amplitude: 0,
  wave_length: 10,
  wave_direction: 0,
  wave_speed: 0.5,
  tide_direction: 0,
  tide_speed: 0,
  speedup: 1,
})
const presets = ref<EnvironmentPreset[]>([])
const busy = ref(false)

const waveModes = [
  { title: 'Disabled', value: 0 },
  { title: 'Roll & pitch', value: 1 },
  { title: 'Roll, pitch & heave', value: 2 },
]

async function loadPresets(): Promise<void> {
  try {
    presets.value = await EnvironmentApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load presets')
  }
}

async function apply(): Promise<void> {
  busy.value = true
  try {
    const result = await EnvironmentApi.set(environment.value)
    notify(`Applied ${result.applied.length} parameter(s).`, 'success')
  } catch (error) {
    notifyError(error, 'Could not apply environment')
  } finally {
    busy.value = false
  }
}

async function applyPreset(preset: EnvironmentPreset): Promise<void> {
  busy.value = true
  try {
    for (const key of Object.keys(preset.environment) as (keyof Environment)[]) {
      const value = preset.environment[key]
      if (value != null) {
        environment.value[key] = value
      }
    }
    await EnvironmentApi.applyPreset(preset.name)
    notify(`Applied preset "${preset.name}".`, 'success')
  } catch (error) {
    notifyError(error, 'Could not apply preset')
  } finally {
    busy.value = false
  }
}

onMounted(loadPresets)
</script>

<template>
  <v-card>
    <v-card-title>
      <v-icon class="mr-2">
        mdi-weather-windy
      </v-icon>
      Ambient conditions
    </v-card-title>
    <v-card-text>
      <div class="text-subtitle-2 mb-2">
        Presets
      </div>
      <div class="d-flex flex-wrap ga-2 mb-4">
        <v-btn
          v-for="preset in presets"
          :key="preset.name"
          size="small"
          variant="tonal"
          :loading="busy"
          @click="applyPreset(preset)"
        >
          <v-tooltip
            activator="parent"
            location="top"
          >
            {{ preset.description }}
          </v-tooltip>
          {{ preset.name }}
        </v-btn>
      </div>

      <v-divider class="mb-4" />

      <div class="text-subtitle-2 mb-2">
        Wind
      </div>
      <v-slider
        v-model="environment.wind_speed"
        label="Speed"
        :min="0"
        :max="30"
        :step="0.5"
        thumb-label
        density="compact"
      >
        <template #append>
          <span class="text-caption">{{ environment.wind_speed }} m/s</span>
        </template>
      </v-slider>
      <v-slider
        v-model="environment.wind_direction"
        label="Direction"
        :min="0"
        :max="360"
        :step="1"
        thumb-label
        density="compact"
      >
        <template #append>
          <span class="text-caption">{{ environment.wind_direction }}°</span>
        </template>
      </v-slider>
      <v-slider
        v-model="environment.wind_turbulence"
        label="Turbulence"
        :min="0"
        :max="1"
        :step="0.05"
        thumb-label
        density="compact"
      />

      <v-divider class="my-3" />

      <div class="text-subtitle-2 mb-2">
        Waves &amp; current
      </div>
      <v-select
        v-model="environment.wave_enable"
        :items="waveModes"
        label="Wave mode"
        density="compact"
        variant="outlined"
        hide-details
        class="mb-3"
      />
      <v-slider
        v-model="environment.wave_amplitude"
        label="Wave amplitude"
        :min="0"
        :max="3"
        :step="0.1"
        thumb-label
        density="compact"
      >
        <template #append>
          <span class="text-caption">{{ environment.wave_amplitude }} m</span>
        </template>
      </v-slider>
      <v-slider
        v-model="environment.tide_speed"
        label="Current speed"
        :min="0"
        :max="3"
        :step="0.1"
        thumb-label
        density="compact"
      >
        <template #append>
          <span class="text-caption">{{ environment.tide_speed }} m/s</span>
        </template>
      </v-slider>

      <v-divider class="my-3" />

      <div class="text-subtitle-2 mb-2">
        Simulation
      </div>
      <v-slider
        v-model="environment.speedup"
        label="Speed-up"
        :min="0.1"
        :max="10"
        :step="0.1"
        thumb-label
        density="compact"
      >
        <template #append>
          <span class="text-caption">{{ environment.speedup }}×</span>
        </template>
      </v-slider>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn
        color="primary"
        :loading="busy"
        @click="apply"
      >
        Apply conditions
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
