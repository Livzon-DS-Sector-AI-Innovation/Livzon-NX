import { unstable_cancelCallback, unstable_IdlePriority, unstable_scheduleCallback } from 'scheduler'

const realSetTimeout = globalThis.setTimeout.bind(globalThis)
const realClearTimeout = globalThis.clearTimeout.bind(globalThis)
const realSetImmediate = globalThis.setImmediate?.bind(globalThis)

function waitForSchedulerIdle(timeoutMs: number): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    // React's normal-priority passive effects may yield over many host turns.
    // An idle-priority barrier runs after those effects and their continuations.
    const task = unstable_scheduleCallback(unstable_IdlePriority, () => {
      realClearTimeout(deadline)
      resolve()
    })
    const deadline = realSetTimeout(() => {
      unstable_cancelCallback(task)
      reject(new Error('React scheduler did not become idle before DOM teardown'))
    }, timeoutMs)
  })
}

export async function drainReactScheduler(timeoutMs = 5000): Promise<void> {
  await waitForSchedulerIdle(timeoutMs)
  if (realSetImmediate) {
    await new Promise<void>((resolve) => realSetImmediate(resolve))
  }
  await new Promise<void>((resolve) => realSetTimeout(resolve, 0))
  // DOM timers may enqueue another passive-effect callback during the host turn.
  await waitForSchedulerIdle(timeoutMs)
}
