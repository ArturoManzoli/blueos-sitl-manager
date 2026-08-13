<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import { BlueButtonGroup, BlueMenu, type BlueMenuItem, BluePromptDialog, BlueSelect } from '@bluerobotics/bluevue'

import ApplyProgressDialog from '@/components/ApplyProgressDialog.vue'
import { hideLoading, showLoading } from '@/composables/loading'
import { notify, notifyError } from '@/composables/notify'
import { isSitl, refreshVehicleStatus } from '@/composables/vehicleStatus'
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
const frames = ref<Partial<Record<VehicleType, string[]>>>({})
const presets = ref<VehiclePreset[]>([])
const busy = ref(false)
// Set while the fields are written from the vehicle or from a preset, so the watchers below
// can tell a choice the user made from one they are only being shown.
const syncing = ref(false)
const progressJob = ref<ApplyJob | null>(null)
const progressOpen = ref(false)

// What the section is set to, which is not what the vehicle is running until Apply is
// pressed. Everything here — the two selectors and the highlighted preset — is a proposal.
const selectedFrame = ref<string | null>(null)
const selectedVehicle = ref<VehicleType>('Sub')
const selectedPresetName = ref<string>(CUSTOM_PRESET)

// What the vehicle was running when it was last read, which is what a proposal is measured
// against to decide whether there is anything to apply.
const appliedFrame = ref<string | null>(null)
const appliedVehicle = ref<VehicleType | null>(null)
const appliedPresetName = ref<string>(CUSTOM_PRESET)

// The last preset the user applied, or 'Custom' for a combination they assembled themselves.
// Detection is only consulted while this is null, because it answers with the built-in whose
// frame-defining parameter the vehicle happens to share: a Rover left on a quad frame reads
// as Ground Rover, and a saved preset reads as the built-in it was captured from. Either
// answer would take the row off what the user chose.
const userChoice = ref<string | null>(null)

const presetMenuOpen = ref(false)
const saveDialogOpen = ref(false)
const importInput = ref<HTMLInputElement | null>(null)

// The preset a long press or right-click opened the actions menu on, and where to hang it.
const contextPreset = ref<VehiclePreset | null>(null)
// The Custom entry names no preset, so it opens a menu of its own.
const contextCustom = ref(false)
const contextTarget = ref<[number, number]>([0, 0])
const contextMenuOpen = ref(false)
const renameDialogOpen = ref(false)

const vehicleItems = computed(() => vehicleTypes.map((value) => ({ name: value, value })))
// Only the frames the chosen firmware can run: each is a physics model compiled into one
// vehicle's binary, so offering a plane to a sub would only be offering a failure.
const vehicleFrames = computed(() => frames.value[selectedVehicle.value] ?? [])
// The running frame stays selectable even when it is not one of the curated ones — or not
// one of this vehicle's at all, which is what a vehicle configured elsewhere looks like — so
// the dropdown can show what the vehicle is actually set to.
const frameItems = computed(() => {
  const names = [...vehicleFrames.value]
  if (selectedFrame.value && !names.includes(selectedFrame.value)) {
    names.unshift(selectedFrame.value)
  }
  return names.map((value) => ({ name: value, value }))
})
const presetButtons = computed<PresetButton[]>(() => {
  const buttons: PresetButton[] = presets.value.map((preset) => ({
    name: preset.name,
    tooltip: preset.description,
    preSelected: selectedPresetName.value === preset.name,
    onSelected: () => selectPreset(preset),
  }))
  buttons.push({
    name: CUSTOM_PRESET,
    tooltip: 'Whatever the two selectors below are set to, saved under a name of its own or left as an experiment',
    preSelected: selectedPresetName.value === CUSTOM_PRESET,
    onSelected: () => {
      selectedPresetName.value = CUSTOM_PRESET
    },
  })
  return buttons
})

// A preset says what to write; Custom means whatever the selectors are set to.
const selectedPreset = computed(() => presets.value.find((preset) => preset.name === selectedPresetName.value) ?? null)

const configChanged = computed(
  () => selectedVehicle.value !== appliedVehicle.value || selectedFrame.value !== appliedFrame.value
)

// What Apply would actually do. Landing on Custom without touching the selectors changes
// nothing, and re-applying the preset the vehicle already runs is what the preset's own
// Reload is for, so neither arms the button.
const pendingChange = computed(() =>
  selectedPreset.value ? selectedPreset.value.name !== appliedPresetName.value : configChanged.value
)

const presetsFull = computed(() => presets.value.length >= MAX_PRESETS)
const fullHint = computed(() => (presetsFull.value ? `The row holds ${MAX_PRESETS} presets; delete one first` : undefined))

// Applying anything here reconfigures the autopilot, which on a real board would mean
// reflashing it, so the vehicle actions wait for the simulator. Everything that only moves
// presets around — importing, renaming, exporting a stored one, deleting — stays available.
const locked = computed(() => busy.value || !isSitl.value)
const sitlHint = computed(() => (isSitl.value ? undefined : 'Only available on a SITL board'))

// Saving captures the vehicle as it is running, so it is held back while the section is
// proposing something else: the preset would carry the old configuration under a name the
// user picked for the new one.
const pendingHint = computed(() => (pendingChange.value ? 'Apply the pending changes first' : undefined))
const saveDisabled = computed(() => presetsFull.value || !isSitl.value || pendingChange.value)
const saveHint = computed(() => fullHint.value ?? sitlHint.value ?? pendingHint.value)

// The three-dots menu, which acts on the vehicle rather than on any one preset.
const presetActions = computed<BlueMenuItem[]>(() => [
  {
    title: 'Save current config as preset',
    icon: 'mdi-content-save-outline',
    disabled: saveDisabled.value,
    hint: saveHint.value,
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

// What a long press offers on the Custom entry. Both roads lead to the same dialog: naming
// the configuration is what turns it into a preset, and doing so hands Custom back empty for
// the next experiment.
const customItems = computed<BlueMenuItem[]>(() => [
  {
    title: 'Save as preset…',
    icon: 'mdi-content-save-outline',
    disabled: saveDisabled.value,
    hint: saveHint.value,
    action: () => (saveDialogOpen.value = true),
  },
  {
    title: 'Rename…',
    icon: 'mdi-rename-box-outline',
    disabled: saveDisabled.value,
    hint: saveHint.value,
    action: () => (saveDialogOpen.value = true),
  },
])

// What a long press offers for one preset. A built-in can be reloaded, edited, renamed (as a
// copy) and exported, but never deleted: an edited one is reverted to its shipped definition
// instead, which is what keeps the curated presets impossible to lose.
const contextItems = computed<BlueMenuItem[]>(() => {
  const preset = contextPreset.value
  if (!preset) {
    return contextCustom.value ? customItems.value : []
  }
  const items: BlueMenuItem[] = [
    {
      // The one place a preset is written to the vehicle without going through Apply: it
      // asks for the preset the vehicle is already on to be laid down again, which the
      // button cannot offer because that is not a change.
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

// Which preset the vehicle is on. A choice the user made stands: detection is there to
// recognise a vehicle nobody has told us about — the one found on a fresh page load — and
// only ever answers with a built-in.
async function loadActivePreset(): Promise<void> {
  if (userChoice.value !== null) {
    appliedPresetName.value = userChoice.value
    return
  }
  try {
    appliedPresetName.value = (await VehicleApi.activePreset()) ?? CUSTOM_PRESET
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

// Read what the vehicle is running. Writing the fields is left to the caller, which does it
// once the preset is known too, so the section never shows half of one state and half of
// another.
async function readStatus(): Promise<void> {
  try {
    const status = await refreshVehicleStatus()
    appliedVehicle.value = vehicleTypeFromFirmware(status.firmware_vehicle_type) ?? appliedVehicle.value
    appliedFrame.value = status.frame ?? appliedFrame.value
  } catch {
    // Status is surfaced (and its errors reported) by the StatusPanel; stay quiet here.
  }
}

// Put the section back on the vehicle, dropping anything that was proposed and not applied.
async function showApplied(): Promise<void> {
  syncing.value = true
  if (appliedVehicle.value) {
    selectedVehicle.value = appliedVehicle.value
  }
  if (appliedFrame.value) {
    selectedFrame.value = appliedFrame.value
  }
  selectedPresetName.value = appliedPresetName.value
  await nextTick()
  syncing.value = false
}

// Driven by the view rather than onMounted, which is what lets the overlay stay up until
// every panel has something to show. The preset list is read before the active preset is
// resolved, since resolving it means matching against that list.
async function reload(): Promise<void> {
  await Promise.all([loadFrames(), loadPresets()])
  await Promise.all([loadActivePreset(), readStatus()])
  await showApplied()
}

defineExpose({ reload })

// Every configuration change runs as a backend job; start it, then hand the first snapshot to
// the progress dialog, which polls the rest. The Apply button spins for the wait in between.
async function startJob(start: () => Promise<ApplyJob>, failureMessage: string): Promise<boolean> {
  busy.value = true
  try {
    progressJob.value = await start()
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
    userChoice.value = preset.name
  }
}

// Only what differs is sent: installing the firmware that is already running is work the job
// would skip anyway, but naming it would still put a step on screen claiming to do it.
async function applyConfig(): Promise<void> {
  const config = {
    vehicle: selectedVehicle.value !== appliedVehicle.value ? selectedVehicle.value : undefined,
    frame: selectedFrame.value !== appliedFrame.value ? (selectedFrame.value ?? undefined) : undefined,
  }
  if (await startJob(() => VehicleApi.applyConfig(config), 'Could not apply the configuration')) {
    userChoice.value = CUSTOM_PRESET
  }
}

// Everything the section proposes lands here, and only here.
async function applySelection(): Promise<void> {
  const preset = selectedPreset.value
  await (preset ? applyPreset(preset) : applyConfig())
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
  // A job that stopped short leaves a vehicle that is nobody's idea of a preset, so the row
  // gives up the name it was applying and reports whatever the vehicle now reads as.
  if (job.state !== 'succeeded') {
    userChoice.value = null
  }
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

// Picking a preset fills the selectors from it, so the section says what Apply will bring
// about rather than leaving the vehicle it names to be taken on trust.
async function selectPreset(preset: VehiclePreset): Promise<void> {
  syncing.value = true
  selectedPresetName.value = preset.name
  selectedVehicle.value = preset.vehicle
  // An imported or older preset can carry no frame, in which case it leaves the running one
  // alone and the selector should keep showing it.
  if (preset.frame) {
    selectedFrame.value = preset.frame
  }
  await nextTick()
  syncing.value = false
}

// Changing the vehicle type takes the frame with it when the one on screen belongs to the
// firmware being left behind. Left alone, the field would keep offering to run a sub on a
// plane. A frame the vehicle is genuinely running is left where it is, which is why this
// only answers to a choice the user made.
watch(selectedVehicle, () => {
  const allowed = vehicleFrames.value
  if (!syncing.value && allowed.length && !allowed.includes(selectedFrame.value ?? '')) {
    selectedFrame.value = allowed[0]
  }
})

// A combination the user assembles belongs to nobody's preset, so the row says so. Custom is
// deliberately free-form: any pairing of vehicle type and frame can be tried from it, and
// saving turns whichever one worked into a preset of its own.
watch([selectedVehicle, selectedFrame], () => {
  if (!syncing.value) {
    selectedPresetName.value = CUSTOM_PRESET
  }
})

async function confirmSavePreset(name: string, description: string): Promise<void> {
  showLoading('Saving current configuration as a preset… reading all parameters.')
  try {
    const preset = await VehicleApi.savePreset(name, description)
    await loadPresets()
    // The vehicle now has a preset's name to go by, so the row moves onto it and Custom is
    // left empty for the next experiment.
    userChoice.value = preset.name
    appliedPresetName.value = preset.name
    selectedPresetName.value = preset.name
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
  if (!preset && item.name !== CUSTOM_PRESET) {
    return
  }
  contextPreset.value = preset ?? null
  contextCustom.value = !preset
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
    if (userChoice.value === preset.name) {
      userChoice.value = newName
    }
    await loadPresets()
    await loadActivePreset()
    await showApplied()
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
    // The vehicle still runs what the preset described, but there is no longer a name for
    // it, so the row falls back to what detection makes of the configuration.
    if (userChoice.value === preset.name) {
      userChoice.value = null
    }
    await loadPresets()
    await loadActivePreset()
    await showApplied()
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
          :key="selectedPresetName"
          label="Vehicle preset"
          theme="dark"
          type="switch"
          :disabled="locked"
          :button-items="presetButtons"
          info-tooltip="Picking a preset fills the fields below with the firmware, SITL frame and defining parameters (motor mapping, battery, tuning) it describes; Apply writes them and restarts the autopilot. Custom is whatever combination you set yourself, and can be saved as a preset of its own. Hold or right-click an entry for its own actions."
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

    <BlueSelect
      v-model="selectedVehicle"
      label="Vehicle type"
      theme="dark"
      width="200px"
      :disabled="locked"
      :items="vehicleItems"
      info-tooltip="Which firmware Apply installs. Choosing one by hand moves the row to Custom, since the combination is yours rather than a preset's."
    />
    <BlueSelect
      v-model="selectedFrame"
      label="SITL frame"
      theme="dark"
      width="200px"
      :disabled="locked"
      :items="frameItems"
      info-tooltip="Which physics model the simulator runs. Like the vehicle type, it moves the row to Custom and only takes effect once Apply has restarted the autopilot."
    />

    <div class="flex items-center justify-end gap-2">
      <v-btn
        color="primary"
        size="small"
        :loading="busy"
        :disabled="locked || !pendingChange"
        @click="applySelection"
      >
        Apply and restart
      </v-btn>
    </div>

    <ApplyProgressDialog
      v-model="progressOpen"
      :initial="progressJob"
      @finished="onJobFinished"
      @restarted="onJobRestarted"
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
          : `Renames ${contextPreset?.name}, keeping its vehicle type, frame and parameters.`
      "
      @confirm="confirmRenamePreset"
    />

    <BluePromptDialog
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
