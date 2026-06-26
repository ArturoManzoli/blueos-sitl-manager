<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { notifyError } from '@/composables/notify'
import { VehicleApi } from '@/services/api'
import type { VehicleStatus } from '@/types/sitl'

const status = ref<VehicleStatus | null>(null)
const loading = ref(false)

async function refresh(): Promise<void> {
  loading.value = true
  try {
    status.value = await VehicleApi.status()
  } catch (error) {
    notifyError(error, 'Could not read vehicle status')
  } finally {
    loading.value = false
  }
}

defineExpose({ refresh })
onMounted(refresh)
</script>

<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-icon class="mr-2">
        mdi-information-outline
      </v-icon>
      SITL status
      <v-spacer />
      <v-btn
        icon
        variant="text"
        :loading="loading"
        @click="refresh"
      >
        <v-icon>mdi-refresh</v-icon>
      </v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert
        v-if="status && !status.is_sitl"
        type="warning"
        variant="tonal"
        density="compact"
        class="mb-3"
      >
        The active board is not SITL. Select SITL in the Autopilot Firmware page to use this extension.
      </v-alert>
      <v-row dense>
        <v-col
          cols="6"
          sm="3"
        >
          <div class="text-caption text-medium-emphasis">
            Board
          </div>
          <div>{{ status?.board ?? '—' }}</div>
        </v-col>
        <v-col
          cols="6"
          sm="3"
        >
          <div class="text-caption text-medium-emphasis">
            Is SITL
          </div>
          <div>{{ status ? (status.is_sitl ? 'Yes' : 'No') : '—' }}</div>
        </v-col>
        <v-col
          cols="6"
          sm="3"
        >
          <div class="text-caption text-medium-emphasis">
            Frame
          </div>
          <div>{{ status?.frame ?? '—' }}</div>
        </v-col>
        <v-col
          cols="6"
          sm="3"
        >
          <div class="text-caption text-medium-emphasis">
            Vehicle type
          </div>
          <div>{{ status?.firmware_vehicle_type ?? '—' }}</div>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>
