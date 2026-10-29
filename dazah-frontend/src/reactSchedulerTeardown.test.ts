/* @vitest-environment node */

import { expect, it, vi } from 'vitest'
import { unstable_cancelCallback, unstable_NormalPriority, unstable_scheduleCallback, type FrameCallbackType } from 'scheduler'
import { drainReactScheduler } from '../test/react-scheduler-teardown'

it('drains React continuations across host turns before the DOM is removed', async () => {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const observations: unknown[] = []
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { event: 'live-dom' },
  })
  const continuation: FrameCallbackType = () => {
    observations.push(window.event)
    return observations.length < 6 ? continuation : undefined
  }
  const task = unstable_scheduleCallback(unstable_NormalPriority, continuation)
  try {
    await drainReactScheduler()
    expect(observations).toEqual(Array.from({ length: 6 }, () => 'live-dom'))
  } finally {
    unstable_cancelCallback(task)
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
    else Reflect.deleteProperty(globalThis, 'window')
  }
})

it('uses real scheduler and deadline timers when the test enables fake timers', async () => {
  vi.useFakeTimers()
  const callback = vi.fn()
  const task = unstable_scheduleCallback(unstable_NormalPriority, callback)
  try {
    await drainReactScheduler()
    expect(callback).toHaveBeenCalledOnce()
  } finally {
    unstable_cancelCallback(task)
    vi.useRealTimers()
  }
})

it('fails a busy teardown instead of suppressing pending scheduler work', async () => {
  const continuation: FrameCallbackType = () => continuation
  const task = unstable_scheduleCallback(unstable_NormalPriority, continuation)
  try {
    await expect(drainReactScheduler(20)).rejects.toThrow(
      'React scheduler did not become idle before DOM teardown',
    )
  } finally {
    unstable_cancelCallback(task)
    await drainReactScheduler()
  }
})
