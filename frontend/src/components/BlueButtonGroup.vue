<template>
  <div class="flex w-full justify-between items-center">
    <div v-if="label">
      <label
        class="text-start mr-6"
        :class="theme === 'dark' ? 'text-white' : 'text-black'"
      >{{ label }}</label>
    </div>
    <div v-else />
    <slot name="insetElement" />
    <div class="flex items-center">
      <div
        v-if="infoTooltip"
        class="relative group inline-flex items-center mr-2"
      >
        <span
          class="mdi mdi-information-outline text-[16px] opacity-60 cursor-help"
          :class="theme === 'dark' ? 'text-white' : 'text-black'"
        />
        <div
          class="absolute bottom-full mb-1 right-0 hidden group-hover:block w-max max-w-[280px] px-2 py-1 text-xs rounded bg-gray-700 text-white z-[1000]"
        >
          {{ infoTooltip }}
        </div>
      </div>
      <div
        ref="trackRef"
        class="relative flex justify-end overflow-hidden rounded-[6px] elevation-1 z-[666]"
        :class="[theme === 'dark' ? 'bg-[#464646AA]' : 'bg-[#00000011]', disabled ? 'opacity-50 pointer-events-none' : '']"
        :style="{ height: height || '30px' }"
      >
        <div
          id="border-releif"
          class="absolute left-[-20px] top-0 h-full w-[6px] bg-[#6699cc] z-[20] pointer-events-none"
        />
        <template
          v-for="(btn, idx) in buttonItems"
          :key="btn.name"
        >
          <button
            :disabled="disabled || btn.disabled"
            :title="btn.name"
            class="flex items-center justify-center px-4 text-sm font-medium transition-colors duration-200"
            :class="[
              selected[idx] ? 'text-white' : theme === 'dark' ? 'text-[#ffffff99]' : 'text-[#00000066]',
              selected[idx] && type === 'switch' ? 'elevation-5' : 'elevation-0',
              disabled || btn.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
            ]"
            :style="{ backgroundColor: selected[idx] ? btn.activeColor || '#0B5087' : undefined }"
            @click="!btn.disabled && toggleButton(idx)"
          >
            <div class="relative group inline-block min-w-0">
              <p
                data-bbg-label
                class="text-xs"
                :class="isWide ? 'truncate max-w-[150px]' : ''"
              >
                {{ btn.name }}
              </p>
              <div
                v-if="btn.tooltip"
                class="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block whitespace-no-wrap px-2 py-1 text-xs rounded bg-gray-700 text-white"
              >
                {{ btn.tooltip }}
              </div>
            </div>
          </button>
          <div
            v-if="idx < buttonItems.length - 1"
            class="w-[1px] bg-[#FFFFFF22] my-2"
          />
        </template>
        <div
          v-if="buttonsMenu?.length"
          class="w-[1px] bg-[#FFFFFF22] my-2 mr-[3px]"
        />
        <div
          v-if="buttonsMenu?.length"
          v-click-outside="() => (menuOpen = false)"
          class="relative"
        >
          <div
            class="px-0 flex items-center justify-center h-full cursor-pointer"
            :class="theme === 'dark' ? 'text-white' : 'text-black'"
            @click="openMenu($event)"
          >
            <div class="self-center mdi mdi-menu-right text-[20px] mr-[2px] opacity-80" />
          </div>
          <div
            v-if="menuOpen"
            class="fixed elevation-5 border-[1px] rounded-[4px] border-[#FFFFFF22] z-100"
            :class="theme === 'dark' ? 'text-[#FFFFFF99] bg-[#363636]' : 'text-black hover:bg-gray-200'"
            :style="flipX ? { top: menuY + 'px', right: menuRight + 'px' } : { top: menuY + 'px', left: menuX + 'px' }"
          >
            <ul>
              <div
                v-for="(item, idx) in buttonsMenu"
                :key="item.name"
              >
                <button
                  :disabled="item.menuItemDisabled"
                  class="block w-full text-left px-4 py-2 text-[14px]"
                  :class="[
                    idx < buttonsMenu.length - 1 ? 'border-b border-white' : '',
                    theme === 'dark' ? 'hover:bg-[#333333]' : 'hover:bg-gray-100',
                    item.menuItemDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
                  ]"
                  @click="
                    () => {
                      item.action()
                      menuOpen = false
                    }
                  "
                >
                  {{ item.name }}
                </button>
              </div>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

/**
 * One button in the group
 */
interface ButtonItem {
  /** Name of the button, displayed as text */
  name: string
  /** Optional tooltip text displayed on hover */
  tooltip?: string
  /** Whether this button is pre-selected (only for 'switch' type) */
  preSelected?: boolean
  /** Optional color for the button when active */
  activeColor?: string
  /** Whether the button is disabled */
  disabled?: boolean
  /** Callback when the button is selected */
  onSelected?: () => void
  /** Custom options to handle button item press */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  options?: Record<string, any>
}

/**
 * One item in the menu
 */
interface MenuItem {
  /** Name of the menu item, displayed as text */
  name: string
  /** Callback when the menu item is clicked */
  action: () => void
  /** Disable the menu item */
  menuItemDisabled?: boolean
}

const props = defineProps<{
  /** List of buttons in the group */
  buttonItems: ButtonItem[]
  /** Optional menu items to display in a dropdown */
  buttonsMenu?: MenuItem[]
  /** Whether the entire button group is disabled */
  disabled?: boolean
  /** Theme of the button group */
  theme?: 'light' | 'dark'
  /** Type of button group, 'switch' for single selection or 'toggle' for multiple selections */
  type: 'switch' | 'toggle'
  /** Height of the button group container */
  height?: string
  /** Label text on the left side of the button group */
  label?: string
  /** Optional info tooltip shown via an info icon next to the control. */
  infoTooltip?: string
}>()

const emit = defineEmits<{
  (e: 'update:selected', value: boolean[]): void
}>()

const selected = ref<boolean[]>([])
const menuOpen = ref(false)

// Once the buttons' natural width would exceed this, cap each label so long names
// ellipsize instead of letting the group sprawl (or clip) past the panel.
const GROUP_WIDTH_LIMIT = 850
const BUTTON_HORIZONTAL_PADDING = 32 // px-4 on both sides
const trackRef = ref<HTMLElement | null>(null)
const isWide = ref(false)
let resizeObserver: ResizeObserver | null = null

const measureWidth = (): void => {
  const track = trackRef.value
  if (!track) return
  // Each label keeps its full text width in scrollWidth even while ellipsized, so the
  // natural width is independent of the cap we apply, avoiding a measure/toggle loop.
  const labels = track.querySelectorAll<HTMLElement>('[data-bbg-label]')
  let natural = 0
  labels.forEach((label) => {
    natural += label.scrollWidth + BUTTON_HORIZONTAL_PADDING
  })
  natural += Math.max(0, labels.length - 1) // 1px separators between buttons
  isWide.value = natural > GROUP_WIDTH_LIMIT
}
const menuX = ref<number>(0)
const menuY = ref<number>(0)
const menuRight = ref<number>(0)
const flipX = ref<boolean>(false)

const initSelected = (): void => {
  const items = props.buttonItems
  if (props.type === 'switch') {
    const first = items.findIndex((b) => b.preSelected)
    const idx = first >= 0 ? first : 0
    selected.value = items.map((_, i) => i === idx)
  } else {
    selected.value = items.map((b) => !!b.preSelected)
  }
  emit('update:selected', selected.value)
}

const toggleButton = (idx: number): void => {
  if (props.disabled || props.buttonItems[idx].disabled) return
  const btn = props.buttonItems[idx]
  if (props.type === 'switch') {
    if (!selected.value[idx]) {
      selected.value = selected.value.map((_, i) => i === idx)
      btn.onSelected?.()
    }
  } else {
    selected.value[idx] = !selected.value[idx]
    if (selected.value[idx]) btn.onSelected?.()
  }
  emit('update:selected', selected.value)
}

const openMenu = (event: MouseEvent): void => {
  const x = event.clientX
  const y = event.clientY
  menuX.value = x
  menuY.value = y
  menuRight.value = window.innerWidth - x
  flipX.value = menuRight.value < 200
  menuOpen.value = true
}

onMounted(() => {
  initSelected()
  nextTick(measureWidth)
  if (typeof ResizeObserver !== 'undefined' && trackRef.value) {
    resizeObserver = new ResizeObserver(() => measureWidth())
    resizeObserver.observe(trackRef.value)
  }
})

onBeforeUnmount(() => resizeObserver?.disconnect())

watch(
  () => props.buttonItems.length,
  initSelected,
  { deep: true, immediate: true }
)

watch(
  () => props.buttonItems.map((item) => item.name).join('|'),
  () => nextTick(measureWidth)
)
</script>
