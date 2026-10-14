/* @vitest-environment happy-dom */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { transitionAppearance } from './appearanceTransition'

beforeEach(() => {
  Object.defineProperty(document.documentElement, 'animate', { value: vi.fn(), configurable: true })
  Object.defineProperty(document, 'startViewTransition', { value: vi.fn(), configurable: true })
})

afterEach(() => {
  vi.restoreAllMocks()
  Reflect.deleteProperty(document.documentElement, 'animate')
  Reflect.deleteProperty(document, 'startViewTransition')
  delete document.documentElement.dataset.appearanceTransition
})

function fixture() {
  const button = document.createElement('button')
  vi.spyOn(button, 'getBoundingClientRect').mockReturnValue(new DOMRect(30, 40, 32, 28))
  vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false } as MediaQueryList)
  const cancel = vi.fn()
  // happy-dom has no Web Animations implementation; this double covers the API we consume.
  const animation: Pick<Animation, 'cancel'> = { cancel }
  const animate = vi.spyOn(document.documentElement, 'animate').mockReturnValue(animation as Animation)
  let finish = () => {}
  const transition = {
    ready: Promise.resolve(),
    finished: new Promise<void>((resolve) => { finish = resolve }),
    updateCallbackDone: Promise.resolve(),
    skipTransition: vi.fn(),
    types: new Set<string>(),
  }
  const start = vi.spyOn(document, 'startViewTransition').mockImplementation((callback) => {
    if (typeof callback === 'function') void callback()
    return transition
  })
  const update = vi.fn()
  return { button, animate, cancel, transition, start, update, finish }
}

it('reveals from the button lower left toward the upper right and clears temporary styles', async () => {
  const { button, animate, cancel, update, finish } = fixture()
  transitionAppearance(button, update, true)
  await Promise.resolve()
  expect(update).toHaveBeenCalledOnce()
  expect(animate).toHaveBeenCalledWith({ clipPath: [
    'circle(0px at 30px 68px)',
    `circle(${Math.hypot(window.innerWidth, window.innerHeight)}px at ${window.innerWidth}px 0px)`,
  ] }, expect.objectContaining({ duration: 480, fill: 'both', pseudoElement: '::view-transition-new(root)' }))
  expect(document.documentElement.dataset.appearanceTransition).toBe('active')
  finish()
  await Promise.resolve()
  expect(cancel).toHaveBeenCalledOnce()
  expect(document.documentElement.dataset.appearanceTransition).toBeUndefined()
  expect(document.documentElement.style.getPropertyValue('--appearance-reveal-x')).toBe('')
  expect(document.documentElement.style.getPropertyValue('--appearance-reveal-y')).toBe('')
})

it('sets the reveal mask before capturing the new theme, including while capture is pending', async () => {
  const { button, start, transition, animate, finish } = fixture()
  let ready = () => {}
  transition.ready = new Promise<void>((resolve) => { ready = resolve })
  const update = vi.fn(() => {
    expect(document.documentElement.dataset.appearanceTransition).toBe('active')
    expect(document.documentElement.style.getPropertyValue('--appearance-reveal-x')).toBe('30px')
    expect(document.documentElement.style.getPropertyValue('--appearance-reveal-y')).toBe('68px')
  })
  transitionAppearance(button, update, true)
  expect(start).toHaveBeenCalledOnce()
  expect(update).toHaveBeenCalledOnce()
  expect(animate).not.toHaveBeenCalled()
  ready()
  await Promise.resolve()
  expect(animate).toHaveBeenCalledOnce()
  finish()
  await Promise.resolve()
})

it.each(['same-color', 'reduced-motion', 'unsupported'])('switches immediately for %s', async (reason) => {
  const { button, start, update, animate } = fixture()
  if (reason === 'reduced-motion') vi.mocked(window.matchMedia).mockReturnValue({ matches: true } as MediaQueryList)
  if (reason === 'unsupported') Object.defineProperty(document, 'startViewTransition', { value: undefined, configurable: true })
  transitionAppearance(button, update, reason !== 'same-color')
  expect(update).toHaveBeenCalledOnce()
  expect(start).not.toHaveBeenCalled()
  expect(animate).not.toHaveBeenCalled()
})

it('still applies the preference when starting a transition fails', () => {
  const { button, start, update } = fixture()
  start.mockImplementation(() => { throw new Error('unavailable') })
  transitionAppearance(button, update, true)
  expect(update).toHaveBeenCalledOnce()
  expect(document.documentElement.dataset.appearanceTransition).toBeUndefined()
})

it('skips a failed capture without losing the selected preference', async () => {
  const { button, transition, update, animate, finish } = fixture()
  transition.ready = Promise.reject(new Error('capture failed'))
  transitionAppearance(button, update, true)
  await Promise.resolve()
  await Promise.resolve()
  expect(update).toHaveBeenCalledOnce()
  expect(transition.skipTransition).toHaveBeenCalledOnce()
  expect(animate).not.toHaveBeenCalled()
  finish()
  await Promise.resolve()
})

it('keeps the newer transition active when a previous transition finishes', async () => {
  const first = fixture()
  transitionAppearance(first.button, first.update, true)
  await Promise.resolve()
  const second = fixture()
  transitionAppearance(second.button, second.update, true)
  await Promise.resolve()
  expect(first.transition.skipTransition).toHaveBeenCalledOnce()
  expect(first.cancel).toHaveBeenCalledOnce()
  first.finish()
  await Promise.resolve()
  expect(document.documentElement.dataset.appearanceTransition).toBe('active')
  second.finish()
  await Promise.resolve()
  expect(document.documentElement.dataset.appearanceTransition).toBeUndefined()
})

it('does not start an obsolete animation when rapid switching supersedes a pending capture', async () => {
  const first = fixture()
  let ready = () => {}
  first.transition.ready = new Promise<void>((resolve) => { ready = resolve })
  transitionAppearance(first.button, first.update, true)
  const second = fixture()
  transitionAppearance(second.button, second.update, true)
  await Promise.resolve()
  const calls = second.animate.mock.calls.length
  ready()
  await Promise.resolve()
  expect(second.animate).toHaveBeenCalledTimes(calls)
  first.finish()
  second.finish()
  await Promise.resolve()
})

it('releases the current animation and mask when the next selection needs no animation', async () => {
  const { button, update, cancel, animate, finish } = fixture()
  transitionAppearance(button, update, true)
  await Promise.resolve()
  transitionAppearance(button, update, false)
  expect(cancel).toHaveBeenCalledOnce()
  expect(animate).toHaveBeenCalledOnce()
  expect(update).toHaveBeenCalledTimes(2)
  expect(document.documentElement.dataset.appearanceTransition).toBeUndefined()
  finish()
  await Promise.resolve()
})

it('uses an opacity fade without a circular mask on limited hardware', async () => {
  const { button, update, animate, finish } = fixture()
  vi.spyOn(navigator, 'hardwareConcurrency', 'get').mockReturnValue(2)
  transitionAppearance(button, update, true)
  await Promise.resolve()
  expect(update).toHaveBeenCalledOnce()
  expect(document.documentElement.dataset.appearanceTransition).toBe('fade')
  expect(animate).toHaveBeenCalledWith({ opacity: [0, 1] }, expect.objectContaining({ duration: 160 }))
  finish()
  await Promise.resolve()
  expect(document.documentElement.dataset.appearanceTransition).toBeUndefined()
})

it('stops frame sampling when a transition is superseded and finishes', async () => {
  const { button, finish } = fixture()
  const request = vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(42)
  const cancel = vi.spyOn(window, 'cancelAnimationFrame')
  transitionAppearance(button, () => {}, true)
  await Promise.resolve()
  expect(request).toHaveBeenCalledOnce()
  transitionAppearance(button, () => {}, false)
  expect(cancel).toHaveBeenCalledWith(42)
  finish()
  await Promise.resolve()
})

it.each([[150, 'fade'], [450, 'none']] as const)('adapts the current switch after a %i ms capture to %s', async (duration, expected) => {
  vi.resetModules()
  const isolated = await import('./appearanceTransition')
  const { button, update, animate, transition, finish } = fixture()
  vi.spyOn(performance, 'now').mockReturnValueOnce(0).mockReturnValueOnce(0).mockReturnValue(duration)
  isolated.transitionAppearance(button, update, true)
  await Promise.resolve()
  expect(update).toHaveBeenCalledOnce()
  if (expected === 'fade') {
    expect(animate).toHaveBeenCalledWith({ opacity: [0, 1] }, expect.objectContaining({ duration: 160 }))
  } else {
    expect(animate).not.toHaveBeenCalled()
    expect(transition.skipTransition).toHaveBeenCalledOnce()
  }
  finish()
  await Promise.resolve()
  expect(document.documentElement.dataset.appearanceTransition).toBeUndefined()
})
