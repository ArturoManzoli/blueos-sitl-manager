<script setup lang="ts">
import { loading } from '@/composables/loading'
</script>

<template>
  <v-dialog
    theme="dark"
    :model-value="loading.show"
    persistent
    width="320px"
  >
    <div class="sitl-loading flex flex-col items-center justify-center rounded-lg px-6 pt-7 pb-5">
      <v-icon
        size="60"
        class="sitl-loading__icon mb-3"
      >
        mdi-test-tube
      </v-icon>
      <span class="text-center text-base text-white mb-5">
        {{ loading.message }}
      </span>
      <v-progress-linear
        indeterminate
        rounded
        color="primary"
        class="w-full"
      />
    </div>
  </v-dialog>
</template>

<style scoped>
.sitl-loading {
  background-color: rgba(30, 30, 30, 0.92);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 4px 4px rgba(0, 0, 0, 0.2), 0 8px 12px 6px rgba(0, 0, 0, 0.15);
}

.sitl-loading__icon {
  color: rgb(var(--v-theme-primary));
  animation: sitl-pulse 1.4s ease-in-out infinite;
}

@keyframes sitl-pulse {
  0%,
  100% {
    opacity: 0.5;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.1);
  }
}
</style>
