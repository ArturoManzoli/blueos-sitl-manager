<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type BannerSeverity = 'error' | 'warning' | 'info' | 'success'

interface Look {
  icon: string
  color: string
  background: string
  border: string
}

const LOOKS: Record<BannerSeverity, Look> = {
  error: { icon: 'mdi-alert-circle-outline', color: '#EF9A9A', background: '#CF667926', border: '#CF667955' },
  warning: { icon: 'mdi-alert', color: '#FFB74D', background: '#FB8C0022', border: '#FB8C0055' },
  info: { icon: 'mdi-information-outline', color: '#81D4FA', background: '#4FC3F71A', border: '#4FC3F744' },
  success: { icon: 'mdi-check-circle-outline', color: '#A5D6A7', background: '#66BB6A22', border: '#66BB6A55' },
}

const props = defineProps<{
  /** The message, which the banner is only as wide as while it is open. */
  text: string
  /** Which of the standard looks to take (default 'info'). */
  severity?: BannerSeverity
  /** An mdi class, in place of the severity's icon. */
  icon?: string
  /** Icon and text colour, in place of the severity's. */
  color?: string
  /** Fill, in place of the severity's. */
  background?: string
  /** Hairline, in place of the severity's. */
  border?: string
  /** Whether it starts open (default true). */
  expanded?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:expanded', value: boolean): void
}>()

const box = ref<HTMLElement | null>(null)
const reveal = ref<HTMLElement | null>(null)
const label = ref<HTMLElement | null>(null)

const isOpen = ref(props.expanded ?? true)
const messageWidth = ref(0)
const messageHeight = ref(0)
const measured = ref(false)

const look = computed(() => LOOKS[props.severity ?? 'info'])

const boxStyle = computed(() => ({
  color: props.color ?? look.value.color,
  backgroundColor: props.background ?? look.value.background,
  borderColor: props.border ?? look.value.border,
}))

// The window onto the message, which is what grows and shrinks: the button around it is sized by
// its content, so it follows along without a size of its own to animate. Shut is nothing to show
// and needs no measurement; open before the first one is the message laid out as it lays itself
// out, which is what the measurement will say anyway.
const revealStyle = computed(() => {
  if (!isOpen.value) {
    return { width: '0px', height: '0px' }
  }
  return measured.value ? { width: `${messageWidth.value}px`, height: `${messageHeight.value}px` } : undefined
})

// The message is held at the width it was measured at whether the window is open or not, so it
// keeps the shape it ends up in and the window uncovers it rather than rewrapping it every frame.
const labelStyle = computed(() => (measured.value ? { width: `${messageWidth.value}px` } : undefined))

// How much room the message asks for, and how tall it is once it has it. Sizes are read off the
// elements laid out by their content and put back within the one task, so nothing is painted in
// between, and `transition: none` covers the reads in case one would otherwise leave a value for
// an animation to start from. Fractions are kept and rounded up: a width rounded down by half a
// pixel is a width the last word does not fit in.
function measure(): void {
  const button = box.value
  const pane = reveal.value
  const message = label.value
  if (!button || !pane || !message) {
    return
  }
  const buttonStyle = button.style.cssText
  const paneStyle = pane.style.cssText
  const messageStyle = message.style.cssText
  const putBack = (): void => {
    button.style.cssText = buttonStyle
    pane.style.cssText = paneStyle
    message.style.cssText = messageStyle
    button.classList.remove('bluevue-banner--measuring')
  }
  button.classList.add('bluevue-banner--measuring')

  button.style.width = '100%'
  pane.style.width = 'auto'
  pane.style.height = 'auto'
  pane.style.flex = '1 1 auto'
  message.style.width = 'auto'
  const room = message.getBoundingClientRect().width
  // Nowhere to lay anything out, the banner being inside something closed or off screen: whatever
  // it measured last is a better answer than none.
  if (room <= 0) {
    putBack()
    return
  }

  message.style.width = 'max-content'
  const wanted = message.getBoundingClientRect().width

  // As wide as the message asks for, or as wide as there is room for, in which case it wraps and
  // the banner is taller instead.
  messageWidth.value = Math.min(Math.ceil(wanted), Math.floor(room))
  message.style.width = `${messageWidth.value}px`
  messageHeight.value = Math.ceil(message.getBoundingClientRect().height)

  putBack()
  measured.value = true
}

function toggle(): void {
  // A click is proof of being on screen, which a banner mounted inside a closed panel was not.
  measure()
  isOpen.value = !isOpen.value
  emit('update:expanded', isOpen.value)
}

let observer: ResizeObserver | null = null

onMounted(() => {
  measure()
  // The icon is a glyph, so how much of the row it takes is one thing before the font arrives and
  // another after.
  void document.fonts?.ready.then(measure)
  const parent = box.value?.parentElement
  if (parent) {
    // Only a change in the room available is worth measuring again for: opening the banner makes
    // its surroundings taller, and measuring from inside that notification loops.
    let room = parent.clientWidth
    observer = new ResizeObserver(() => {
      if (parent.clientWidth !== room) {
        room = parent.clientWidth
        // On the next frame rather than here: laying the message out again from inside the
        // notification resizes what is being reported on, which the browser calls a loop.
        requestAnimationFrame(measure)
      }
    })
    observer.observe(parent)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})

// After the render, since a new message is measured on screen rather than in the props.
watch(() => props.text, measure, { flush: 'post' })

watch(
  () => props.expanded,
  (value) => {
    if (value !== undefined) {
      isOpen.value = value
    }
  }
)
</script>

<template>
  <button
    ref="box"
    type="button"
    class="bluevue-banner bluevue-elevation-1-soft flex w-fit items-start rounded-[6px] border text-left text-xs cursor-pointer px-3 py-2"
    :style="boxStyle"
    :aria-expanded="isOpen"
    :aria-label="text"
    :title="isOpen ? undefined : text"
    @click="toggle"
  >
    <span
      class="mdi shrink-0 text-[16px] leading-none"
      :class="props.icon ?? look.icon"
    />
    <!-- Free to shrink until there is a measurement to hold it to, so a banner opened before it
         could measure itself gives its message the room there is rather than clipping it. -->
    <span
      ref="reveal"
      class="bluevue-banner__reveal overflow-hidden"
      :class="measured ? 'shrink-0' : ''"
      :style="revealStyle"
    >
      <!-- The gap after the icon rides with the message, so a shut window leaves none of it. -->
      <span
        ref="label"
        class="block pl-2"
        :style="labelStyle"
      >{{ text }}</span>
    </span>
  </button>
</template>
