import { reactive } from 'vue'

type Color = 'success' | 'error' | 'info' | 'warning'

export const snackbar = reactive({
  show: false,
  text: '',
  color: 'info' as Color,
})

export function notify(text: string, color: Color = 'info'): void {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

export function notifyError(error: unknown, fallback = 'Request failed'): void {
  const axiosDetail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  const message = (error as Error)?.message
  notify(axiosDetail ?? message ?? fallback, 'error')
}
