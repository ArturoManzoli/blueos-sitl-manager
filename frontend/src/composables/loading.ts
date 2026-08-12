import { reactive } from 'vue'

// Global blocking-overlay state, shown while the autopilot is restarting or applying
// a configuration so the user cannot fire overlapping operations.
export const loading = reactive({
  show: false,
  message: 'Applying…',
  dismissible: false,
})

/**
 * Raise the overlay.
 *
 * @param message What is being waited on.
 * @param dismissible Whether the user may close it and carry on. Reserved for waits that
 * only delay information, like the first read of the vehicle: an operation that is writing
 * to the autopilot must stay blocking, since dismissing it would leave the page live over
 * a change still in flight.
 */
export function showLoading(message = 'Applying…', dismissible = false): void {
  loading.message = message
  loading.dismissible = dismissible
  loading.show = true
}

export function hideLoading(): void {
  loading.show = false
}
