<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'

import { notifyError } from '@/composables/notify'
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
  (event: 'restarted', job: ApplyJob): void
}>()

const POLL_INTERVAL = 400
const PARAMETERS_STEP = 'parameters'

const job = ref<ApplyJob | null>(null)
const logRef = ref<HTMLElement | null>(null)
const resuming = ref<'retry' | 'skip' | null>(null)
let timer: number | undefined

const running = computed(() => job.value?.state === 'running')
const failed = computed(() => job.value?.state === 'failed')

const OUTCOME_STYLE: Record<ParamOutcome, { label: string; color: string }> = {
  written: { label: 'written', color: '#66BB6A' },
  unchanged: { label: 'unchanged', color: '#90A4AE' },
  unsupported: { label: 'not supported', color: '#FFB74D' },
  failed: { label: 'rejected', color: '#EF5350' },
}

// The step icons and the connectors between them share this height, which is what puts the
// line on the icons' centre line. Applied inline: Vuetify's reset zeroes margins outside any
// cascade layer, which beats Tailwind's layered spacing utilities.
const STEP_ICON_SIZE = 22

const STEP_STYLE: Record<StepState, { icon: string; color: string }> = {
  pending: { icon: 'mdi-circle-outline', color: '#ffffff44' },
  running: { icon: 'mdi-progress-clock', color: '#42A5F5' },
  done: { icon: 'mdi-check-circle', color: '#66BB6A' },
  failed: { icon: 'mdi-alert-circle', color: '#EF5350' },
  skipped: { icon: 'mdi-minus-circle-outline', color: '#ffffff44' },
}

const activeStep = computed(() => job.value?.steps.find((step) => step.state === 'running') ?? null)

// A failed job always leaves exactly one failed step, which is what Retry and Skip act on.
const failedStep = computed(() => job.value?.steps.find((step) => step.state === 'failed') ?? null)

// The step the progress section reports on: the one in flight, or the one that failed.
const focusStep = computed(() => activeStep.value ?? failedStep.value)

// Parameters are the only step that knows how much is left, so it fills the bar. Everything
// else waits on the autopilot for an unknowable time — a firmware download, a restart, the
// vehicle type read-back — and reports seconds spent instead of a fraction, so the bar runs
// indeterminate rather than sitting full at 75/75 while nothing appears to happen.
const awaitingStep = computed(() => (focusStep.value?.key === PARAMETERS_STEP ? null : focusStep.value))

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

function startPolling(): void {
  stopPolling()
  timer = window.setInterval(poll, POLL_INTERVAL)
}

function stopPolling(): void {
  window.clearInterval(timer)
  timer = undefined
}

function close(): void {
  emit('update:modelValue', false)
}

// Retry re-runs the failed step, skip gives up on it; both then carry the same job on
// through the steps that are left.
async function resume(action: 'retry' | 'skip'): Promise<void> {
  resuming.value = action
  try {
    const restarted = action === 'retry' ? await VehicleApi.retryApplyJob() : await VehicleApi.skipApplyJob()
    job.value = restarted
    emit('restarted', restarted)
    startPolling()
  } catch (error) {
    notifyError(error, action === 'retry' ? 'Could not retry the step' : 'Could not skip the step')
  } finally {
    resuming.value = null
  }
}

// Follow the tail of the log as parameter records arrive and as the awaited step reports in.
watch(
  () => [job.value?.records.length, awaitingStep.value?.detail],
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
    startPolling()
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
      class="bluevue-panel rounded-lg text-white"
    >
      <div class="flex items-start gap-3 px-5 pt-4 pb-3">
        <v-icon
          size="22"
          :color="running ? '#42A5F5' : failed ? '#EF5350' : '#66BB6A'"
          class="mt-[2px]"
        >
          {{ running ? 'mdi-cog-sync' : failed ? 'mdi-alert-circle' : 'mdi-check-circle' }}
        </v-icon>
        <div class="flex-1 min-w-0">
          <div class="text-base leading-tight truncate">
            {{ running ? `Applying ${job.title}` : job.title }}
          </div>
          <div class="text-xs text-[#ffffff88] mt-1 truncate">
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
            class="flex flex-1 items-center"
            :style="{ height: `${STEP_ICON_SIZE}px` }"
          >
            <div class="h-px w-full bg-[#ffffff1a]" />
          </div>
          <!-- Wide enough for the longest step title to stay on one line before the ellipsis. -->
          <div class="flex flex-col items-center gap-1 w-[84px] shrink-0">
            <v-icon
              :size="STEP_ICON_SIZE"
              :color="STEP_STYLE[step.state].color"
            >
              {{ STEP_STYLE[step.state].icon }}
            </v-icon>
            <span
              class="w-full truncate text-[10px] leading-tight text-center"
              :title="step.title"
              :class="step.state === 'running' ? 'text-white' : 'text-[#ffffff77]'"
            >
              {{ step.title }}
            </span>
          </div>
        </template>
      </div>

      <div
        v-if="awaitingStep || job.params_total"
        class="border-t border-[#ffffff0d] px-5 py-4"
      >
        <div class="flex items-baseline justify-between mb-2">
          <span class="text-xs text-[#ffffffcc] truncate">
            {{
              awaitingStep
                ? awaitingStep.title
                : job.current_param
                  ? `Sending parameter ${job.params_done + 1}/${job.params_total}: ${job.current_param}`
                  : `${job.params_done}/${job.params_total} parameters processed`
            }}
          </span>
          <div class="flex gap-2 shrink-0 pl-3">
            <span
              v-for="entry in outcomeCounts"
              :key="entry.outcome"
              class="text-[11px] whitespace-nowrap"
              :style="{ color: OUTCOME_STYLE[entry.outcome].color }"
            >
              {{ entry.count }} {{ OUTCOME_STYLE[entry.outcome].label }}
            </span>
          </div>
        </div>
        <v-progress-linear
          :model-value="awaitingStep ? 100 : paramProgress"
          :indeterminate="Boolean(awaitingStep) && running"
          rounded
          height="4"
          :color="failed ? '#EF5350' : 'primary'"
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
          <div
            v-if="awaitingStep"
            class="flex items-center gap-2 py-[3px]"
            :class="running ? 'text-[#ffffffcc]' : 'text-[#EF5350]'"
          >
            <v-progress-circular
              v-if="running"
              indeterminate
              size="11"
              width="2"
              color="#42A5F5"
            />
            <v-icon
              v-else
              size="13"
              color="#EF5350"
            >
              mdi-alert-circle
            </v-icon>
            <span class="truncate">{{ awaitingStep.detail || awaitingStep.title }}</span>
          </div>
        </div>
      </div>

      <div
        v-if="!running"
        class="flex items-center justify-between gap-3 border-t border-[#ffffff0d] px-5 py-3"
      >
        <span class="text-xs text-[#ffffff88]">
          {{
            failedStep
              ? `Retry or skip the ${failedStep.title.toLowerCase()} step and carry on from there.`
              : job.reported_vehicle
                ? `The autopilot reports itself as ${job.reported_vehicle}.`
                : ''
          }}
        </span>
        <div class="flex items-center gap-2 shrink-0">
          <template v-if="failedStep">
            <v-btn
              size="small"
              prepend-icon="mdi-refresh"
              :loading="resuming === 'retry'"
              :disabled="Boolean(resuming)"
              @click="resume('retry')"
            >
              Retry step
            </v-btn>
            <v-btn
              size="small"
              prepend-icon="mdi-debug-step-over"
              :loading="resuming === 'skip'"
              :disabled="Boolean(resuming)"
              @click="resume('skip')"
            >
              Skip step
            </v-btn>
          </template>
          <v-btn
            size="small"
            color="primary"
            @click="close"
          >
            Close
          </v-btn>
        </div>
      </div>
    </div>
  </v-dialog>
</template>
