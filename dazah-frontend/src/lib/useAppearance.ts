'use client'

import { useSyncExternalStore } from 'react'
import { APPEARANCE_STORAGE_KEY, DARK_MODE_QUERY, parseAppearance, resolveAppearance, type AppearanceMode } from './appearance'

let mode: AppearanceMode = 'system'
let snapshot = 'system:light'
let media: MediaQueryList | undefined
const listeners = new Set<() => void>()

function publish() {
  const resolved = resolveAppearance(mode, media?.matches ?? false)
  snapshot = `${mode}:${resolved}`
  document.documentElement.dataset.appearance = mode
  document.documentElement.dataset.theme = resolved
  listeners.forEach((notify) => notify())
}

function storageChanged(event: StorageEvent) {
  if (event.key !== APPEARANCE_STORAGE_KEY && event.key !== null) return
  mode = parseAppearance(event.newValue)
  publish()
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  if (listeners.size === 1) {
    try { mode = parseAppearance(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)) } catch { /* Keep the in-memory choice if storage is unavailable. */ }
    media = window.matchMedia(DARK_MODE_QUERY)
    media.addEventListener('change', publish)
    window.addEventListener('storage', storageChanged)
    publish()
  }
  return () => {
    listeners.delete(notify)
    if (listeners.size === 0) {
      media?.removeEventListener('change', publish)
      window.removeEventListener('storage', storageChanged)
      media = undefined
    }
  }
}

export function setAppearance(next: AppearanceMode) {
  mode = next
  try { window.localStorage.setItem(APPEARANCE_STORAGE_KEY, next) } catch { /* Switching still works for this session. */ }
  publish()
}

const getSnapshot = () => snapshot
const getServerSnapshot = () => 'system:light'

export function useAppearance() {
  const state = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  return {
    mode: parseAppearance(state.split(':')[0]),
    resolved: state.endsWith(':dark') ? 'dark' as const : 'light' as const,
    setAppearance,
  }
}
