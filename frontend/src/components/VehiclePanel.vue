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

const vehicleItems = computed(() => vehicleTypes.map((value) => ({ name: value, value })))
const frameItems = computed(() => frames.value.map((value) => ({ name: value, value })))
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
    activePresetName.value = (await VehicleApi.activePreset()) ?? CUSTOM_PRESET
  } catch {
    activePresetName.value = CUSTOM_PRESET
  }
}

async function applyPreset(preset: VehiclePreset): Promise<void> {
  busy.value = true
  showLoading(`Applying ${preset.name}… the autopilot will restart, this can take up to a minute.`)
  try {
    const result = await VehicleApi.applyPreset(preset.name)
    notify(result.detail, result.success ? 'success' : 'warning')
    activePresetName.value = result.success ? preset.name : CUSTOM_PRESET
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
    emit('changed')
  } catch (error) {
    notifyError(error, 'Could not switch vehicle type')
  } finally {
    busy.value = false
    hideLoading()
  }
}

onMounted(() => {
  loadFrames()
  loadPresets()
  loadActivePreset()
})
</script>

<template>
  <div class="flex flex-col gap-5">
    <div>
      <BlueButtonGroup
        v-if="presetButtons.length"
        :key="activePresetName"
        label="Vehicle preset"
        theme="dark"
        type="switch"
        :disabled="busy"
        :button-items="presetButtons"
      />
      <p class="text-xs text-[#ffffff88] leading-relaxed mt-2">
        Presets install the matching firmware, set the SITL frame and write the vehicle's
        defining parameters (motor mapping, battery, tuning), then restart the autopilot.
      </p>
    </div>

    <div class="flex items-center gap-3">
      <div class="flex-1 h-px bg-[#ffffff22]" />
      <span class="text-xs uppercase tracking-wide text-[#ffffff66]">Manual configuration</span>
      <div class="flex-1 h-px bg-[#ffffff22]" />
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

    <p class="text-xs text-[#ffffff88] leading-relaxed">
      Switching vehicle type installs the matching SITL firmware and restarts the autopilot.
      The SITL frame only takes effect after a restart.
    </p>
  </div>
</template>
