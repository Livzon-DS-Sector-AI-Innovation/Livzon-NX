/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { switchWorkspaceIdentity, WorkspaceIdentitySync } from './WorkspaceIdentitySync'
import { WORKSPACE_IDENTITY_TRANSITION_KEY, workspaceIdentityTransitionInitScript } from '@/lib/workspaceIdentityTransition'

const root = document.documentElement
const runInitScript = new Function('window', 'document', 'sessionStorage', workspaceIdentityTransitionInitScript)

function listenForViewTransition() {
  const listeners = new Map<string, (event: { viewTransition?: typeof transition }) => void>()
  const transition = { skipTransition: vi.fn(), finished: Promise.resolve() }
  runInitScript({
    matchMedia: window.matchMedia,
    addEventListener: (name: string, listener: () => void) => listeners.set(name, listener),
  }, document, sessionStorage)
  return {
    transition,
    swap: () => listeners.get('pageswap')?.({ viewTransition: transition }),
    reveal: (snapshot = true) => listeners.get('pagereveal')?.({ viewTransition: snapshot ? transition : undefined }),
  }
}

beforeEach(() => {
  document.body.innerHTML = '<main></main>'
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  vi.spyOn(window.location, 'replace').mockImplementation(() => {})
  const query = window.matchMedia('(min-width: 0px)')
  vi.spyOn(window, 'matchMedia').mockReturnValue({ ...query, matches: false })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  document.body.replaceChildren()
  delete root.dataset.workspaceIdentityTransition
  delete root.dataset.workspaceIdentityDeparting
  root.removeAttribute('style')
  sessionStorage.clear()
  localStorage.clear()
  window.history.replaceState({}, '', '/')
})

it('locks the old page and navigates directly with the opening animation armed', async () => {
  const transition = switchWorkspaceIdentity('opening', async () => '/')

  expect(document.querySelector('main')?.inert).toBe(true)
  await transition
  expect(root.dataset.workspaceIdentityDeparting).toBe('true')
  expect(root.dataset.workspaceIdentityTransition).toBeUndefined()
  expect(sessionStorage.getItem(WORKSPACE_IDENTITY_TRANSITION_KEY)).toBe(JSON.stringify({ arrival: 'opening' }))
  expect(window.location.replace).toHaveBeenCalledWith('/')

  const { swap, reveal, transition: snapshot } = listenForViewTransition()
  swap()
  expect(snapshot.skipTransition).not.toHaveBeenCalled()
  reveal()
  expect(root.dataset.workspaceIdentityTransition).toBe('opening')
  expect(sessionStorage.getItem(WORKSPACE_IDENTITY_TRANSITION_KEY)).toBeNull()
  await snapshot.finished
  expect(root.dataset.workspaceIdentityTransition).toBeUndefined()
})

it('unlocks the current page after a failed switch', async () => {
  const operation = vi.fn().mockRejectedValue(new Error('切换失败'))

  await expect(switchWorkspaceIdentity('restored', operation)).rejects.toThrow('切换失败')
  expect(document.querySelector('main')?.inert).toBe(false)
  expect(root.dataset.workspaceIdentityTransition).toBeUndefined()
  expect(sessionStorage.getItem(WORKSPACE_IDENTITY_TRANSITION_KEY)).toBeNull()
  expect(window.location.replace).not.toHaveBeenCalled()
})

it('reloads the workspace after another tab switches or a stale page returns from cache', async () => {
  const changeKey = 'dazah.workspace-identity-change'
  localStorage.setItem(changeKey, 'previous-identity')
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const container = document.createElement('div')
  document.body.append(container)
  const syncRoot = createRoot(container)
  try {
    await act(async () => syncRoot.render(<WorkspaceIdentitySync />))
    window.dispatchEvent(new StorageEvent('storage', { key: 'unrelated' }))
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }))
    expect(window.location.replace).not.toHaveBeenCalled()

    localStorage.setItem(changeKey, 'current-identity')
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: false }))
    expect(window.location.replace).not.toHaveBeenCalled()
    window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }))
    expect(window.location.replace).toHaveBeenCalledExactlyOnceWith('/')
    window.dispatchEvent(new StorageEvent('storage', { key: changeKey }))
    expect(vi.mocked(window.location.replace).mock.calls).toEqual([['/'], ['/']])
  } finally {
    await act(async () => syncRoot.unmount())
    container.remove()
    vi.unstubAllGlobals()
  }
  window.dispatchEvent(new StorageEvent('storage', { key: changeKey }))
  expect(window.location.replace).toHaveBeenCalledTimes(2)
})

it('navigates immediately when reduced motion is enabled', async () => {
  vi.mocked(window.matchMedia).mockReturnValue({ ...window.matchMedia(''), matches: true })

  await switchWorkspaceIdentity('restored', async () => '/settings')
  expect(root.dataset.workspaceIdentityTransition).toBeUndefined()
  expect(sessionStorage.getItem(WORKSPACE_IDENTITY_TRANSITION_KEY)).toBeNull()
  expect(window.location.replace).toHaveBeenCalledWith('/settings')
})

it('skips native transitions on unrelated document navigations', () => {
  const { swap, reveal, transition } = listenForViewTransition()
  swap()
  reveal()
  expect(transition.skipTransition).toHaveBeenCalledTimes(2)
  expect(root.dataset.workspaceIdentityTransition).toBeUndefined()
})

it('restores the measured banner origin on the next document', async () => {
  await switchWorkspaceIdentity('restored', async () => '/settings', { x: 0.625, y: 0.05 })

  const { reveal, transition } = listenForViewTransition()
  reveal()
  expect(root.dataset.workspaceIdentityTransition).toBe('restored')
  expect(root.style.getPropertyValue('--workspace-identity-origin-x')).toBe('62.5%')
  expect(root.style.getPropertyValue('--workspace-identity-origin-y')).toBe('5%')
  expect(sessionStorage.getItem(WORKSPACE_IDENTITY_TRANSITION_KEY)).toBeNull()
  await transition.finished
  expect(root.style.getPropertyValue('--workspace-identity-origin-x')).toBe('')
})

it('uses the default origin for an out-of-viewport stored anchor', () => {
  sessionStorage.setItem(WORKSPACE_IDENTITY_TRANSITION_KEY, JSON.stringify({
    arrival: 'restored',
    origin: { x: 0.5, y: 2 },
  }))
  listenForViewTransition().reveal()
  expect(root.dataset.workspaceIdentityTransition).toBe('restored')
  expect(root.style.getPropertyValue('--workspace-identity-origin-x')).toBe('')
  expect(root.style.getPropertyValue('--workspace-identity-origin-y')).toBe('')
})

it('opens normally and consumes the marker when the browser has no snapshot for the navigation', () => {
  sessionStorage.setItem(WORKSPACE_IDENTITY_TRANSITION_KEY, '{"arrival":"opening"}')
  listenForViewTransition().reveal(false)
  expect(root.dataset.workspaceIdentityTransition).toBeUndefined()
  expect(sessionStorage.getItem(WORKSPACE_IDENTITY_TRANSITION_KEY)).toBeNull()
})
