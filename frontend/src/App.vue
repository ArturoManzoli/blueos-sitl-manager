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
      :timeout="4000"
    >
      {{ snackbar.text }}
    </v-snackbar>
  </v-app>
</template>
