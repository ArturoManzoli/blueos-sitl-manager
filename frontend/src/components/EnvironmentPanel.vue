<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import BlueButtonGroup from '@/components/BlueButtonGroup.vue'
import BlueSelect from '@/components/BlueSelect.vue'
import BlueSlider from '@/components/BlueSlider.vue'
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
  { name: 'Disabled', value: 0 },
  { name: 'Roll & pitch', value: 1 },
  { name: 'Roll, pitch & heave', value: 2 },
]

const presetButtons = computed(() =>
  presets.value.map((preset) => ({
    name: preset.name,
    tooltip: preset.description,
    onSelected: () => applyPreset(preset),
  })),
)

async function loadPresets(): Promise<void> {
  try {
    presets.value = await EnvironmentApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load presets')
  }
}

// Populate the sliders with the conditions currently set on the vehicle.
async function refresh(): Promise<void> {
  try {
    const current = await EnvironmentApi.get()
    for (const key of Object.keys(current) as (keyof Environment)[]) {
      const value = current[key]
      if (value != null) {
        environment.value[key] = value
      }
    }
  } catch (error) {
    notifyError(error, 'Could not read current conditions')
  }
}

defineExpose({ refresh })

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

const metersPerSecond = (value: number): string => `${value.toFixed(1)} m/s`
const degrees = (value: number): string => `${value.toFixed(0)}°`
const meters = (value: number): string => `${value.toFixed(1)} m`
const speedupLabel = (value: number): string => `${value.toFixed(1)}×`

onMounted(() => {
  loadPresets()
  refresh()
})
</script>

<template>
  <div class="flex flex-col gap-5">
    <BlueButtonGroup
      v-if="presetButtons.length"
      label="Presets"
      theme="dark"
      type="switch"
      :button-items="presetButtons"
    />

    <div>
      <div class="text-xs uppercase tracking-wide text-[#ffffff66] mb-3">
        Wind
      </div>
      <div class="flex flex-col gap-3">
        <BlueSlider
          v-model="environment.wind_speed"
          name="wind-speed"
          label="Speed"
          theme="dark"
          width="380px"
          :min="0"
          :max="30"
          :step="0.5"
          :format-display="metersPerSecond"
        />
        <BlueSlider
          v-model="environment.wind_direction"
          name="wind-direction"
          label="Direction"
          theme="dark"
          width="380px"
          :min="0"
          :max="360"
          :step="1"
          :format-display="degrees"
        />
        <BlueSlider
          v-model="environment.wind_turbulence"
          name="wind-turbulence"
          label="Turbulence"
          theme="dark"
          width="380px"
          :min="0"
          :max="1"
          :step="0.05"
        />
      </div>
    </div>

    <div>
      <div class="text-xs uppercase tracking-wide text-[#ffffff66] mb-3">
        Waves &amp; current
      </div>
      <div class="flex flex-col gap-3">
        <BlueSelect
          v-model="environment.wave_enable"
          label="Wave mode"
          theme="dark"
          width="200px"
          :items="waveModes"
        />
        <BlueSlider
          v-model="environment.wave_amplitude"
          name="wave-amplitude"
          label="Wave amplitude"
          theme="dark"
          width="380px"
          :min="0"
          :max="3"
          :step="0.1"
          :format-display="meters"
        />
        <BlueSlider
          v-model="environment.tide_speed"
          name="current-speed"
          label="Current speed"
          theme="dark"
          width="380px"
          :min="0"
          :max="3"
          :step="0.1"
          :format-display="metersPerSecond"
        />
      </div>
    </div>

    <div>
      <div class="text-xs uppercase tracking-wide text-[#ffffff66] mb-3">
        Simulation
      </div>
      <BlueSlider
        v-model="environment.speedup"
        name="speedup"
        label="Speed-up"
        theme="dark"
        width="380px"
        :min="0.1"
        :max="10"
        :step="0.1"
        :format-display="speedupLabel"
      />
    </div>

    <div class="flex justify-end">
      <v-btn
        size="small"
        color="primary"
        :loading="busy"
        @click="apply"
      >
        Apply conditions
      </v-btn>
    </div>
  </div>
</template>
