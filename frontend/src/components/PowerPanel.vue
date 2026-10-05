<script setup lang="ts">
import {
  BlueBanner,
  BlueButton,
  BlueButtonGroup,
  BlueInput,
  BlueStat,
  BlueSwitch,
  useBlueSnackbar,
} from '@bluerobotics/bluevue'
import { computed, onBeforeUnmount, ref } from 'vue'

import { isSitl } from '@/composables/vehicleStatus'
import { PowerApi, VehicleApi } from '@/services/api'
import type { BatteryPack, PowerReading } from '@/types/sitl'

const { notify, notifyError } = useBlueSnackbar()

// The draw curve is the BlueBoat's, fitted to its hull over field data, so it describes no other
// vehicle: a sub or a ground rover would be reported spending a boat's power.
const BLUEBOAT = 'BlueBoat'

const pack = ref<BatteryPack>({ enabled: false, cells: 4, packs: 2, capacity_ah: 18, idle_watts: 10 })
// The pack the vehicle is running, which is what the fields are measured against to decide
// whether there is anything left to apply, and what the reading below belongs to.
const applied = ref<BatteryPack | null>(null)
const reading = ref<PowerReading | null>(null)
// null once a read said the vehicle matches no preset; undefined while that is unknown.
const preset = ref<string | null | undefined>()
const busy = ref(false)

// On any other vehicle the whole section goes inert: nothing here would be true of it, and the
// service stops reporting the pack on its own, so there is nothing to switch off either.
const locked = computed(() => !isSitl.value || (preset.value !== undefined && preset.value !== BLUEBOAT))

const wrongVehicle = computed(() => {
  if (!isSitl.value || preset.value === undefined || preset.value === BLUEBOAT) {
    return ''
  }
  const vehicle = preset.value === null ? 'this vehicle' : `the ${preset.value} preset`
  return (
    `Only the BlueBoat can be simulated: the draw is that hull's own power curve, ` +
    `which describes ${vehicle} not at all.`
  )
})

// Nominal voltage of a Li-ion cell, which is how a pack is named: four of them make a 14.8 V 4S.
const NOMINAL_CELL_VOLTS = 3.7
const READING_INTERVAL_MS = 2000

// The battery Blue Robotics sells for the hull, and the counts a BlueBoat is fitted with. Anything
// else is a pack of the user's own, which is the only case the fields below are theirs to change.
const STANDARD_CELLS = 4
const STANDARD_CAPACITY_AH = 18
const STANDARD_COUNTS = [2, 4, 6, 8]

function standardCount(entry: BatteryPack): number | null {
  const standard = entry.cells === STANDARD_CELLS && entry.capacity_ah === STANDARD_CAPACITY_AH
  return standard && STANDARD_COUNTS.includes(entry.packs) ? entry.packs : null
}

const custom = ref(false)

function chooseStandard(count: number): void {
  custom.value = false
  pack.value = { ...pack.value, cells: STANDARD_CELLS, packs: count, capacity_ah: STANDARD_CAPACITY_AH }
}

const packButtons = computed(() => [
  {
    name: 'Custom pack',
    tooltip: 'A supply of your own, described by the fields below',
    preSelected: custom.value,
    onSelected: (): void => {
      custom.value = true
    },
  },
  ...STANDARD_COUNTS.map((count) => ({
    name: `${count}`,
    tooltip: `${count} of the 14.8 V ${STANDARD_CAPACITY_AH} Ah packs the hull is fitted with`,
    preSelected: !custom.value && standardCount(pack.value) === count,
    onSelected: () => chooseStandard(count),
  })),
])

const summary = computed(() => {
  const ampHours = pack.value.packs * pack.value.capacity_ah
  const volts = pack.value.cells * NOMINAL_CELL_VOLTS
  return `${ampHours.toFixed(0)} Ah at ${volts.toFixed(1)} V nominal, ${(ampHours * volts).toFixed(0)} Wh`
})

// From the pack being reported rather than the one on the fields, since that is what the
// autopilot is counting the charge of.
const runningAmpHours = computed(() => {
  const running = applied.value ?? pack.value
  return running.packs * running.capacity_ah
})

// Nothing to report while the pack is being charged, which is when the draw is zero.
function timeLeft(live: PowerReading): string | null {
  if (live.watts <= 0) {
    return null
  }
  const hours = ((live.charge / 100) * runningAmpHours.value * live.voltage) / live.watts
  return hours >= 1.5 ? `~${hours.toFixed(1)} h` : `~${(hours * 60).toFixed(0)} min`
}

const stats = computed(() => {
  const live = reading.value
  if (live === null) {
    return []
  }
  // Every figure is a model's answer rather than a measurement, which the tilde says outright.
  return [
    { label: 'Voltage', value: `~${live.voltage.toFixed(2)} V` },
    { label: 'Current', value: `~${live.current.toFixed(2)} A` },
    { label: 'Draw', value: `~${live.watts.toFixed(0)} W` },
    { label: 'Charge left', value: `~${live.charge.toFixed(1)} %` },
    { label: 'Charge spent', value: `~${live.consumed_mah.toFixed(0)} mAh` },
    { label: 'Time left', value: timeLeft(live) },
  ]
})

// Where the draw comes from, which is the part a gauge cannot show: the same speed costs a
// different amount against a stream, and a headwind is paid for on top of it.
const because = computed(() => {
  const live = reading.value
  if (live === null) {
    return ''
  }
  if (live.charging) {
    return `Charging at ${Math.abs(live.current).toFixed(0)} A until the pack reads full.`
  }
  const wind =
    live.headwind >= 0
      ? `into ${live.headwind.toFixed(1)} m/s of headwind`
      : `with ${Math.abs(live.headwind).toFixed(1)} m/s of wind behind`
  return `${live.water_speed.toFixed(2)} m/s through the water, ${wind}.`
})

const pendingChange = computed(() => {
  const running = applied.value
  return (
    running === null ||
    (Object.keys(running) as (keyof BatteryPack)[]).some((key) => running[key] !== pack.value[key])
  )
})

let poll: ReturnType<typeof setInterval> | null = null

function stopPolling(): void {
  if (poll !== null) {
    clearInterval(poll)
    poll = null
  }
}

// A reading is a snapshot of a loop that keeps running, so it is polled rather than pushed. The
// backend answers from what it last computed, without asking the vehicle anything.
async function refreshReading(): Promise<void> {
  try {
    reading.value = (await PowerApi.get()).reading
    if (reading.value === null) {
      stopPolling()
    }
  } catch {
    // Whatever went wrong will still be wrong in two seconds, and a notice every two seconds
    // is worse than the last reading staying on screen.
    stopPolling()
  }
}

function startPolling(): void {
  if (poll === null) {
    poll = setInterval(refreshReading, READING_INTERVAL_MS)
  }
}

onBeforeUnmount(stopPolling)

function follow(state: { pack: BatteryPack; reading: PowerReading | null }): void {
  applied.value = { ...state.pack }
  reading.value = state.reading
  if (state.pack.enabled) {
    startPolling()
  } else {
    stopPolling()
  }
}

async function reload(): Promise<void> {
  // A vehicle that cannot be asked which preset it runs leaves the panel usable rather than
  // locked, the same way the rest of the extension treats a read it did not get.
  preset.value = await VehicleApi.activePreset().catch(() => undefined)
  try {
    const state = await PowerApi.get()
    pack.value = { ...state.pack }
    custom.value = standardCount(state.pack) === null
    follow(state)
  } catch (error) {
    notifyError(error, 'Could not read the simulated battery pack')
  }
}

defineExpose({ reload })

async function apply(): Promise<void> {
  busy.value = true
  try {
    const state = await PowerApi.set(pack.value)
    follow(state)
    notify(
      state.pack.enabled
        ? `The vehicle now reports a ${summary.value} pack.`
        : 'The simulator has its own battery back.',
      { severity: 'success' }
    )
  } catch (error) {
    notifyError(error, 'Could not set the simulated battery pack')
  } finally {
    busy.value = false
  }
}

async function recharge(): Promise<void> {
  busy.value = true
  try {
    notify((await PowerApi.recharge()).detail, { severity: 'success' })
    await refreshReading()
  } catch (error) {
    notifyError(error, 'Could not charge the pack')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <BlueBanner
      v-if="wrongVehicle"
      severity="warning"
      :text="wrongVehicle"
    />

    <div
      class="flex flex-col gap-4"
      :class="{ 'opacity-50 pointer-events-none': locked }"
    >
      <BlueSwitch
        v-model="pack.enabled"
        name="simulated-pack"
        label="Simulate the pack"
        theme="dark"
        :disabled="locked || busy"
        info-tooltip="The vehicle reports this pack instead of the simulator's own, which only follows the throttle. The draw comes from the BlueBoat's measured power curve and rises against a stream or a headwind, and the autopilot counts the charge spent, so Cockpit shows it as it would a real monitor."
      />

      <div v-if="stats.length">
        <div class="flex flex-wrap items-stretch gap-2">
          <BlueStat
            v-for="stat in stats"
            :key="stat.label"
            :label="stat.label"
            :value="stat.value"
          />
        </div>
        <div class="mt-2 text-sm text-[#ffffff88]">
          {{ because }}
        </div>
      </div>

      <div>
        <div class="mx-auto mb-4 h-px w-[70%] bg-[#ffffff0b]" />
        <div class="text-base font-bold uppercase tracking-wide text-[#989898] mt-[5px] mb-[17px] truncate">
          Pack
        </div>
        <div class="flex flex-wrap gap-3">
          <BlueButtonGroup
            :key="`${custom}-${pack.packs}-${pack.cells}-${pack.capacity_ah}`"
            label="Batteries"
            theme="dark"
            type="switch"
            :disabled="locked"
            :button-items="packButtons"
            info-tooltip="How many of the 14.8 V 18 Ah packs Blue Robotics sells for the hull are aboard. Custom pack hands the three fields below over, for a supply of your own."
          />
          <BlueInput
            v-model="pack.cells"
            name="cells"
            label="Cells in series"
            type="number"
            theme="dark"
            width="240px"
            suffix="S"
            :min="1"
            :max="24"
            :step="1"
            :disabled="locked || !custom"
          />
          <BlueInput
            v-model="pack.packs"
            name="packs"
            label="Packs in parallel"
            type="number"
            theme="dark"
            width="240px"
            :min="1"
            :max="12"
            :step="1"
            :disabled="locked || !custom"
          />
          <BlueInput
            v-model="pack.capacity_ah"
            name="capacity"
            label="Capacity per pack"
            type="number"
            theme="dark"
            width="240px"
            suffix="Ah"
            :min="0.1"
            :max="1000"
            :step="0.5"
            :disabled="locked || !custom"
            info-tooltip="A smaller pack is what makes a short recording show the charge going down; SIM_SPEEDUP does the same by running the mission faster."
          />
          <BlueInput
            v-model="pack.idle_watts"
            name="idle-watts"
            label="Idle electronics consumption"
            type="number"
            theme="dark"
            width="240px"
            suffix="W"
            :min="0"
            :max="1000"
            :step="1"
            :disabled="locked"
            info-tooltip="What the computer, autopilot and radio draw whether the vehicle is moving or not, so a pack left switched on empties on this alone."
          />
        </div>
        <div class="mt-3 text-sm text-[#ffffff88]">
          {{ summary }}
        </div>
      </div>

      <div class="flex items-center justify-between gap-2">
        <BlueButton
          density="compact"
          theme="dark"
          icon="mdi-battery-charging"
          :disabled="locked || busy || reading === null"
          @click="recharge"
        >
          Recharge
        </BlueButton>
        <BlueButton
          variant="filled"
          theme="dark"
          :loading="busy"
          :disabled="locked || !pendingChange"
          @click="apply"
        >
          Apply
        </BlueButton>
      </div>
    </div>
  </div>
</template>
