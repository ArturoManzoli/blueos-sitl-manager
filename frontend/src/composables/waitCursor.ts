// The pointer is the only feedback there is while a click waits on a request that has yet to
// put anything on screen — starting a configuration job answers a moment before its progress
// dialog can open. Counted rather than a flag, so overlapping waits cannot clear each other.
let waiting = 0

const WAITING_CLASS = 'sitl-waiting'

function apply(): void {
  document.documentElement.classList.toggle(WAITING_CLASS, waiting > 0)
}

/** Run `work` with the wait pointer up. */
export async function withWaitCursor<T>(work: () => Promise<T>): Promise<T> {
  waiting += 1
  apply()
  try {
    return await work()
  } finally {
    waiting -= 1
    apply()
  }
}
