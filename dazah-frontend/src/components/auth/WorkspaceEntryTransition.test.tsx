/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { WorkspaceEntryTransition, useWorkspaceEntryTransition } from './WorkspaceEntryTransition'

const location = vi.hoisted(() => ({ pathname: '/login/complete' }))
vi.mock('next/navigation', () => ({ usePathname: () => location.pathname }))

function EntryButton() {
  const beginEntry = useWorkspaceEntryTransition()
  return <button onClick={() => beginEntry('/energy/entry?source=feishu', <section>原验证页面：身份验证成功</section>)}>进入</button>
}

describe('WorkspaceEntryTransition', () => {
  let host: HTMLDivElement
  let root: Root
  const render = () => root.render(<WorkspaceEntryTransition><EntryButton /><main>业务页面</main></WorkspaceEntryTransition>)

  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false } as MediaQueryList)
    location.pathname = '/login/complete'
    host = document.createElement('div')
    document.body.append(host)
    root = createRoot(host)
  })

  afterEach(() => {
    act(() => root.unmount())
    host.remove()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('leaves ordinary visits and subsequent navigation unobstructed', () => {
    act(render)
    expect(host.textContent).toContain('业务页面')
    expect(host.querySelector('[role="status"]')).toBeNull()
    expect(host.querySelector('[inert]')).toBeNull()
    location.pathname = '/energy/entry'
    act(render)
    expect(host.querySelector('[role="status"]')).toBeNull()
  })

  it('keeps the cover across a slow route change and reveals the committed page', async () => {
    act(render)
    act(() => host.querySelector('button')?.click())
    expect(host.querySelector('[data-phase="waiting"]')).not.toBeNull()
    expect(host.querySelector('[inert]')).not.toBeNull()
    expect(host.querySelector('[data-phase] section')?.textContent).toBe('原验证页面：身份验证成功')
    expect(host.querySelector('[role="status"]')?.textContent).toContain('身份验证成功')
    expect(host.textContent).not.toContain('正在打开工作台')
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(host.querySelector('[data-phase="waiting"]')).not.toBeNull()
    location.pathname = '/energy/entry'
    act(render)
    expect(host.querySelector('[data-phase="revealing"]')).not.toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(host.querySelector('[role="status"]')).toBeNull()
    expect(host.querySelector('[inert]')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(12_000) })
    expect(host.querySelector('a')).toBeNull()
  })

  it('offers a native recovery link without losing the destination query', async () => {
    act(render)
    act(() => host.querySelector('button')?.click())
    await act(async () => { await vi.advanceTimersByTimeAsync(12_000) })
    expect(host.textContent).toContain('工作台加载较慢')
    expect(host.querySelector('a')?.getAttribute('href')).toBe('/energy/entry?source=feishu')
    expect(host.querySelector('a')?.textContent).toBe('重新打开工作台')
    location.pathname = '/energy/entry'
    act(render)
    expect(host.querySelector('a')).toBeNull()
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(host.querySelector('[inert]')).toBeNull()
  })

  it('also releases the cover after an authentication redirect', async () => {
    act(render)
    act(() => host.querySelector('button')?.click())
    location.pathname = '/login'
    act(render)
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(host.querySelector('[role="status"]')).toBeNull()
  })

  it('cleans up pending timers on unmount', () => {
    act(render)
    act(() => host.querySelector('button')?.click())
    expect(vi.getTimerCount()).toBe(1)
    act(() => root.render(null))
    expect(vi.getTimerCount()).toBe(0)
  })

  it('releases the screen immediately when reduced motion is requested', async () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
    act(render)
    act(() => host.querySelector('button')?.click())
    location.pathname = '/energy/entry'
    act(render)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(host.querySelector('[data-phase]')).toBeNull()
    expect(host.querySelector('[inert]')).toBeNull()
  })
})
