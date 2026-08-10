<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'

import { VehicleApi } from '@/services/api'
import type { ApplyJob, ParamOutcome, StepState } from '@/types/sitl'

const props = defineProps<{
  modelValue: boolean
  // First snapshot returned when the job was started, so the dialog has something to show
  // before its first poll lands.
  initial: ApplyJob | null
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'finished', job: ApplyJob): void
}>()

const POLL_INTERVAL = 400

const job = ref<ApplyJob | null>(null)
const logRef = ref<HTMLElement | null>(null)
let timer: number | undefined

const running = computed(() => job.value?.state === 'running')
const failed = computed(() => job.value?.state === 'failed')

const OUTCOME_STYLE: Record<ParamOutcome, { label: string; color: string }> = {
  written: { label: 'written', color: '#66BB6A' },
  unchanged: { label: 'unchanged', color: '#90A4AE' },
  unsupported: { label: 'not supported', color: '#FFB74D' },
  failed: { label: 'rejected', color: '#EF5350' },
}

const STEP_STYLE: Record<StepState, { icon: string; color: string }> = {
  pending: { icon: 'mdi-circle-outline', color: '#ffffff44' },
  running: { icon: 'mdi-progress-clock', color: '#42A5F5' },
  done: { icon: 'mdi-check-circle', color: '#66BB6A' },
  failed: { icon: 'mdi-alert-circle', color: '#EF5350' },
  skipped: { icon: 'mdi-minus-circle-outline', color: '#ffffff44' },
}

const activeStep = computed(() => job.value?.steps.find((step) => step.state === 'running') ?? null)

const outcomeCounts = computed(() =>
  (Object.keys(OUTCOME_STYLE) as ParamOutcome[])
    .map((outcome) => ({ outcome, count: job.value?.counts[outcome] ?? 0 }))
    .filter((entry) => entry.count > 0)
)

const paramProgress = computed(() => {
  const total = job.value?.params_total ?? 0
  return total ? ((job.value?.params_done ?? 0) / total) * 100 : 0
})

async function poll(): Promise<void> {
  try {
    const latest = await VehicleApi.applyJob()
    if (!latest || latest.id !== job.value?.id) {
      return
    }
    job.value = latest
    if (latest.state !== 'running') {
      stopPolling()
      emit('finished', latest)
    }
  } catch {
    // A restarting autopilot makes the backend briefly unreachable; keep polling.
  }
}

function stopPolling(): void {
  window.clearInterval(timer)
  timer = undefined
}

function close(): void {
  emit('update:modelValue', false)
}

// Follow the tail of the parameter log as records arrive.
watch(
  () => job.value?.records.length,
  async () => {
    await nextTick()
    if (logRef.value) {
      logRef.value.scrollTop = logRef.value.scrollHeight
    }
  }
)

watch(
  () => props.modelValue,
  (open) => {
    stopPolling()
    if (!open) {
      return
    }
    job.value = props.initial
    timer = window.setInterval(poll, POLL_INTERVAL)
  },
  { immediate: true }
)

onUnmounted(stopPolling)
</script>

<template>
  <v-dialog
    theme="dark"
    :model-value="modelValue"
    :persistent="running"
    width="620px"
    @update:model-value="close"
  >
    <div
      v-if="job"
      class="sitl-progress rounded-lg text-white"
    >
      <div class="flex items-start gap-3 px-5 pt-4 pb-3">
        <v-icon
          size="22"
          :color="running ? '#42A5F5' : failed ? '#EF5350' : '#66BB6A'"
          class="mt-[2px]"
        >
          {{ running ? 'mdi-cog-sync' : failed ? 'mdi-alert-circle' : 'mdi-check-circle' }}
        </v-icon>
        <div class="flex-1">
          <div class="text-base leading-tight">
            {{ running ? `Applying ${job.title}` : job.title }}
          </div>
          <div class="text-xs text-[#ffffff88] mt-1">
            {{ job.detail || activeStep?.detail || 'Working…' }}
          </div>
        </div>
        <button
          v-if="!running"
          class="text-[#ffffffaa] hover:text-white transition-colors cursor-pointer"
          title="Close"
          @click="close"
        >
          <v-icon size="20">
            mdi-close
          </v-icon>
        </button>
      </div>

      <div class="flex items-start px-5 pb-4">
        <template
          v-for="(step, index) in job.steps"
          :key="step.key"
        >
          <div
            v-if="index"
            class="flex-1 h-px mt-[11px] bg-[#ffffff1a]"
          />
          <div class="flex flex-col items-center gap-1 w-[74px]">
            <v-icon
              size="22"
              :color="STEP_STYLE[step.state].color"
            >
              {{ STEP_STYLE[step.state].icon }}
            </v-icon>
            <span
              class="text-[10px] leading-tight text-center"
              :class="step.state === 'running' ? 'text-white' : 'text-[#ffffff77]'"
            >
              {{ step.title }}
            </span>
          </div>
        </template>
      </div>

      <div
        v-if="job.params_total"
        class="border-t border-[#ffffff0d] px-5 py-4"
      >
        <div class="flex items-baseline justify-between mb-2">
          <span class="text-xs text-[#ffffffcc]">
            {{
              job.current_param
                ? `Sending parameter ${job.params_done + 1}/${job.params_total}: ${job.current_param}`
                : `${job.params_done}/${job.params_total} parameters processed`
            }}
          </span>
          <div class="flex gap-2">
            <span
              v-for="entry in outcomeCounts"
              :key="entry.outcome"
              class="text-[11px]"
              :style="{ color: OUTCOME_STYLE[entry.outcome].color }"
            >
              {{ entry.count }} {{ OUTCOME_STYLE[entry.outcome].label }}
            </span>
          </div>
        </div>
        <v-progress-linear
          :model-value="paramProgress"
          rounded
          height="4"
          color="primary"
          bg-color="#ffffff1a"
        />
        <div
          ref="logRef"
          class="mt-3 max-h-[220px] overflow-y-auto rounded-[6px] bg-[#00000033] px-3 py-2 font-mono text-[11px]"
        >
          <div
            v-for="record in job.records"
            :key="record.name"
            class="flex items-center justify-between gap-3 py-[2px]"
          >
            <span class="text-[#ffffffcc] truncate">{{ record.name }}</span>
            <span class="flex items-center gap-2 shrink-0">
              <span class="text-[#ffffff66]">{{ record.value }}</span>
              <span :style="{ color: OUTCOME_STYLE[record.outcome].color }">
                {{ OUTCOME_STYLE[record.outcome].label }}
              </span>
            </span>
          </div>
        </div>
      </div>

      <div
        v-if="!running"
        class="flex items-center justify-between gap-3 border-t border-[#ffffff0d] px-5 py-3"
      >
        <span class="text-xs text-[#ffffff88]">
          {{ job.reported_vehicle ? `The autopilot reports itself as ${job.reported_vehicle}.` : '' }}
        </span>
        <v-btn
          size="small"
          color="primary"
          @click="close"
        >
          Close
        </v-btn>
      </div>
    </div>
  </v-dialog>
</template>

<style scoped>
.sitl-progress {
  background-color: rgba(30, 30, 30, 0.96);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 4px 4px rgba(0, 0, 0, 0.2), 0 8px 12px 6px rgba(0, 0, 0, 0.15);
}
</style>
