<script setup lang="ts">
import { BlueButton, BlueIcon, BlueSpinner, BlueStepsDialog, useBlueSnackbar } from '@bluerobotics/bluevue'
import { computed, onUnmounted, ref, watch } from 'vue'

import { VehicleApi } from '@/services/api'
import type { ApplyJob, ParamOutcome } from '@/types/sitl'

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

const { notifyError } = useBlueSnackbar()

const POLL_INTERVAL = 400
const PARAMETERS_STEP = 'parameters'

const job = ref<ApplyJob | null>(null)
const resuming = ref<'retry' | 'skip' | null>(null)
let timer: number | undefined

const running = computed(() => job.value?.state === 'running')

const OUTCOME_STYLE: Record<ParamOutcome, { label: string; color: string }> = {
  written: { label: 'written', color: '#66BB6A' },
  unchanged: { label: 'unchanged', color: '#90A4AE' },
  unsupported: { label: 'not supported', color: '#FFB74D' },
  failed: { label: 'rejected', color: '#EF5350' },
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

const progressLabel = computed(() => {
  if (awaitingStep.value) return awaitingStep.value.title
  const current = job.value?.current_param
  return current
    ? `Sending parameter ${(job.value?.params_done ?? 0) + 1}/${job.value?.params_total}: ${current}`
    : `${job.value?.params_done ?? 0}/${job.value?.params_total ?? 0} parameters processed`
})

const footerNote = computed(() => {
  if (failedStep.value) {
    return `Retry or skip the ${failedStep.value.title.toLowerCase()} step and carry on from there.`
  }
  return job.value?.reported_vehicle ? `The autopilot reports itself as ${job.value.reported_vehicle}.` : ''
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
  <BlueStepsDialog
    v-if="job"
    :model-value="modelValue"
    :state="job.state === 'running' ? 'running' : job.state === 'failed' ? 'failed' : 'done'"
    :title="running ? `Applying ${job.title}` : job.title"
    :subtitle="job.detail || activeStep?.detail || 'Working…'"
    :steps="job.steps"
    :progress-label="progressLabel"
    :progress="awaitingStep ? undefined : paramProgress"
    :indeterminate="Boolean(awaitingStep)"
    @update:model-value="close"
  >
    <template #badges>
      <span
        v-for="entry in outcomeCounts"
        :key="entry.outcome"
        class="whitespace-nowrap text-[11px]"
        :style="{ color: OUTCOME_STYLE[entry.outcome].color }"
      >
        {{ entry.count }} {{ OUTCOME_STYLE[entry.outcome].label }}
      </span>
    </template>

    <template #log>
      <div
        v-for="record in job.records"
        :key="record.name"
        class="flex items-center justify-between gap-3 py-[2px]"
      >
        <span class="truncate text-[#ffffffcc]">{{ record.name }}</span>
        <span class="flex shrink-0 items-center gap-2">
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
        <BlueSpinner
          v-if="running"
          :size="11"
          :width="2"
          color="#42A5F5"
        />
        <BlueIcon
          v-else
          name="mdi-alert-circle"
          :size="13"
          color="#EF5350"
        />
        <span class="truncate">{{ awaitingStep.detail || awaitingStep.title }}</span>
      </div>
    </template>

    <template
      v-if="!running"
      #footer
    >
      <span class="text-xs text-[#ffffff88]">{{ footerNote }}</span>
      <div class="flex shrink-0 items-center gap-2">
        <template v-if="failedStep">
          <BlueButton
            density="compact"
            theme="dark"
            icon="mdi-refresh"
            :loading="resuming === 'retry'"
            :disabled="Boolean(resuming)"
            @click="resume('retry')"
          >
            Retry step
          </BlueButton>
          <BlueButton
            density="compact"
            theme="dark"
            icon="mdi-debug-step-over"
            :loading="resuming === 'skip'"
            :disabled="Boolean(resuming)"
            @click="resume('skip')"
          >
            Skip step
          </BlueButton>
        </template>
        <BlueButton
          variant="filled"
          density="compact"
          theme="dark"
          @click="close"
        >
          Close
        </BlueButton>
      </div>
    </template>
  </BlueStepsDialog>
</template>
