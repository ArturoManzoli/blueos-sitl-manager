<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  type BannerContent,
  BlueBannerGroup,
  BlueButton,
  BlueButtonGroup,
  BlueIcon,
  BlueMenu,
  type BlueMenuItem,
  BluePromptDialog,
  BlueSelect,
  BlueSlider,
  BlueWindRose,
  useBlueLoading,
  useBlueSnackbar,
} from '@bluerobotics/bluevue'

import { isSitl, refreshVehicleStatus } from '@/composables/vehicleStatus'
import { EnvironmentApi, MAX_PRESETS } from '@/services/api'
import type { AppliedParams, Environment, EnvironmentPreset } from '@/types/sitl'

const { notify, notifyError } = useBlueSnackbar()
const { showLoading, hideLoading } = useBlueLoading()

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

const presetMenuOpen = ref(false)
const saveDialogOpen = ref(false)
const renameDialogOpen = ref(false)
const importInput = ref<HTMLInputElement | null>(null)

// The preset a long press or right-click opened the actions menu on, and where to hang it.
const contextPreset = ref<EnvironmentPreset | null>(null)
const contextTarget = ref<[number, number]>([0, 0])
const contextMenuOpen = ref(false)

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
const windNotes = computed<BannerContent[]>(() => {
  if (!frameKnown.value) {
    return []
  }
  if (model.value.noWind) {
    return [{ text: `The ${frame.value} frame ignores wind — it ${model.value.noWind}.`, severity: 'warning' }]
  }
  const notes: BannerContent[] = []
  if (model.value.surface && environment.value.wind_profile !== NO_WIND_PROFILE) {
    notes.push({
      text: `This profile fades the wind to nothing at ground level, and the ${frame.value} frame never leaves it.
        Set the profile to None for the wind to be felt.`,
      severity: 'warning',
    })
  }
  if (model.value.windIs) {
    notes.push({ text: model.value.windIs })
  }
  return notes
})

const waterNotes = computed<BannerContent[]>(() => {
  const because = model.value.noWater
  if (!frameKnown.value || !because) {
    return []
  }
  return [
    {
      text: `The ${frame.value} frame ignores waves and current — it ${because}. Switch to a motorboat or
        sailboat frame for them to move the vehicle.`,
      severity: 'warning',
    },
  ]
})

// The preset last picked or created, which settles the highlight while the sliders still sit on
// it. Two presets can describe the same conditions — a renamed built-in leaves a copy of them
// behind — so the values alone no longer name one preset, and the row would light up whichever
// comes first.
const chosenPresetName = ref('')

// A preset matches while every condition it names is on the sliders, so the highlight follows
// a value dragged onto or away from a preset rather than only a preset that was clicked.
function isStaged(preset: EnvironmentPreset): boolean {
  return (Object.keys(preset.environment) as (keyof Environment)[]).every(
    (key) => preset.environment[key] == null || preset.environment[key] === environment.value[key]
  )
}

const matchedPresetName = computed(() => {
  const chosen = presets.value.find((preset) => preset.name === chosenPresetName.value)
  if (chosen && isStaged(chosen)) {
    return chosen.name
  }
  return presets.value.find(isStaged)?.name ?? ''
})

const presetButtons = computed(() =>
  presets.value.map((preset) => ({
    name: preset.name,
    tooltip: preset.description,
    preSelected: preset.name === matchedPresetName.value,
    onSelected: () => stagePreset(preset),
  })),
)

const presetsFull = computed(() => presets.value.length >= MAX_PRESETS)
const fullHint = computed(() => (presetsFull.value ? `The row holds ${MAX_PRESETS} presets; delete one first` : undefined))

// The three-dots menu, which acts on the conditions on the sliders rather than on any preset.
const presetActions = computed<BlueMenuItem[]>(() => [
  {
    title: 'Save current conditions as preset',
    icon: 'mdi-content-save-outline',
    disabled: presetsFull.value,
    hint: fullHint.value,
    action: () => (saveDialogOpen.value = true),
  },
  { title: 'Download preset file', icon: 'mdi-download-outline', action: downloadCurrentConditions },
  {
    title: 'Import preset file',
    icon: 'mdi-upload-outline',
    disabled: presetsFull.value,
    hint: fullHint.value,
    action: () => importInput.value?.click(),
  },
])

// What a long press offers for one preset, matching the vehicle and location presets: a built-in
// can be edited, renamed (as a copy) and exported, but only ever reverted, never deleted.
const contextItems = computed<BlueMenuItem[]>(() => {
  const preset = contextPreset.value
  if (!preset) {
    return []
  }
  const items: BlueMenuItem[] = [
    { title: 'Reload profile', icon: 'mdi-refresh', action: () => stagePreset(preset) },
    {
      title: 'Save current conditions here',
      icon: 'mdi-content-save-outline',
      action: () => savePreset(preset.name, preset.description),
    },
    { title: 'Rename…', icon: 'mdi-rename-box-outline', action: () => (renameDialogOpen.value = true) },
    { title: 'Export to file', icon: 'mdi-download-outline', action: () => triggerDownload(preset) },
  ]
  if (preset.overridden) {
    items.push({
      title: 'Revert to built-in',
      icon: 'mdi-backup-restore',
      danger: true,
      action: () => removePreset(preset),
    })
  } else if (!preset.builtin) {
    items.push({
      title: 'Delete profile',
      icon: 'mdi-delete-outline',
      danger: true,
      action: () => removePreset(preset),
    })
  }
  return items
})

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
    notify(`${what}, but ${result.unverified.join(', ')} did not take. Try again.`, { severity: 'warning' })
    return
  }
  notify(`${what}.`, { severity: 'success' })
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
  chosenPresetName.value = preset.name
}

function onPresetContextMenu({ item, x, y }: { item: { name: string }; x: number; y: number }): void {
  const preset = presets.value.find((candidate) => candidate.name === item.name)
  if (!preset) {
    return
  }
  contextPreset.value = preset
  contextTarget.value = [x, y]
  contextMenuOpen.value = true
}

// Stores the conditions on the sliders under a name. Saving onto a built-in's name shadows the
// shipped conditions until it is reverted, which is how a built-in gets edited.
async function savePreset(name: string, description: string): Promise<void> {
  showLoading(`Saving "${name}"…`)
  try {
    const saved = await EnvironmentApi.savePreset({ name, description, environment: { ...environment.value } })
    await loadPresets()
    // Saved from the sliders, which another preset may already describe, so the row is told
    // which name to light up rather than left to work it out from the values.
    chosenPresetName.value = saved.name
    notify(`Saved conditions preset "${saved.name}".`, { severity: 'success' })
  } catch (error) {
    notifyError(error, 'Could not save the conditions preset')
  } finally {
    hideLoading()
  }
}

async function confirmRenamePreset(newName: string): Promise<void> {
  const preset = contextPreset.value
  if (!preset) {
    return
  }
  showLoading(`Renaming "${preset.name}"…`)
  try {
    const renamed = await EnvironmentApi.renamePreset(preset.name, newName)
    await loadPresets()
    if (preset.builtin) {
      // A built-in is renamed by copying it, so the row gains an entry describing conditions
      // that already had one and nothing would look to have happened. Moving onto it shows it.
      stagePreset(renamed)
    } else if (chosenPresetName.value === preset.name) {
      chosenPresetName.value = newName
    }
    notify(
      preset.builtin
        ? `Copied "${preset.name}" to "${newName}"; the built-in stays in place.`
        : `Renamed "${preset.name}" to "${newName}".`,
      { severity: 'success' }
    )
  } catch (error) {
    notifyError(error, `Could not rename ${preset.name}`)
  } finally {
    hideLoading()
  }
}

async function removePreset(preset: EnvironmentPreset): Promise<void> {
  showLoading(preset.builtin ? `Reverting "${preset.name}"…` : `Deleting preset "${preset.name}"…`)
  try {
    const result = await EnvironmentApi.deletePreset(preset.name)
    await loadPresets()
    notify(result.detail, { severity: 'success' })
  } catch (error) {
    notifyError(error, `Could not delete ${preset.name}`)
  } finally {
    hideLoading()
  }
}

function triggerDownload(preset: EnvironmentPreset): void {
  const payload = { name: preset.name, description: preset.description, environment: preset.environment }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${preset.name || 'sitl-conditions'}.json`
  link.click()
  URL.revokeObjectURL(url)
}

function downloadCurrentConditions(): void {
  triggerDownload({ name: 'Current conditions', description: '', environment: { ...environment.value } })
}

async function onImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  showLoading('Importing conditions preset…')
  try {
    const preset = JSON.parse(await file.text()) as EnvironmentPreset
    const saved = await EnvironmentApi.savePreset({
      name: preset.name,
      description: preset.description ?? '',
      environment: preset.environment,
    })
    await loadPresets()
    // Moving onto what arrived is what shows it: the row would otherwise light up whichever
    // preset already described those conditions, and an import would read as having done nothing.
    stagePreset(saved)
    notify(`Imported conditions preset "${saved.name}".`, { severity: 'success' })
  } catch (error) {
    notifyError(error, 'Could not import the conditions preset')
  } finally {
    hideLoading()
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
    <div class="order-1 flex items-center gap-2">
      <div class="flex-1 min-w-0">
        <BlueButtonGroup
          v-if="presetButtons.length"
          :key="`${presets.length}-${matchedPresetName}`"
          label="Presets"
          theme="dark"
          type="switch"
          density="regular"
          :disabled="busy || !isSitl"
          :button-items="presetButtons"
          info-tooltip="Picking a preset fills the sliders below with the conditions it describes; Apply writes them to the simulator. Hold or right-click a preset for its own actions."
          @context-menu="onPresetContextMenu"
        />
      </div>
      <BlueMenu
        v-model="presetMenuOpen"
        :items="presetActions"
      >
        <template #activator="{ props: menuProps }">
          <button
            v-bind="menuProps"
            class="shrink-0 rounded-[6px] px-1 py-1 text-[#ffffffaa] hover:text-white transition-colors"
            :class="busy ? 'opacity-50 pointer-events-none' : 'cursor-pointer'"
            title="Preset actions"
          >
            <BlueIcon name="mdi-dots-vertical" />
          </button>
        </template>
      </BlueMenu>
      <BlueMenu
        v-model="contextMenuOpen"
        :items="contextItems"
        :target="contextTarget"
      />
      <input
        ref="importInput"
        type="file"
        accept="application/json,.json"
        class="hidden"
        @change="onImportFileSelected"
      >
    </div>

    <div class="order-2">
      <!-- Each category carries the rule above it, which is what keeps the line where the groups
           reorder to: one that sinks below Apply takes its divider with it. -->
      <div class="mx-auto mb-4 h-px w-[70%] bg-[#ffffff0b]" />
      <div class="text-base font-bold uppercase tracking-wide text-[#989898] mt-[5px] mb-[17px] truncate">
        Simulation
      </div>
      <BlueSlider
        v-model="environment.speedup"
        name="speedup"
        label="Speed-up"
        theme="dark"
        :min="0.1"
        :max="10"
        :step="0.1"
        :disabled="!isSitl"
        :format-display="speedupLabel"
      />
    </div>

    <div :class="windApplies ? 'order-3' : 'order-5'">
      <div class="mx-auto mb-4 h-px w-[70%] bg-[#ffffff0b]" />
      <div class="text-base font-bold uppercase tracking-wide text-[#989898] mt-[5px] mb-[17px] truncate">
        Wind
      </div>
      <div class="flex flex-col gap-3">
        <BlueBannerGroup
          v-if="windNotes.length > 0"
          :banners="windNotes"
        />
        <BlueSlider
          v-model="environment.wind_speed"
          name="wind-speed"
          label="Speed"
          theme="dark"
          :min="0"
          :max="30"
          :step="0.5"
          :disabled="!windApplies"
          :format-display="metersPerSecond"
        />
        <BlueWindRose
          v-model="environment.wind_direction"
          name="wind-direction"
          label="Direction"
          theme="dark"
          width="240px"
          :disabled="!windApplies"
        />
        <BlueSlider
          v-model="environment.wind_elevation"
          name="wind-elevation"
          label="Vertical angle"
          theme="dark"
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
          :min="0"
          :max="300"
          :step="5"
          :disabled="!altitudeApplies"
          :format-display="meters"
        />
      </div>
    </div>

    <div :class="waterApplies ? 'order-3' : 'order-5'">
      <div class="mx-auto mb-4 h-px w-[70%] bg-[#ffffff0b]" />
      <div class="text-base font-bold uppercase tracking-wide text-[#989898] mt-[5px] mb-[17px] truncate">
        Waves &amp; current
      </div>
      <div class="flex flex-col gap-3">
        <BlueBannerGroup
          v-if="waterNotes.length > 0"
          :banners="waterNotes"
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
          :min="0"
          :max="3"
          :step="0.1"
          :disabled="!waterApplies"
          :format-display="meters"
        />
        <BlueWindRose
          v-model="environment.wave_direction"
          name="wave-direction"
          label="Wave direction"
          theme="dark"
          width="240px"
          :disabled="!waterApplies"
        />
        <BlueSlider
          v-model="environment.tide_speed"
          name="current-speed"
          label="Current speed"
          theme="dark"
          :min="0"
          :max="3"
          :step="0.1"
          :disabled="!waterApplies"
          :format-display="metersPerSecond"
        />
        <BlueWindRose
          v-model="environment.tide_direction"
          name="current-direction"
          label="Current direction"
          theme="dark"
          width="240px"
          :disabled="!waterApplies"
        />
      </div>
    </div>

    <!-- Whatever the frame ignores sits below this row: the groups it can act on come first,
         and Apply draws the line between what is worth setting and what is only explained. -->
    <div class="order-4 flex justify-end">
      <BlueButton
        variant="filled"
        theme="dark"
        :loading="busy"
        :disabled="!isSitl || !pendingChange"
        @click="apply"
      >
        Apply conditions
      </BlueButton>
    </div>

    <BluePromptDialog
      v-model="saveDialogOpen"
      icon="mdi-weather-partly-cloudy"
      title="Save current conditions"
      subtitle="Stores every value on the sliders below, so you can come back to these conditions in one click."
      label="Preset name"
      notes-label="Description (optional)"
      hint="Saving does not write anything to the simulator."
      @confirm="savePreset"
    />

    <BluePromptDialog
      v-model="renameDialogOpen"
      icon="mdi-rename-box-outline"
      title="Rename preset"
      label="New name"
      confirm-label="Rename"
      :initial="contextPreset?.name"
      :subtitle="
        contextPreset?.builtin
          ? `${contextPreset.name} is built in and stays where it is, so this saves a copy under the new name.`
          : `Renames ${contextPreset?.name}, keeping the conditions it describes.`
      "
      @confirm="confirmRenamePreset"
    />
  </div>
</template>
