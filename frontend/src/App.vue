<script setup lang="ts">
import { BlueLoadingDialog } from '@bluerobotics/bluevue'

import { hideLoading, loading } from '@/composables/loading'
import { snackbar } from '@/composables/notify'
import HomeView from '@/views/HomeView.vue'
</script>

<template>
  <v-app class="bg-transparent">
    <v-main>
      <HomeView />
    </v-main>

    <!-- The overlay is driven from anywhere through the loading composable, so closing a
         dismissible one has to travel back the same way rather than only to the dialog. -->
    <BlueLoadingDialog
      :model-value="loading.show"
      :message="loading.message"
      :dismissible="loading.dismissible"
      @update:model-value="hideLoading"
    />

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      location="bottom right"
      :timeout="-1"
    >
      {{ snackbar.text }}

      <template #actions>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          @click="snackbar.show = false"
        />
      </template>
    </v-snackbar>
  </v-app>
</template>
