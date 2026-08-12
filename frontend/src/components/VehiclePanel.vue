<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import ApplyProgressDialog from '@/components/ApplyProgressDialog.vue'
import BlueButtonGroup from '@/components/BlueButtonGroup.vue'
import BlueSelect from '@/components/BlueSelect.vue'
import NamePromptDialog from '@/components/NamePromptDialog.vue'
import PresetMenu, { type PresetMenuItem } from '@/components/PresetMenu.vue'
import { hideLoading, showLoading } from '@/composables/loading'
import { notify, notifyError } from '@/composables/notify'
import { isSitl, refreshVehicleStatus } from '@/composables/vehicleStatus'
import { withWaitCursor } from '@/composables/waitCursor'
import { MAX_PRESETS, VehicleApi } from '@/services/api'
import type { ApplyJob, VehiclePreset, VehicleType } from '@/types/sitl'

const emit = defineEmits<{ (event: 'changed'): void }>()

const CUSTOM_PRESET = 'Custom'

interface PresetButton {
  name: string
  tooltip?: string
  preSelected?: boolean
  onSelected: () => void
}

const vehicleTypes: VehicleType[] = ['Sub', 'Rover', 'Plane', 'Copter']
const frames = ref<string[]>([])
const presets = ref<VehiclePreset[]>([])
const selectedFrame = ref<string | null>(null)
const selectedVehicle = ref<VehicleType>('Sub')
const busy = ref(false)
// The selectors apply on change, so they are also written from the running vehicle's
// state. This guards the watchers from firing on those programmatic updates.
const syncing = ref(false)
const progressJob = ref<ApplyJob | null>(null)
const progressOpen = ref(false)
// Which preset the running vehicle matches; 'Custom' when it matches none.
const activePresetName = ref<string>(CUSTOM_PRESET)
// The last preset the user explicitly applied via the button group. Detection only sees
// built-in presets (a custom preset is a full dump of the built-in it derives from and
// shares its frame-defining parameter), so without this it would downgrade an applied
// custom preset to its built-in cousin and hide the delete action.
const explicitPresetName = ref<string | null>(null)

const presetMenuOpen = ref(false)
const saveDialogOpen = ref(false)
const importInput = ref<HTMLInputElement | null>(null)

// The preset a long press or right-click opened the actions menu on, and where to hang it.
const contextPreset = ref<VehiclePreset | null>(null)
const contextTarget = ref<[number, number]>([0, 0])
const contextMenuOpen = ref(false)
const renameDialogOpen = ref(false)

const vehicleItems = computed(() => vehicleTypes.map((value) => ({ name: value, value })))
// Keep the running frame selectable even when it is not one of the curated SITL frames,
// so the dropdown can show what the vehicle is actually configured with.
const frameItems = computed(() => {
  const names = [...frames.value]
  if (selectedFrame.value && !names.includes(selectedFrame.value)) {
    names.unshift(selectedFrame.value)
  }
  return names.map((value) => ({ name: value, value }))
})
const presetButtons = computed<PresetButton[]>(() => {
  const buttons: PresetButton[] = presets.value.map((preset) => ({
    name: preset.name,
    tooltip: preset.description,
    preSelected: activePresetName.value === preset.name,
    onSelected: () => {
      applyPreset(preset)
    },
  }))
  buttons.push({
    name: CUSTOM_PRESET,
    tooltip: 'The current configuration does not match a preset',
    preSelected: activePresetName.value === CUSTOM_PRESET,
    onSelected: () => undefined,
  })
  return buttons
})

const presetsFull = computed(() => presets.value.length >= MAX_PRESETS)
const fullHint = computed(() => (presetsFull.value ? `The row holds ${MAX_PRESETS} presets; delete one first` : undefined))

// Applying anything here reconfigures the autopilot, which on a real board would mean
// reflashing it, so the vehicle actions wait for the simulator. Everything that only moves
// presets around — importing, renaming, exporting a stored one, deleting — stays available.
const locked = computed(() => busy.value || !isSitl.value)
const sitlHint = computed(() => (isSitl.value ? undefined : 'Only available on a SITL board'))
const vehicleActionHint = computed(() => fullHint.value ?? sitlHint.value)

// The three-dots menu, which acts on the vehicle rather than on any one preset.
const presetActions = computed<PresetMenuItem[]>(() => [
  {
    title: 'Save current config as preset',
    icon: 'mdi-content-save-outline',
    disabled: presetsFull.value || !isSitl.value,
    hint: vehicleActionHint.value,
    action: () => (saveDialogOpen.value = true),
  },
  {
    title: 'Download preset file',
    icon: 'mdi-download-outline',
    disabled: !isSitl.value,
    hint: sitlHint.value,
    action: downloadPreset,
  },
  {
    title: 'Import preset file',
    icon: 'mdi-upload-outline',
    disabled: presetsFull.value,
    hint: fullHint.value,
    action: () => importInput.value?.click(),
  },
])

// What a long press offers for one preset. A built-in can be reloaded, edited, renamed (as a
// copy) and exported, but never deleted: an edited one is reverted to its shipped definition
// instead, which is what keeps the curated presets impossible to lose.
const contextItems = computed<PresetMenuItem[]>(() => {
  const preset = contextPreset.value
  if (!preset) {
    return []
  }
  const items: PresetMenuItem[] = [
    {
      title: 'Reload profile',
      icon: 'mdi-refresh',
      disabled: !isSitl.value,
      hint: sitlHint.value,
      action: () => applyPreset(preset),
    },
    {
      title: 'Save current config here',
      icon: 'mdi-content-save-outline',
      disabled: !isSitl.value,
      hint: sitlHint.value,
      action: () => overwritePreset(preset),
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

async function loadFrames(): Promise<void> {
  try {
    frames.value = await VehicleApi.frames()
  } catch (error) {
    notifyError(error, 'Could not load frames')
  }
}

async function loadPresets(): Promise<void> {
  try {
    presets.value = await VehicleApi.presets()
  } catch (error) {
    notifyError(error, 'Could not load vehicle presets')
  }
}

async function loadActivePreset(): Promise<void> {
  try {
    const detected = await VehicleApi.activePreset()
    const explicit = presets.value.find((preset) => preset.name === explicitPresetName.value)
    // What was applied wins over detection in two cases: a custom preset, which detection
    // cannot recognize (it is a dump of the built-in it came from and shares its
    // frame-defining parameter, so it would be reported as its cousin), and a detection that
    // came back empty, which is a parameter read that did not answer rather than a vehicle
    // that matches nothing.
    if (explicit && (!explicit.builtin || !detected)) {
      activePresetName.value = explicit.name
      return
    }
    activePresetName.value = detected ?? CUSTOM_PRESET
  } catch {
    // Leave the row as it was: an unanswered read is not evidence the vehicle changed.
  }
}

// ArduPilot Manager reports the type as e.g. "ArduSub"/"ArduRover"; match it to one of
// our short vehicle labels by substring.
function vehicleTypeFromFirmware(firmware: string | null): VehicleType | null {
  if (!firmware) {
    return null
  }
  return vehicleTypes.find((type) => firmware.toLowerCase().includes(type.toLowerCase())) ?? null
}

// Mirror the manual-configuration fields onto whatever the vehicle currently runs.
async function syncFromStatus(): Promise<void> {
  syncing.value = true
  try {
    const status = await refreshVehicleStatus()
    const vehicle = vehicleTypeFromFirmware(status.firmware_vehicle_type)
    if (vehicle) {
      selectedVehicle.value = vehicle
    }
    if (status.frame) {
      selectedFrame.value = status.frame
    }
  } catch {
    // Status is surfaced (and its errors reported) by the StatusPanel; stay quiet here.
  } finally {
    await nextTick()
    syncing.value = false
  }
}

// Driven by the view rather than onMounted, which is what lets the overlay stay up until
// every panel has something to show. The preset list is read before the active preset is
// resolved, since resolving it means matching against that list.
async function reload(): Promise<void> {
  await Promise.all([loadFrames(), loadPresets()])
  await Promise.all([loadActivePreset(), syncFromStatus()])
}

defineExpose({ reload })

// Every configuration change runs as a backend job; start it, then hand the first
// snapshot to the progress dialog, which polls the rest. Starting one takes long enough to
// notice, and nothing has appeared yet at that point, so the pointer carries the wait.
async function startJob(start: () => Promise<ApplyJob>, failureMessage: string): Promise<boolean> {
  busy.value = true
  try {
    progressJob.value = await withWaitCursor(start)
    progressOpen.value = true
    return true
  } catch (error) {
    notifyError(error, failureMessage)
    busy.value = false
    return false
  }
}

async function applyPreset(preset: VehiclePreset): Promise<void> {
  if (await startJob(() => VehicleApi.applyPreset(preset.name), `Could not apply ${preset.name}`)) {
    activePresetName.value = preset.name
    explicitPresetName.value = preset.name
  }
}

async function applyFrame(frame: string): Promise<void> {
  if (await startJob(() => VehicleApi.setFrame(frame), 'Could not set frame')) {
    activePresetName.value = CUSTOM_PRESET
    explicitPresetName.value = null
  }
}

async function applyVehicle(vehicle: VehicleType): Promise<void> {
  if (await startJob(() => VehicleApi.setType(vehicle), 'Could not switch vehicle type')) {
    activePresetName.value = CUSTOM_PRESET
    explicitPresetName.value = null
  }
}

// A finished job leaves its result on screen until the user dismisses it, so the page is
// re-read when the dialog closes rather than when the job ends: everything on the page still
// describes the vehicle that existed before the change, and throwing the overlay over a
// dialog somebody is still reading would hide the outcome they were looking at. Set on a
// failed job too — a half-applied change moves the page just as much as a whole one.
const changedByJob = ref(false)

function onJobFinished(job: ApplyJob): void {
  busy.value = false
  changedByJob.value = true
  notify(job.detail, job.state === 'succeeded' ? 'success' : 'warning')
}

watch(progressOpen, (open) => {
  if (open || !changedByJob.value) {
    return
  }
  changedByJob.value = false
  emit('changed')
})

// Retried from the progress dialog, so the selectors go back to being locked.
function onJobRestarted(job: ApplyJob): void {
  progressJob.value = job
  busy.value = true
}

watch(selectedVehicle, (vehicle, previous) => {
  if (!syncing.value && previous && vehicle !== previous) {
    applyVehicle(vehicle)
  }
})

watch(selectedFrame, (frame, previous) => {
  if (!syncing.value && previous && frame && frame !== previous) {
    applyFrame(frame)
  }
})

async function confirmSavePreset(name: string, description: string): Promise<void> {
  showLoading('Saving current configuration as a preset… reading all parameters.')
  try {
    const preset = await VehicleApi.savePreset(name, description)
    await loadPresets()
    await loadActivePreset()
    notify(`Saved preset "${preset.name}" with ${Object.keys(preset.parameters).length} parameters.`, 'success')
  } catch (error) {
    notifyError(error, 'Could not save preset')
  } finally {
    hideLoading()
  }
}

function triggerDownload(preset: VehiclePreset): void {
  const blob = new Blob([JSON.stringify(preset, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${preset.name || 'sitl-preset'}.json`
  link.click()
  URL.revokeObjectURL(url)
}

async function downloadPreset(): Promise<void> {
  showLoading('Reading current configuration… capturing all parameters.')
  try {
    triggerDownload(await VehicleApi.currentConfig())
  } catch (error) {
    notifyError(error, 'Could not export configuration')
  } finally {
    hideLoading()
  }
}

function onPresetContextMenu({ item, x, y }: { item: { name: string }; x: number; y: number }): void {
  const preset = presets.value.find((candidate) => candidate.name === item.name)
  // The trailing 'Custom' button reports the configuration rather than naming a preset, so
  // there is nothing to act on there.
  if (!preset) {
    return
  }
  contextPreset.value = preset
  contextTarget.value = [x, y]
  contextMenuOpen.value = true
}

// Re-captures the running vehicle under an existing name. On a built-in this stores an
// override that shadows the shipped definition until it is reverted.
async function overwritePreset(preset: VehiclePreset): Promise<void> {
  showLoading(`Saving the current configuration as "${preset.name}"… reading all parameters.`)
  try {
    const saved = await VehicleApi.savePreset(preset.name, preset.description)
    await loadPresets()
    notify(`Updated "${saved.name}" with the current configuration.`, 'success')
  } catch (error) {
    notifyError(error, `Could not update ${preset.name}`)
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
    await VehicleApi.renamePreset(preset.name, newName)
    if (explicitPresetName.value === preset.name) {
      explicitPresetName.value = newName
    }
    await loadPresets()
    await loadActivePreset()
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

async function removePreset(preset: VehiclePreset): Promise<void> {
  showLoading(preset.builtin ? `Reverting "${preset.name}"…` : `Deleting preset "${preset.name}"…`)
  try {
    const result = await VehicleApi.deletePreset(preset.name)
    if (explicitPresetName.value === preset.name) {
      explicitPresetName.value = null
    }
    await loadPresets()
    await loadActivePreset()
    notify(result.detail, 'success')
  } catch (error) {
    notifyError(error, `Could not delete ${preset.name}`)
  } finally {
    hideLoading()
  }
}

async function onImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  showLoading('Importing preset…')
  try {
    const preset = JSON.parse(await file.text()) as VehiclePreset
    const saved = await VehicleApi.importPreset(preset)
    await loadPresets()
    await loadActivePreset()
    notify(`Imported preset "${saved.name}".`, 'success')
  } catch (error) {
    notifyError(error, 'Could not import preset')
  } finally {
    hideLoading()
  }
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex items-center gap-2">
      <div class="flex-1 min-w-0">
        <BlueButtonGroup
          v-if="presetButtons.length"
          :key="activePresetName"
          label="Vehicle preset"
          theme="dark"
          type="switch"
          :disabled="locked"
          :button-items="presetButtons"
          info-tooltip="Presets install the matching firmware, set the SITL frame and write the vehicle's defining parameters (motor mapping, battery, tuning), then restart the autopilot. Hold or right-click a preset for its own actions."
          @context-menu="onPresetContextMenu"
        />
      </div>
      <PresetMenu
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
      </PresetMenu>
      <PresetMenu
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

    <BlueSelect
      v-model="selectedVehicle"
      label="Vehicle type"
      theme="dark"
      width="200px"
      :disabled="locked"
      :items="vehicleItems"
      info-tooltip="Applied on selection: installs the matching SITL firmware and restarts the autopilot."
    />
    <BlueSelect
      v-model="selectedFrame"
      label="SITL frame"
      theme="dark"
      width="200px"
      :disabled="locked"
      :items="frameItems"
      info-tooltip="Applied on selection. The frame supplies the simulated physics and only takes effect after the autopilot restarts."
    />

    <ApplyProgressDialog
      v-model="progressOpen"
      :initial="progressJob"
      @finished="onJobFinished"
      @restarted="onJobRestarted"
    />

    <NamePromptDialog
      v-model="renameDialogOpen"
      icon="mdi-rename-box-outline"
      title="Rename preset"
      label="New name"
      confirm-label="Rename"
      :initial="contextPreset?.name"
      :subtitle="
        contextPreset?.builtin
          ? `${contextPreset.name} is built in and stays where it is, so this saves a copy under the new name.`
          : `Renames ${contextPreset?.name}, keeping its vehicle type, frame and parameters.`
      "
      @confirm="confirmRenamePreset"
    />

    <NamePromptDialog
      v-model="saveDialogOpen"
      icon="mdi-content-save-outline"
      title="Save current configuration"
      subtitle="Captures the running vehicle's type, SITL frame and every parameter into a preset you can re-apply or export later."
      label="Preset name"
      notes-label="Description (optional)"
      hint="Reads every parameter, so this takes a moment."
      @confirm="confirmSavePreset"
    />
  </div>
</template>
