import { reactive } from 'vue'

// Global blocking-overlay state, shown while the autopilot is restarting or applying
// a configuration so the user cannot fire overlapping operations.
export const loading = reactive({
  show: false,
  message: 'Applying…',
})

export function showLoading(message = 'Applying…'): void {
  loading.message = message
  loading.show = true
}

export function hideLoading(): void {
  loading.show = false
}
