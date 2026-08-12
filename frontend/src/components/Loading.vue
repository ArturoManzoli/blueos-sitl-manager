<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import logo from '@/assets/br-logo-white.svg'
import { hideLoading, loading } from '@/composables/loading'

const dialogRef = ref<HTMLDialogElement | null>(null)

const sync = (show: boolean): void => {
  const el = dialogRef.value
  if (!el) return
  if (show && !el.open) el.showModal()
  if (!show && el.open) el.close()
}

// Escape closes a dismissible overlay through the same path as the button, so the shared
// state follows the dialog instead of thinking it is still up.
const onCancel = (event: Event): void => {
  event.preventDefault()
  if (loading.dismissible) hideLoading()
}

onMounted(() => sync(loading.show))
watch(() => loading.show, sync)
</script>

<template>
  <!-- Escape is swallowed unless the wait is dismissible: an operation the user cannot
       interrupt must not end up running under a live page. -->
  <dialog
    ref="dialogRef"
    class="bluevue-dialog"
    @cancel="onCancel"
  >
    <div class="bluevue-panel relative flex w-[320px] flex-col items-center justify-center rounded-lg px-6 pt-7 pb-5">
      <button
        v-if="loading.dismissible"
        type="button"
        class="absolute right-3 top-3 cursor-pointer text-[#ffffffaa] transition-colors hover:text-white"
        title="Close"
        @click="hideLoading"
      >
        <span class="mdi mdi-close text-[20px] leading-none" />
      </button>
      <img
        :src="logo"
        alt=""
        class="bluevue-loading__icon mb-6 h-[100px] w-[100px]"
      >
      <span class="mt-[15px] text-center text-base text-white">
        {{ loading.message }}
      </span>
    </div>
  </dialog>
</template>

<style scoped>
/* The logo is a propeller, so it turns like one: a creep of 80 degrees over two seconds, then
   the balance of four turns over the next two, carrying it round to where it started. */
.bluevue-loading__icon {
  animation: bluevue-prop 4s infinite;
}

@keyframes bluevue-prop {
  /* Each segment carries its own easing, which is what gives the blade its weight: it takes a
     moment to get moving, settles at the end of the creep, then winds up into the spins and
     bleeds the speed off again rather than stopping dead. The cycle ends on a whole turn, so
     the loop restarts from the orientation it began at and the seam is invisible. */
  0% {
    transform: rotate(0deg);
    animation-timing-function: cubic-bezier(0.45, 0, 0.55, 1);
  }
  /* 80deg at the halfway mark, leaving the other two seconds for the 1360deg that follow. */
  50% {
    transform: rotate(80deg);
    animation-timing-function: cubic-bezier(0.35, 0, 0.45, 1);
  }
  100% {
    transform: rotate(1440deg);
  }
}
</style>
