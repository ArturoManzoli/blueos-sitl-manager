<script setup lang="ts">
import { computed, ref } from 'vue'

import { BlueButtonGroup, BlueInput, BlueMenu, type BlueMenuItem, BluePromptDialog } from '@bluerobotics/bluevue'

import MapPicker from '@/components/MapPicker.vue'
import { hideLoading, showLoading } from '@/composables/loading'
import { notify, notifyError } from '@/composables/notify'
import { isSitl } from '@/composables/vehicleStatus'
import { LocationApi, MAX_PRESETS } from '@/services/api'
import type { LocationPreset, SitlLocation } from '@/types/sitl'

const emit = defineEmits<{ (event: 'changed'): void }>()

const location = ref<SitlLocation>({ latitude: -27.563, longitude: -48.459, altitude: 0, heading: 270 })
// Where the vehicle was last read to spawn, which is what the form is measured against to
// decide whether there is anything left to write.
const applied = ref<SitlLocation | null>(null)
const presets = ref<LocationPreset[]>([])
const busy = ref(false)
// Kept apart from busy so a read does not put the Apply button in a spin it has no part in.
const fetching = ref(false)

const presetMenuOpen = ref(false)
const saveDialogOpen = ref(false)
const renameDialogOpen = ref(false)
const importInput = ref<HTMLInputElement | null>(null)

// The preset a long press or right-click opened the actions menu on, and where to hang it.
const contextPreset = ref<LocationPreset | null>(null)
const contextTarget = ref<[number, number]>([0, 0])
const contextMenuOpen = ref(false)

// Close enough that the same spot typed by hand or picked off the map still counts.
function isSameSpot(a: SitlLocation, b: SitlLocation): boolean {
  return Math.abs(a.latitude - b.latitude) < 1e-5 && Math.abs(a.longitude - b.longitude) < 1e-5
}

// The preset last picked or created, which settles the highlight while the coordinates still
// sit on it. Renaming a built-in leaves a copy on the same spot as its source, so the spot
// alone no longer names one preset, and the row would light up whichever comes first.
const chosenPresetName = ref('')

// Which preset the coordinates in the form sit on, empty when they sit on none. Doubles as the
// button group's key, so the highlight follows coordinates that were typed or picked off the
// map rather than only ones that arrived by clicking a preset.
const matchedPresetName = computed(() => {
  const chosen = presets.value.find((preset) => preset.name === chosenPresetName.value)
  if (chosen && isSameSpot(chosen.location, location.value)) {
    return chosen.name
  }
  return presets.value.find((preset) => isSameSpot(preset.location, location.value))?.name ?? ''
})

// Fills the form from a preset, which is all selecting one means here.
function selectPreset(preset: LocationPreset): void {
  location.value = { ...preset.location }
  chosenPresetName.value = preset.name
}

const presetButtons = computed(() =>
  presets.value.map((preset) => ({
    name: preset.name,
    preSelected: preset.name === matchedPresetName.value,
    onSelected: () => selectPreset(preset),
  })),
)

const presetsFull = computed(() => presets.value.length >= MAX_PRESETS)
const fullHint = computed(() => (presetsFull.value ? `The row holds ${MAX_PRESETS} presets; delete one first` : undefined))

// The three-dots menu, which acts on the coordinates in the form rather than on any preset.
const presetActions = computed<BlueMenuItem[]>(() => [
  {
    title: 'Save current location as preset',
    icon: 'mdi-content-save-outline',
    disabled: presetsFull.value,
    hint: fullHint.value,
    action: () => (saveDialogOpen.value = true),
  },
  { title: 'Download preset file', icon: 'mdi-download-outline', action: downloadCurrentLocation },
  {
    title: 'Import preset file',
    icon: 'mdi-upload-outline',
    disabled: presetsFull.value,
    hint: fullHint.value,
    action: () => importInput.value?.click(),
  },
])

// What a long press offers for one preset, matching the vehicle presets: a built-in can be
// edited, renamed (as a copy) and exported, but only ever reverted, never deleted.
const contextItems = computed<BlueMenuItem[]>(() => {
  const preset = contextPreset.value
  if (!preset) {
    return []
  }
  const items: BlueMenuItem[] = [
    { title: 'Reload profile', icon: 'mdi-refresh', action: () => selectPreset(preset) },
    {
      title: 'Save current coordinates here',
      icon: 'mdi-content-save-outline',
      action: () => savePreset(preset.name),
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
    presets.value = await LocationApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load location presets')
  }
}

// Show where the vehicle is actually configured to spawn rather than a hardcoded guess.
async function refresh(): Promise<boolean> {
  try {
    location.value = await LocationApi.get()
    applied.value = { ...location.value }
    return true
  } catch (error) {
    notifyError(error, 'Could not read the spawn location')
    return false
  }
}

// The form is free to wander — a preset tried on, a pin dragged across the map — and this
// brings it back to the vehicle, which also says where the vehicle stands if it was moved
// from somewhere else in the meantime.
async function fetchFromVehicle(): Promise<void> {
  fetching.value = true
  try {
    if (await refresh()) {
      notify('Read the spawn location back from the vehicle.', 'info')
    }
  } finally {
    fetching.value = false
  }
}

// Every field counts, not just the coordinates: a heading is as much a change as a move.
const pendingChange = computed(() => {
  const current = applied.value
  return current === null || (Object.keys(current) as (keyof SitlLocation)[]).some((key) => current[key] !== location.value[key])
})

// Driven by the view, which keeps the loading overlay up until every panel has its data.
async function reload(): Promise<void> {
  await Promise.all([loadPresets(), refresh()])
}

defineExpose({ reload })

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

function onPresetContextMenu({ item, x, y }: { item: { name: string }; x: number; y: number }): void {
  const preset = presets.value.find((candidate) => candidate.name === item.name)
  if (!preset) {
    return
  }
  contextPreset.value = preset
  contextTarget.value = [x, y]
  contextMenuOpen.value = true
}

// Stores the coordinates in the form under a name. Saving onto a built-in's name shadows the
// shipped location until it is reverted, which is how a built-in gets edited.
async function savePreset(name: string): Promise<void> {
  showLoading(`Saving "${name}"…`)
  try {
    const saved = await LocationApi.savePreset({ name, location: { ...location.value } })
    await loadPresets()
    // Saved from the coordinates on screen, which another preset may already hold, so the row
    // is told which name to light up rather than left to work it out from the spot.
    chosenPresetName.value = saved.name
    notify(`Saved location preset "${saved.name}".`, 'success')
  } catch (error) {
    notifyError(error, 'Could not save the location preset')
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
    const renamed = await LocationApi.renamePreset(preset.name, newName)
    await loadPresets()
    if (preset.builtin) {
      // A built-in is renamed by copying it, so the row gains an entry on a spot that already
      // had one and nothing would look to have happened. Moving onto it is what shows it.
      selectPreset(renamed)
    } else if (chosenPresetName.value === preset.name) {
      chosenPresetName.value = newName
    }
    notify(
      preset.builtin
        ? `Copied "${preset.name}" to "${newName}"; the built-in stays in place.`
        : `Renamed "${preset.name}" to "${newName}".`,
      'success'
    )
  } catch (error) {
    notifyError(error, `Could not rename ${preset.name}`)
  } finally {
    hideLoading()
  }
}

async function removePreset(preset: LocationPreset): Promise<void> {
  showLoading(preset.builtin ? `Reverting "${preset.name}"…` : `Deleting preset "${preset.name}"…`)
  try {
    const result = await LocationApi.deletePreset(preset.name)
    await loadPresets()
    notify(result.detail, 'success')
  } catch (error) {
    notifyError(error, `Could not delete ${preset.name}`)
  } finally {
    hideLoading()
  }
}

function triggerDownload(preset: LocationPreset): void {
  const payload = { name: preset.name, location: preset.location }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${preset.name || 'sitl-location'}.json`
  link.click()
  URL.revokeObjectURL(url)
}

function downloadCurrentLocation(): void {
  triggerDownload({ name: 'Current location', location: { ...location.value } })
}

async function onImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  showLoading('Importing location preset…')
  try {
    const preset = JSON.parse(await file.text()) as LocationPreset
    const saved = await LocationApi.savePreset({ name: preset.name, location: preset.location })
    await loadPresets()
    // Moving onto what arrived is what shows it: the row would otherwise light up whichever
    // preset already sat on those coordinates, and an import onto a taken spot would read as
    // having done nothing.
    selectPreset(saved)
    notify(`Imported location preset "${saved.name}".`, 'success')
  } catch (error) {
    notifyError(error, 'Could not import the location preset')
  } finally {
    hideLoading()
  }
}

async function applyLocation(): Promise<void> {
  busy.value = true
  showLoading('Applying spawn location… the autopilot will restart, this can take up to a minute.')
  let applied = false
  try {
    const result = await LocationApi.set(location.value)
    notify(result.detail, result.success ? 'success' : 'warning')
    applied = true
  } catch (error) {
    notifyError(error, 'Could not set the spawn location')
  } finally {
    busy.value = false
    hideLoading()
  }
  // Announced after this overlay is down, so the re-read the view runs owns the next one
  // rather than the two of them fighting over a single global.
  if (applied) {
    emit('changed')
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <div class="flex items-center gap-2">
      <div class="flex-1 min-w-0">
        <BlueButtonGroup
          v-if="presetButtons.length"
          :key="`${presets.length}-${matchedPresetName}`"
          label="Presets"
          theme="dark"
          type="switch"
          :disabled="busy || fetching"
          :button-items="presetButtons"
          info-tooltip="Selecting a preset fills the coordinates below; Apply writes them to the vehicle's SIM_OPOS_* parameters and restarts the autopilot, after which SITL boots here every time. Hold or right-click a preset for its own actions."
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
            <v-icon>mdi-dots-vertical</v-icon>
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

    <MapPicker
      v-model:latitude="location.latitude"
      v-model:longitude="location.longitude"
      :heading="location.heading"
    />

    <div class="flex flex-col gap-3">
      <BlueInput
        v-model="location.latitude"
        name="latitude"
        label="Latitude"
        type="number"
        theme="dark"
        width="240px"
        suffix="°"
        :min="-90"
        :max="90"
        :step="0.000001"
      />
      <BlueInput
        v-model="location.longitude"
        name="longitude"
        label="Longitude"
        type="number"
        theme="dark"
        width="240px"
        suffix="°"
        :min="-180"
        :max="180"
        :step="0.000001"
      />
      <BlueInput
        v-model="location.altitude"
        name="altitude"
        label="Altitude"
        type="number"
        theme="dark"
        width="240px"
        suffix="m AMSL"
        :step="1"
        info-tooltip="Height above mean sea level the vehicle spawns at, written to SIM_OPOS_ALT."
      />
      <BlueInput
        v-model="location.heading"
        name="heading"
        label="Heading"
        type="number"
        theme="dark"
        width="240px"
        suffix="°"
        :min="0"
        :max="360"
        :step="1"
        info-tooltip="Direction the vehicle faces when it spawns, clockwise from north."
      />
    </div>

    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <v-btn
          size="small"
          prepend-icon="mdi-crosshairs-gps"
          :disabled="busy || fetching"
          @click="useBrowserLocation"
        >
          Use my location
        </v-btn>
        <v-btn
          class="ml-2"
          size="small"
          prepend-icon="mdi-refresh"
          :loading="fetching"
          :disabled="busy"
          @click="fetchFromVehicle"
        >
          Fetch from vehicle
        </v-btn>
      </div>
      <!-- Only the write waits for the simulator: picking, saving and exporting coordinates
           is the same work on any board. -->
      <v-btn
        color="primary"
        size="small"
        :loading="busy"
        :disabled="!isSitl || !pendingChange || fetching"
        @click="applyLocation"
      >
        Apply and restart
      </v-btn>
    </div>

    <BluePromptDialog
      v-model="saveDialogOpen"
      icon="mdi-map-marker-plus-outline"
      title="Save current location"
      subtitle="Stores the coordinates and heading below, so you can come back to this spot in one click."
      label="Preset name"
      hint="Saving does not move the vehicle."
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
          : `Renames ${contextPreset?.name}, keeping its coordinates and heading.`
      "
      @confirm="confirmRenamePreset"
    />
  </div>
</template>
