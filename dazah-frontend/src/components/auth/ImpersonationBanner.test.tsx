/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import { ImpersonationBanner } from './ImpersonationBanner'

const mocks = vi.hoisted(() => ({
  exit: vi.fn().mockResolvedValue(true),
  switchIdentity: vi.fn(async (_arrival: string, resolve: () => Promise<string>) => resolve()),
}))
vi.mock('@/lib/api/client/impersonation', () => ({ exitImpersonation: mocks.exit }))
vi.mock('./WorkspaceIdentitySync', () => ({ switchWorkspaceIdentity: mocks.switchIdentity }))

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

it('highlights the target identity and keeps the restore action available', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ImpersonationBanner name="验收用户" />))
    const notice = host.querySelector('[data-platform-notice="warning"]')
    expect(notice?.querySelector('strong')?.textContent).toBe('验收用户')
    const restore = notice?.querySelector('button')
    expect(restore?.textContent).toBe('返回管理员身份')
    await act(async () => restore?.click())
    expect(mocks.exit).toHaveBeenCalledOnce()
    expect(mocks.switchIdentity).toHaveBeenCalledWith('restored', expect.any(Function), undefined)
    await expect(mocks.switchIdentity.mock.results[0].value).resolves.toBe('/settings?tab=permissions&view=impersonation')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})

it.each([
  ['暂时无法恢复', '暂时无法恢复'],
  ['TypeError: internal restore failure', '暂时无法退出模拟'],
])('announces a safe restore error for %s', async (error, expected) => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  mocks.exit.mockRejectedValueOnce(new Error(error))
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ImpersonationBanner />))
    const status = host.querySelector('[aria-live="assertive"]')
    expect(status?.textContent).toBe('')
    await act(async () => host.querySelector('button')?.click())
    expect(status?.textContent).toBe(expected)
    expect(host.querySelector('button')?.disabled).toBe(false)
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
