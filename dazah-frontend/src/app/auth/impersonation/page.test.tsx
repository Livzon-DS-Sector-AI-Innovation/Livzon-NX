import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, expect, it, vi } from 'vitest'
import ImpersonationRecoveryPage from './page'

const mocks = vi.hoisted(() => ({
  getCookie: vi.fn(),
  getCurrentUser: vi.fn(),
  redirect: vi.fn((path: string) => { throw new Error(`redirect:${path}`) }),
}))

vi.mock('next/headers', () => ({ cookies: async () => ({ get: mocks.getCookie }) }))
vi.mock('next/navigation', () => ({ redirect: mocks.redirect }))
vi.mock('@/actions/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))

const settingsRecovery = { searchParams: Promise.resolve({ reason: 'system-settings' }) }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getCookie.mockReturnValue({ value: 'simulation-fixture' })
  mocks.getCurrentUser.mockResolvedValue(null)
})

it('shows both recovery actions for an active simulated user', async () => {
  mocks.getCurrentUser.mockResolvedValue({
    name: '采购验收用户',
    impersonation: { expires_at: '2026-12-01T00:00:00Z' },
  })
  const html = renderToStaticMarkup(await ImpersonationRecoveryPage(settingsRecovery))
  expect(html).toContain('当前模拟用户无法访问系统设置。')
  expect(html).toContain('采购验收用户')
  expect(html).toMatch(/<a [^>]*href="\/"[^>]*><span>继续模拟<\/span>/)
  expect(html).toContain('返回管理员身份')
})

it('offers only exit when the simulation cannot be verified', async () => {
  const html = renderToStaticMarkup(await ImpersonationRecoveryPage(settingsRecovery))
  expect(html).toContain('模拟登录暂不可用或已结束')
  expect(html).toContain('返回管理员身份')
  expect(html).not.toContain('继续模拟')
})

it('returns to the platform when the simulation cookie is absent', async () => {
  mocks.getCookie.mockReturnValue(undefined)
  await expect(ImpersonationRecoveryPage(settingsRecovery)).rejects.toThrow('redirect:/')
  expect(mocks.getCurrentUser).not.toHaveBeenCalled()
})
