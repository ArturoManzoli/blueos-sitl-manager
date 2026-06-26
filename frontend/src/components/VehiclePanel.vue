<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { notify, notifyError } from '@/composables/notify'
import { VehicleApi } from '@/services/api'
import type { VehicleType } from '@/types/sitl'

const emit = defineEmits<{ (event: 'changed'): void }>()

const vehicleTypes: VehicleType[] = ['Sub', 'Rover', 'Plane', 'Copter']
const frames = ref<string[]>([])
const selectedFrame = ref<string | null>(null)
const selectedVehicle = ref<VehicleType>('Sub')
const restartOnFrameChange = ref(true)
const busy = ref(false)

async function loadFrames(): Promise<void> {
  try {
    frames.value = await VehicleApi.frames()
  } catch (error) {
    notifyError(error, 'Could not load frames')
  }
}

async function applyFrame(): Promise<void> {
  if (!selectedFrame.value) {
    return
  }
  busy.value = true
  try {
    const result = await VehicleApi.setFrame({ frame: selectedFrame.value, restart: restartOnFrameChange.value })
    notify(result.detail, 'success')
    emit('changed')
  } catch (error) {
    notifyError(error, 'Could not set frame')
  } finally {
    busy.value = false
  }
}

async function applyVehicle(): Promise<void> {
  busy.value = true
  try {
    const result = await VehicleApi.setType(selectedVehicle.value)
    notify(result.detail, 'success')
    emit('changed')
  } catch (error) {
    notifyError(error, 'Could not switch vehicle type')
  } finally {
    busy.value = false
  }
}

onMounted(loadFrames)
</script>

<template>
  <v-card>
    <v-card-title>
      <v-icon class="mr-2">
        mdi-submarine
      </v-icon>
      Vehicle &amp; frame
    </v-card-title>
    <v-card-text>
      <div class="text-subtitle-2 mb-2">
        Vehicle type
      </div>
      <div class="d-flex align-center ga-3 mb-4">
        <v-select
          v-model="selectedVehicle"
          :items="vehicleTypes"
          label="Vehicle"
          density="compact"
          hide-details
          variant="outlined"
        />
        <v-btn
          color="primary"
          :loading="busy"
          @click="applyVehicle"
        >
          Switch
        </v-btn>
      </div>
      <v-alert
        type="info"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        Switching vehicle type installs the matching SITL firmware and restarts the autopilot.
      </v-alert>

      <v-divider class="mb-4" />

      <div class="text-subtitle-2 mb-2">
        SITL frame
      </div>
      <div class="d-flex align-center ga-3">
        <v-select
          v-model="selectedFrame"
          :items="frames"
          label="Frame"
          density="compact"
          hide-details
          variant="outlined"
        />
        <v-btn
          color="primary"
          :loading="busy"
          :disabled="!selectedFrame"
          @click="applyFrame"
        >
          Apply
        </v-btn>
      </div>
      <v-checkbox
        v-model="restartOnFrameChange"
        label="Restart autopilot after applying (frame only takes effect on restart)"
        density="compact"
        hide-details
        class="mt-2"
      />
    </v-card-text>
  </v-card>
</template>
