/* @vitest-environment happy-dom */

import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useAgentEntryPreferencesStore as store } from './agent-entry-preferences'

const key = 'dazah.agent.floating-entry-visible'

beforeEach(() => {
  localStorage.clear()
  store.setState({ visible: true, hydrated: false })
})

afterEach(() => vi.restoreAllMocks())

it.each([null, 'true', 'invalid', 'false'])('restores the saved preference %s with a visible default', (saved) => {
  if (saved !== null) localStorage.setItem(key, saved)
  store.getState().restore()
  expect(store.getState().visible).toBe(saved !== 'false')
  expect(store.getState().hydrated).toBe(true)
})

it('persists both choices and restores hidden state after a page reload', () => {
  store.getState().setVisible(false)
  expect(localStorage.getItem(key)).toBe('false')
  store.setState({ visible: true, hydrated: false })
  store.getState().restore()
  expect(store.getState().visible).toBe(false)
  store.getState().setVisible(true)
  expect(localStorage.getItem(key)).toBe('true')
})

it('does not override a live selection when another consumer mounts', () => {
  store.getState().setVisible(false)
  localStorage.setItem(key, 'true')
  store.getState().restore()
  expect(store.getState().visible).toBe(false)
})

it('keeps the toggle usable when browser storage is unavailable', () => {
  vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => { throw new Error('blocked') })
  store.getState().restore()
  expect(store.getState().visible).toBe(true)
  store.getState().setVisible(false)
  expect(store.getState().visible).toBe(false)
  store.getState().setVisible(true)
  expect(store.getState().visible).toBe(true)
})
