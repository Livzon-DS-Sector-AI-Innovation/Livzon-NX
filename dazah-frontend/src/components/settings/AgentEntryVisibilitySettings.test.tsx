/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { AntdProvider } from '../AntdProvider'
import { AgentEntryButton } from '../agent/AgentEntryButton'
import AgentEntryVisibilitySettings from './AgentEntryVisibilitySettings'
import { useAgentEntryPreferencesStore } from '@/stores/agent-entry-preferences'
import { useAgentStore } from '@/stores/agent'
import { setAppearance } from '@/lib/useAppearance'

it.each(['light', 'dark'] as const)('toggles the floating entry immediately in %s mode and preserves the conversation', async (mode) => {
  localStorage.clear()
  useAgentEntryPreferencesStore.setState({ visible: true, hydrated: false })
  useAgentStore.getState().setDraft('待发送的消息')
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => {
      setAppearance(mode)
      root.render(<AntdProvider><AgentEntryVisibilitySettings /><AgentEntryButton minimized /></AntdProvider>)
    })
    const toggle = host.querySelector<HTMLButtonElement>('[role="switch"][aria-label="Livzon助手悬浮按钮"]')!
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(host.querySelector('.agent-floating-entry-button')).not.toBeNull()
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    expect(host.querySelector('.agent-floating-entry-button')).toBeNull()
    expect(useAgentStore.getState().draft).toBe('待发送的消息')
    expect(localStorage.getItem('dazah.agent.floating-entry-visible')).toBe('false')
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(host.querySelector('.agent-floating-entry-button')).not.toBeNull()
    await act(async () => setAppearance(mode === 'light' ? 'dark' : 'light'))
    expect(toggle.getAttribute('aria-checked')).toBe('true')
    expect(host.querySelector('.agent-floating-entry-button')).not.toBeNull()
  } finally {
    await act(async () => root.unmount())
    host.remove()
    useAgentStore.getState().setDraft('')
    useAgentEntryPreferencesStore.setState({ visible: true, hydrated: false })
    localStorage.clear()
  }
})
