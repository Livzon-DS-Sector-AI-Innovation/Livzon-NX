'use client'

import { useEffect } from 'react'
import {
  WORKSPACE_IDENTITY_TRANSITION_KEY,
  type WorkspaceIdentityArrival,
  type WorkspaceIdentityOrigin,
} from '@/lib/workspaceIdentityTransition'

const CHANGE_KEY = 'dazah.workspace-identity-change'

export async function switchWorkspaceIdentity(
  arrival: WorkspaceIdentityArrival,
  resolveDestination: () => Promise<string>,
  origin?: WorkspaceIdentityOrigin,
) {
  const blocked = Array.from(document.body.children).filter(
    (element): element is HTMLElement => element instanceof HTMLElement && !element.inert,
  )
  const previousFocus = document.activeElement
  blocked.forEach(element => { element.inert = true })

  let destination: string
  try {
    destination = await resolveDestination()
  } catch (failure) {
    blocked.forEach(element => { element.inert = false })
    if (previousFocus instanceof HTMLElement) {
      window.requestAnimationFrame(() => previousFocus.focus({ preventScroll: true }))
    }
    throw failure
  }

  try {
    localStorage.setItem(CHANGE_KEY, `${Date.now()}-${Math.random()}`)
  } catch {
    // The initiating tab can still switch when cross-tab storage is unavailable.
  }

  if (document.visibilityState === 'visible' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    try {
      sessionStorage.setItem(WORKSPACE_IDENTITY_TRANSITION_KEY, JSON.stringify({ arrival, origin }))
      document.documentElement.dataset.workspaceIdentityDeparting = 'true'
    } catch {
      // The destination can render normally when storage is unavailable.
    }
  }
  window.location.replace(destination)
}

export function WorkspaceIdentitySync() {
  useEffect(() => {
    function readIdentityChange() {
      try {
        return localStorage.getItem(CHANGE_KEY)
      } catch {
        return null
      }
    }
    const initialChange = readIdentityChange()
    function onStorage(event: StorageEvent) {
      if (event.key === CHANGE_KEY) window.location.replace('/')
    }
    function onPageShow(event: PageTransitionEvent) {
      if (event.persisted && initialChange !== readIdentityChange()) window.location.replace('/')
    }
    window.addEventListener('storage', onStorage)
    window.addEventListener('pageshow', onPageShow)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener('pageshow', onPageShow)
    }
  }, [])
  return null
}
