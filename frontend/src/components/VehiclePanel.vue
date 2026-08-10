<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import BlueButtonGroup from '@/components/BlueButtonGroup.vue'
import BlueSelect from '@/components/BlueSelect.vue'
import BlueSwitch from '@/components/BlueSwitch.vue'
import { hideLoading, showLoading } from '@/composables/loading'
import { notify, notifyError } from '@/composables/notify'
import { VehicleApi } from '@/services/api'
import type { VehiclePreset, VehicleType } from '@/types/sitl'

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
const restartOnFrameChange = ref(true)
const busy = ref(false)
// Which preset the running vehicle matches; 'Custom' when it matches none.
const activePresetName = ref<string>(CUSTOM_PRESET)
// The last preset the user explicitly applied via the button group. Detection only sees
// built-in presets (a custom preset is a full dump of the built-in it derives from and
// shares its frame-defining parameter), so without this it would downgrade an applied
// custom preset to its built-in cousin and hide the delete action.
const explicitPresetName = ref<string | null>(null)

const presetMenuOpen = ref(false)
const saveDialogOpen = ref(false)
const saveName = ref('')
const saveDescription = ref('')
const importInput = ref<HTMLInputElement | null>(null)

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

// Only user-saved/imported presets carry builtin === false and can be deleted.
const activePresetIsCustom = computed(
  () => presets.value.find((preset) => preset.name === activePresetName.value)?.builtin === false
)

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
    const detected = (await VehicleApi.activePreset()) ?? CUSTOM_PRESET
    // Honor an explicitly-applied custom preset over detection, which cannot recognize it.
    const explicit = presets.value.find((preset) => preset.name === explicitPresetName.value)
    if (explicit?.builtin === false) {
      activePresetName.value = explicit.name
      return
    }
    activePresetName.value = detected
  } catch {
    activePresetName.value = CUSTOM_PRESET
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
  try {
    const status = await VehicleApi.status()
    const vehicle = vehicleTypeFromFirmware(status.firmware_vehicle_type)
    if (vehicle) {
      selectedVehicle.value = vehicle
    }
    if (status.frame) {
      selectedFrame.value = status.frame
    }
  } catch {
    // Status is surfaced (and its errors reported) by the StatusPanel; stay quiet here.
  }
}

async function refresh(): Promise<void> {
  await Promise.all([loadActivePreset(), syncFromStatus()])
}

defineExpose({ refresh })

async function applyPreset(preset: VehiclePreset): Promise<void> {
  busy.value = true
  showLoading(`Applying ${preset.name}… the autopilot will restart, this can take up to a minute.`)
  try {
    const result = await VehicleApi.applyPreset(preset.name)
    notify(result.detail, result.success ? 'success' : 'warning')
    activePresetName.value = result.success ? preset.name : CUSTOM_PRESET
    explicitPresetName.value = result.success ? preset.name : null
    emit('changed')
  } catch (error) {
    notifyError(error, `Could not apply ${preset.name}`)
  } finally {
    busy.value = false
    hideLoading()
  }
}

async function applyFrame(): Promise<void> {
  if (!selectedFrame.value) {
    return
  }
  busy.value = true
  if (restartOnFrameChange.value) {
    showLoading('Applying frame… the autopilot will restart.')
  }
  try {
    const result = await VehicleApi.setFrame({ frame: selectedFrame.value, restart: restartOnFrameChange.value })
    notify(result.detail, 'success')
    activePresetName.value = CUSTOM_PRESET
    explicitPresetName.value = null
    emit('changed')
  } catch (error) {
    notifyError(error, 'Could not set frame')
  } finally {
    busy.value = false
    hideLoading()
  }
}

async function applyVehicle(): Promise<void> {
  busy.value = true
  showLoading('Switching vehicle… installing firmware and restarting the autopilot.')
  try {
    const result = await VehicleApi.setType(selectedVehicle.value)
    notify(result.detail, 'success')
    activePresetName.value = CUSTOM_PRESET
    explicitPresetName.value = null
    emit('changed')
  } catch (error) {
    notifyError(error, 'Could not switch vehicle type')
  } finally {
    busy.value = false
    hideLoading()
  }
}

function openSaveDialog(): void {
  saveName.value = ''
  saveDescription.value = ''
  saveDialogOpen.value = true
}

async function confirmSavePreset(): Promise<void> {
  const name = saveName.value.trim()
  if (!name) {
    return
  }
  saveDialogOpen.value = false
  showLoading('Saving current configuration as a preset… reading all parameters.')
  try {
    const preset = await VehicleApi.savePreset(name, saveDescription.value.trim())
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

async function deleteActivePreset(): Promise<void> {
  const name = activePresetName.value
  showLoading(`Deleting preset "${name}"…`)
  try {
    await VehicleApi.deletePreset(name)
    explicitPresetName.value = null
    await loadPresets()
    await loadActivePreset()
    notify(`Deleted preset "${name}".`, 'success')
  } catch (error) {
    notifyError(error, 'Could not delete preset')
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

onMounted(() => {
  loadFrames()
  loadPresets()
  refresh()
})
</script>

<template>
  <div class="flex flex-col gap-5">
    <div class="flex items-center gap-2">
      <div class="flex-1">
        <BlueButtonGroup
          v-if="presetButtons.length"
          :key="activePresetName"
          label="Vehicle preset"
          theme="dark"
          type="switch"
          :disabled="busy"
          :button-items="presetButtons"
          info-tooltip="Presets install the matching firmware, set the SITL frame and write the vehicle's defining parameters (motor mapping, battery, tuning), then restart the autopilot."
        />
      </div>
      <v-menu
        v-model="presetMenuOpen"
        location="bottom end"
      >
        <template #activator="{ props: menuProps }">
          <button
            v-bind="menuProps"
            class="rounded-[6px] px-1 py-1 text-[#ffffffaa] hover:text-white transition-colors"
            :class="busy ? 'opacity-50 pointer-events-none' : 'cursor-pointer'"
            title="Preset actions"
          >
            <v-icon>mdi-dots-vertical</v-icon>
          </button>
        </template>
        <v-list
          density="compact"
          bg-color="#2d2d2d"
          class="py-0"
        >
          <v-list-item
            prepend-icon="mdi-content-save-outline"
            title="Save current config as preset"
            @click="openSaveDialog"
          />
          <div class="h-px bg-[#ffffff0d]" />
          <v-list-item
            prepend-icon="mdi-download-outline"
            title="Download preset file"
            @click="downloadPreset"
          />
          <div class="h-px bg-[#ffffff0d]" />
          <v-list-item
            prepend-icon="mdi-upload-outline"
            title="Import preset file"
            @click="importInput?.click()"
          />
          <template v-if="activePresetIsCustom">
            <div class="h-px bg-[#ffffff0d]" />
            <v-list-item
              prepend-icon="mdi-delete-outline"
              title="Delete this preset"
              base-color="#ff6b6b"
              @click="deleteActivePreset"
            />
          </template>
        </v-list>
      </v-menu>
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
      :items="vehicleItems"
    />
    <BlueSelect
      v-model="selectedFrame"
      label="SITL frame"
      theme="dark"
      width="200px"
      :items="frameItems"
    />
    <BlueSwitch
      v-model="restartOnFrameChange"
      name="restart-on-frame-change"
      label="Restart autopilot after applying"
      theme="dark"
      label-on="Yes"
      label-off="No"
      info-tooltip="Switching vehicle type installs the matching SITL firmware and restarts the autopilot. The SITL frame only takes effect after a restart."
    />

    <div class="flex justify-end gap-2">
      <v-btn
        size="small"
        :loading="busy"
        @click="applyVehicle"
      >
        Switch vehicle
      </v-btn>
      <v-btn
        size="small"
        color="primary"
        :loading="busy"
        :disabled="!selectedFrame"
        @click="applyFrame"
      >
        Apply frame
      </v-btn>
    </div>

    <v-dialog
      v-model="saveDialogOpen"
      width="420"
    >
      <v-card
        color="#2d2d2d"
        class="text-white"
      >
        <v-card-title class="text-base">
          Save current configuration
        </v-card-title>
        <v-card-text class="flex flex-col gap-3">
          <p class="text-xs text-[#ffffff88] leading-relaxed">
            Captures the running vehicle's type, SITL frame and every parameter into a new
            preset you can re-apply or export later.
          </p>
          <v-text-field
            v-model="saveName"
            label="Preset name"
            density="compact"
            variant="outlined"
            autofocus
            hide-details
            @keydown.enter="confirmSavePreset"
          />
          <v-text-field
            v-model="saveDescription"
            label="Description (optional)"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            size="small"
            @click="saveDialogOpen = false"
          >
            Cancel
          </v-btn>
          <v-btn
            size="small"
            color="primary"
            :disabled="!saveName.trim()"
            @click="confirmSavePreset"
          >
            Save
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
