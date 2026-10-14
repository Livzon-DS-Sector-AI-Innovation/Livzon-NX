/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AntdProvider } from '../AntdProvider'
import { AppearanceMenu } from './AppearanceMenu'
import { APPEARANCE_STORAGE_KEY, appearanceInitScript } from '@/lib/appearance'

let root: Root
let media: MediaQueryList
let changes: Set<EventListenerOrEventListenerObject>
beforeEach(() => {
  window.localStorage.clear()
  changes = new Set()
  media = {
    matches: false, media: '(prefers-color-scheme: dark)', onchange: null,
    addEventListener: vi.fn((_type, listener) => changes.add(listener)),
    removeEventListener: vi.fn((_type, listener) => changes.delete(listener)),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  } as MediaQueryList
  vi.spyOn(window, 'matchMedia').mockReturnValue(media)
  const host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  expect(changes.size).toBe(0)
  vi.restoreAllMocks()
  Reflect.deleteProperty(document.documentElement, 'animate')
  Reflect.deleteProperty(document, 'startViewTransition')
  document.body.replaceChildren()
  delete document.documentElement.dataset.theme
  delete document.documentElement.dataset.appearance
})
async function render() {
  await act(async () => root.render(<AntdProvider><AppearanceMenu /></AntdProvider>))
}
async function choose(value: string) {
  const input = document.querySelector<HTMLInputElement>(`input[value="${value}"]`)
  expect(input).not.toBeNull()
  await act(async () => input?.click())
}
async function systemDark(dark: boolean) {
  Object.defineProperty(media, 'matches', { value: dark, configurable: true })
  await act(async () => changes.forEach((listener) => {
    if (typeof listener === 'function') listener(new Event('change'))
    else listener.handleEvent(new Event('change'))
  }))
}

it('defaults to system and immediately responds to system changes', async () => {
  await render()
  expect(document.documentElement.dataset.appearance).toBe('system')
  expect(document.documentElement.dataset.theme).toBe('light')
  await systemDark(true)
  expect(document.documentElement.dataset.theme).toBe('dark')
  await systemDark(false)
  expect(document.documentElement.dataset.theme).toBe('light')
})

it('shows three direct choices with the system mode selected, without opening a popup', async () => {
  await render()
  const radio = document.querySelector<HTMLInputElement>('input[value="system"]')
  expect(radio?.checked).toBe(true)
  expect([...document.querySelectorAll<HTMLInputElement>('input[type="radio"]')].map((input) => input.getAttribute('aria-label')))
    .toEqual(['浅色', '深色', '跟随系统'])
  expect(document.querySelector('.ant-popover')).toBeNull()
  radio?.focus()
  expect(document.activeElement).toBe(radio)
  await choose('dark')
  expect(document.querySelector<HTMLInputElement>('input[value="dark"]')?.checked).toBe(true)
  expect(document.querySelector<HTMLInputElement>('input[value="system"]')?.checked).toBe(false)
})

it('animates a button selection after the new theme is committed', async () => {
  Object.defineProperty(document.documentElement, 'animate', { value: vi.fn(), configurable: true })
  Object.defineProperty(document, 'startViewTransition', { value: vi.fn(), configurable: true })
  // The menu only needs the cancellation API from this happy-dom animation double.
  const animation: Pick<Animation, 'cancel'> = { cancel: vi.fn() }
  const animate = vi.spyOn(document.documentElement, 'animate').mockReturnValue(animation as Animation)
  let finish = () => {}
  const finished = new Promise<void>((resolve) => { finish = resolve })
  const start = vi.spyOn(document, 'startViewTransition').mockImplementation((callback) => {
    if (typeof callback === 'function') void callback()
    return { ready: Promise.resolve(), finished, updateCallbackDone: Promise.resolve(), skipTransition: vi.fn(), types: new Set<string>() }
  })
  await render()
  await choose('dark')
  expect(start).toHaveBeenCalledOnce()
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe('dark')
  expect(animate).toHaveBeenCalledOnce()
  finish()
  await act(async () => { await finished })
  await choose('system')
  expect(start).toHaveBeenCalledTimes(2)
  finish()
  await act(async () => { await finished })
})

it('uses the system when reading browser storage is blocked', async () => {
  const original = window.localStorage.getItem
  window.localStorage.getItem = () => { throw new Error('blocked') }
  try {
    Object.defineProperty(media, 'matches', { value: true, configurable: true })
    new Function('window', 'document', 'localStorage', appearanceInitScript)(window, document, window.localStorage)
    expect(document.documentElement.dataset.theme).toBe('dark')
    await render()
    expect(document.documentElement.dataset.theme).toBe('dark')
  } finally {
    window.localStorage.getItem = original
  }
})

it('selects and remembers all three modes, keeping manual mode independent of the system', async () => {
  await render()
  await choose('dark')
  expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  await systemDark(false)
  expect(document.documentElement.dataset.theme).toBe('dark')
  await choose('light')
  await systemDark(true)
  expect(document.documentElement.dataset.theme).toBe('light')
  expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe('light')
  await choose('system')
  expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe('system')
  expect(document.documentElement.dataset.theme).toBe('dark')
})

it('restores a saved preference and synchronizes changes from another tab', async () => {
  window.localStorage.setItem(APPEARANCE_STORAGE_KEY, 'dark')
  await render()
  expect(document.documentElement.dataset.theme).toBe('dark')
  await act(async () => window.dispatchEvent(new StorageEvent('storage', { key: APPEARANCE_STORAGE_KEY, newValue: 'light' })))
  expect(document.documentElement.dataset.theme).toBe('light')
  await act(async () => window.dispatchEvent(new StorageEvent('storage', { key: APPEARANCE_STORAGE_KEY, newValue: 'invalid' })))
  expect(document.documentElement.dataset.appearance).toBe('system')
})

it('falls back for invalid preferences and still switches when storage is blocked', async () => {
  window.localStorage.setItem(APPEARANCE_STORAGE_KEY, 'invalid')
  await render()
  expect(document.documentElement.dataset.appearance).toBe('system')
  const original = window.localStorage.setItem
  window.localStorage.setItem = () => { throw new Error('blocked') }
  try {
    await choose('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  } finally {
    window.localStorage.setItem = original
  }
})

it.each(['light', 'dark', 'system', 'invalid'])('applies %s before hydration without overwriting storage', (saved) => {
  window.localStorage.setItem(APPEARANCE_STORAGE_KEY, saved)
  Object.defineProperty(media, 'matches', { value: true, configurable: true })
  new Function('window', 'document', 'localStorage', appearanceInitScript)(window, document, window.localStorage)
  expect(document.documentElement.dataset.theme).toBe(saved === 'light' ? 'light' : 'dark')
  expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe(saved)
})
