/* @vitest-environment happy-dom */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import { AntdProvider } from '../AntdProvider'
import { AgentFloatingAssistant } from './AgentFloatingAssistant'
import { useAuthStore } from '@/stores/auth'
import { useAgentStore } from '@/stores/agent'
import { setAppearance } from '@/lib/useAppearance'

it.each(['light', 'dark'] as const)('keeps %s suggestions and composer on matching theme surfaces', async (mode) => {
  const stylesheet = document.createElement('style')
  stylesheet.textContent = readFileSync(resolve('src/app/globals.css'), 'utf8')
    .replace(/^@import.*$/gm, '')
  document.head.append(stylesheet)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const previousUser = useAuthStore.getState().user
  useAuthStore.getState().setUser({ id: 'appearance-test', name: '测试用户', role: 'admin' })
  useAgentStore.getState().startNewConversation()
  useAgentStore.getState().setOpen(true)
  try {
    await act(async () => root.render(<AntdProvider><AgentFloatingAssistant /></AntdProvider>))
    await act(async () => setAppearance(mode))
    const suggestion = host.querySelector<HTMLElement>('.agent-suggestion')
    const title = host.querySelector<HTMLElement>('.agent-suggestion-text')
    const composer = host.querySelector<HTMLElement>('.agent-composer')
    const footer = host.querySelector<HTMLElement>('.agent-composer-footer')
    expect(suggestion).toBeTruthy()
    expect(composer).toBeTruthy()
    const canvas = mode === 'dark' ? '#222225' : '#ffffff'
    const ink = mode === 'dark' ? '#eeedf1' : '#1a1a1a'
    expect(getComputedStyle(suggestion!).backgroundColor).toBe(canvas)
    expect(getComputedStyle(footer!).backgroundColor).toBe(canvas)
    expect(getComputedStyle(title!).color).toBe(ink)
    expect(getComputedStyle(composer!).backgroundColor).toBe(mode === 'dark' ? '#2b2b30' : '#fafaf9')
  } finally {
    await act(async () => root.unmount())
    useAgentStore.getState().setOpen(false)
    useAuthStore.getState().setUser(previousUser)
    stylesheet.remove()
    host.remove()
    window.localStorage.clear()
  }
})
