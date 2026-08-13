<script setup lang="ts">
import { computed, ref } from 'vue'

import { BlueButtonGroup, BlueSelect, BlueSlider } from '@bluerobotics/bluevue'

import BlueBanner from '@/components/BlueBanner.vue'
import { notify, notifyError } from '@/composables/notify'
import { isSitl, refreshVehicleStatus } from '@/composables/vehicleStatus'
import { EnvironmentApi } from '@/services/api'
import type { AppliedParams, Environment, EnvironmentPreset } from '@/types/sitl'

// Form state keeps every field as a concrete number so it binds cleanly to sliders.
type EnvironmentForm = { [K in keyof Environment]-?: number }

const environment = ref<EnvironmentForm>({
  wind_speed: 0,
  wind_direction: 180,
  wind_turbulence: 0,
  wind_elevation: 0,
  wind_variation: 5,
  wind_profile: 1,
  wind_full_altitude: 60,
  wave_enable: 0,
  wave_amplitude: 0,
  wave_length: 10,
  wave_direction: 0,
  wave_speed: 0.5,
  tide_direction: 0,
  tide_speed: 0,
  speedup: 1,
})
// The conditions the vehicle was last read to be running, which is what the sliders are
// measured against to decide whether there is anything left to write.
const applied = ref<EnvironmentForm | null>(null)
const presets = ref<EnvironmentPreset[]>([])
const busy = ref(false)
const frame = ref<string | null>(null)

const waveModes = [
  { name: 'Disabled', value: 0 },
  { name: 'Roll & pitch', value: 1 },
  { name: 'Roll, pitch & heave', value: 2 },
]

// SIM_WIND_T. The square law scales wind by the square root of the height above ground, so it
// leaves nothing at all at the surface — which is where boats, rovers and subs live.
const NO_WIND_PROFILE = 1
const windProfiles = [
  { name: 'None', value: NO_WIND_PROFILE },
  { name: 'Square law', value: 0 },
  { name: 'Linear', value: 2 },
]

// What each ArduPilot simulation model does with the ambient parameters, keyed by the prefix of
// the SITL frames it backs. Frames that match nothing here are aircraft, which fly in the wind
// and know nothing about water. `surface` marks the models that never gain altitude, and so read
// no wind at all unless the profile above is switched off.
interface FrameModel {
  // Why the model makes nothing of the group, which is also what marks the group unavailable.
  // Each completes "the <frame> frame ignores <the group> — it …".
  noWind?: string
  noWater?: string
  // The model never gains altitude, and so reads no wind at all unless the profile is off.
  surface: boolean
  // Said up front where the wind settings drive something other than air.
  windIs?: string
}

const FRAME_MODELS: (FrameModel & { prefix: string })[] = [
  { prefix: 'sailboat', surface: true },
  {
    prefix: 'motorboat',
    surface: true,
    noWind: 'carries no sail area, so wind reaches its wind vane and nothing else',
  },
  {
    prefix: 'vectored',
    surface: true,
    noWater: 'runs below the surface waves shape',
    windIs: 'On a sub the wind vector is the water itself: it drags the hull along like a current.',
  },
  { prefix: 'rover', surface: true, noWind: 'drives on dry land', noWater: 'drives on dry land' },
  { prefix: 'balancebot', surface: true, noWind: 'drives on dry land', noWater: 'drives on dry land' },
]
const AIRCRAFT: FrameModel = { surface: false, noWater: 'flies nowhere near water' }

const model = computed<FrameModel>(() => {
  const name = frame.value?.toLowerCase() ?? ''
  return FRAME_MODELS.find((entry) => name.startsWith(entry.prefix)) ?? AIRCRAFT
})

// Nothing is adjustable on a real board, where these parameters do not exist. Which of them the
// simulator would honour is only known once the frame has been read, so until then the panel is
// permissive rather than a wall of grey.
const frameKnown = computed(() => isSitl.value && frame.value !== null)
const windApplies = computed(() => isSitl.value && (!frameKnown.value || !model.value.noWind))
const waterApplies = computed(() => isSitl.value && (!frameKnown.value || !model.value.noWater))
const altitudeApplies = computed(() => windApplies.value && environment.value.wind_profile !== NO_WIND_PROFILE)

// A grey slider says what cannot be changed but not why, so each group explains itself: what the
// running frame ignores outright, the wind it would take but silently scale away, and what the
// wind stands in for on a vehicle that has no air around it.
interface Note {
  text: string
  warning: boolean
}

const windNotes = computed<Note[]>(() => {
  if (!frameKnown.value) {
    return []
  }
  if (model.value.noWind) {
    return [{ text: `The ${frame.value} frame ignores wind — it ${model.value.noWind}.`, warning: true }]
  }
  const notes: Note[] = []
  if (model.value.surface && environment.value.wind_profile !== NO_WIND_PROFILE) {
    notes.push({
      text: `This profile fades the wind to nothing at ground level, and the ${frame.value} frame never leaves it.
        Set the profile to None for the wind to be felt.`,
      warning: true,
    })
  }
  if (model.value.windIs) {
    notes.push({ text: model.value.windIs, warning: false })
  }
  return notes
})

const waterNotes = computed<Note[]>(() => {
  const because = model.value.noWater
  if (!frameKnown.value || !because) {
    return []
  }
  return [
    {
      text: `The ${frame.value} frame ignores waves and current — it ${because}. Switch to a motorboat or
        sailboat frame for them to move the vehicle.`,
      warning: true,
    },
  ]
})

// A preset matches while every condition it names is on the sliders, so the highlight follows
// a value dragged onto or away from a preset rather than only a preset that was clicked.
const matchedPresetName = computed(
  () =>
    presets.value.find((preset) =>
      (Object.keys(preset.environment) as (keyof Environment)[]).every(
        (key) => preset.environment[key] == null || preset.environment[key] === environment.value[key]
      )
    )?.name ?? ''
)

const presetButtons = computed(() =>
  presets.value.map((preset) => ({
    name: preset.name,
    tooltip: preset.description,
    preSelected: preset.name === matchedPresetName.value,
    onSelected: () => stagePreset(preset),
  })),
)

async function loadPresets(): Promise<void> {
  try {
    presets.value = await EnvironmentApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load presets')
  }
}

// Populate the sliders with the conditions currently set on the vehicle. The SITL frame comes
// along because it decides which of them the simulation model can do anything with.
async function refresh(): Promise<void> {
  try {
    const [current, status] = await Promise.all([EnvironmentApi.get(), refreshVehicleStatus()])
    frame.value = status.frame
    for (const key of Object.keys(current) as (keyof Environment)[]) {
      const value = current[key]
      if (value != null) {
        environment.value[key] = value
      }
    }
    applied.value = { ...environment.value }
  } catch (error) {
    notifyError(error, 'Could not read current conditions')
  }
}

const pendingChange = computed(() => {
  const current = applied.value
  return (
    current === null ||
    (Object.keys(current) as (keyof EnvironmentForm)[]).some((key) => current[key] !== environment.value[key])
  )
})

// Every value is read back after being written, so a name missing from `applied` is one the
// simulator is not running, which is worth saying rather than reporting a clean success.
function reportApplied(result: AppliedParams, what: string): void {
  if (result.unverified.length) {
    notify(`${what}, but ${result.unverified.join(', ')} did not take. Try again.`, 'warning')
    return
  }
  notify(`${what}.`, 'success')
}

// Driven by the view, which keeps the loading overlay up until every panel has its data.
async function reload(): Promise<void> {
  await Promise.all([loadPresets(), refresh()])
}

defineExpose({ reload })

async function apply(): Promise<void> {
  busy.value = true
  try {
    const result = await EnvironmentApi.set(environment.value)
    applied.value = { ...environment.value }
    reportApplied(result, `Applied ${result.applied.length} parameter(s)`)
  } catch (error) {
    notifyError(error, 'Could not apply environment')
  } finally {
    busy.value = false
  }
}

// Presets fill the sliders and stop there, the way the spawn locations do: what the panel
// shows is then what Apply will write, whether it came from a preset or from a slider.
function stagePreset(preset: EnvironmentPreset): void {
  for (const key of Object.keys(preset.environment) as (keyof Environment)[]) {
    const value = preset.environment[key]
    if (value != null) {
      environment.value[key] = value
    }
  }
}

const metersPerSecond = (value: number): string => `${value.toFixed(1)} m/s`
const degrees = (value: number): string => `${value.toFixed(0)}°`
const meters = (value: number): string => `${value.toFixed(1)} m`
const seconds = (value: number): string => `${value.toFixed(1)} s`
const speedupLabel = (value: number): string => `${value.toFixed(1)}×`
</script>

<template>
  <div class="flex flex-col gap-5">
    <BlueButtonGroup
      v-if="presetButtons.length"
      :key="matchedPresetName"
      class="order-1"
      label="Presets"
      theme="dark"
      type="switch"
      density="regular"
      :disabled="busy || !isSitl"
      :button-items="presetButtons"
      info-tooltip="Picking a preset fills the sliders below with the conditions it describes; Apply writes them to the simulator."
    />

    <div class="order-2">
      <div class="text-xs uppercase tracking-wide text-[#ffffff66] mb-3 truncate">
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
        :disabled="!isSitl"
        :format-display="speedupLabel"
      />
    </div>

    <div :class="windApplies ? 'order-3' : 'order-5'">
      <div class="text-xs uppercase tracking-wide text-[#ffffff66] mb-3 truncate">
        Wind
      </div>
      <div class="flex flex-col gap-3">
        <BlueBanner
          v-for="note in windNotes"
          :key="note.text"
          :text="note.text"
          :severity="note.warning ? 'warning' : 'info'"
          :expanded="false"
        />
        <BlueSlider
          v-model="environment.wind_speed"
          name="wind-speed"
          label="Speed"
          theme="dark"
          width="380px"
          :min="0"
          :max="30"
          :step="0.5"
          :disabled="!windApplies"
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
          :disabled="!windApplies"
          :format-display="degrees"
        />
        <BlueSlider
          v-model="environment.wind_elevation"
          name="wind-elevation"
          label="Vertical angle"
          theme="dark"
          width="380px"
          :min="-90"
          :max="90"
          :step="1"
          :disabled="!windApplies"
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
          :disabled="!windApplies"
        />
        <BlueSlider
          v-model="environment.wind_variation"
          name="wind-variation"
          label="Variation time"
          theme="dark"
          width="380px"
          :min="0.1"
          :max="60"
          :step="0.1"
          :disabled="!windApplies"
          :format-display="seconds"
        />
        <BlueSelect
          v-model="environment.wind_profile"
          label="Altitude profile"
          theme="dark"
          width="200px"
          :items="windProfiles"
          :disabled="!windApplies"
          info-tooltip="How the wind above builds with height. None blows at full speed from the ground up; square law and linear taper it off towards the surface, which is where a boat, rover or sub would end up with no wind at all."
        />
        <BlueSlider
          v-model="environment.wind_full_altitude"
          name="wind-full-altitude"
          label="Full-speed altitude"
          theme="dark"
          width="380px"
          :min="0"
          :max="300"
          :step="5"
          :disabled="!altitudeApplies"
          :format-display="meters"
        />
      </div>
    </div>

    <div :class="waterApplies ? 'order-3' : 'order-5'">
      <div class="text-xs uppercase tracking-wide text-[#ffffff66] mb-3 truncate">
        Waves &amp; current
      </div>
      <div class="flex flex-col gap-3">
        <BlueBanner
          v-for="note in waterNotes"
          :key="note.text"
          :text="note.text"
          :severity="note.warning ? 'warning' : 'info'"
          :expanded="false"
        />
        <BlueSelect
          v-model="environment.wave_enable"
          label="Wave mode"
          theme="dark"
          width="200px"
          :items="waveModes"
          :disabled="!waterApplies"
          info-tooltip="Waves and current only move the vehicle while it is armed — ArduPilot keeps the water still until then so the gyros can initialise — and only on a boat frame (motorboat or sailboat), the one simulation model that has water in it."
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
          :disabled="!waterApplies"
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
          :disabled="!waterApplies"
          :format-display="metersPerSecond"
        />
        <BlueSlider
          v-model="environment.tide_direction"
          name="current-direction"
          label="Current direction"
          theme="dark"
          width="380px"
          :min="0"
          :max="360"
          :step="1"
          :disabled="!waterApplies"
          :format-display="degrees"
        />
      </div>
    </div>

    <!-- Whatever the frame ignores sits below this row: the groups it can act on come first,
         and Apply draws the line between what is worth setting and what is only explained. -->
    <div class="order-4 flex justify-end">
      <v-btn
        size="small"
        color="primary"
        :loading="busy"
        :disabled="!isSitl || !pendingChange"
        @click="apply"
      >
        Apply conditions
      </v-btn>
    </div>
  </div>
</template>
