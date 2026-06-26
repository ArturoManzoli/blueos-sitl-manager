<script setup lang="ts">
import Loading from '@/components/Loading.vue'
import { snackbar } from '@/composables/notify'
import HomeView from '@/views/HomeView.vue'
</script>

<template>
  <v-app class="bg-transparent">
    <v-main>
      <HomeView />
    </v-main>

    <Loading />

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
