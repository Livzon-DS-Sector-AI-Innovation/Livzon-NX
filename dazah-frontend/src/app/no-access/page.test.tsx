import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(), getFirstAuthorizedModulePath: vi.fn(), redirect: vi.fn(),
}))
vi.mock('@/actions/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('@/lib/menu-config', () => ({
  getFirstAuthorizedModulePath: mocks.getFirstAuthorizedModulePath,
  NO_AUTHORIZED_PAGE_PATH: '/no-access',
}))
vi.mock('next/navigation', () => ({ redirect: mocks.redirect }))
import NoAccessPage from './page'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.redirect.mockImplementation((path: string) => { throw new Error(`redirect:${path}`) })
})

it('sends signed-out visitors to login', async () => {
  mocks.getCurrentUser.mockResolvedValue(null)
  await expect(NoAccessPage()).rejects.toThrow('redirect:/login')
})

it('rechecks grants and sends authorized users to their first page', async () => {
  mocks.getCurrentUser.mockResolvedValue({ id: 'user-1' })
  mocks.getFirstAuthorizedModulePath.mockReturnValue('/quality/documents')
  await expect(NoAccessPage()).rejects.toThrow('redirect:/quality/documents')
})

it('explains how a signed-in user can recover from having no page access', async () => {
  mocks.getCurrentUser.mockResolvedValue({ id: 'user-1' })
  mocks.getFirstAuthorizedModulePath.mockReturnValue('/no-access')
  const html = renderToStaticMarkup(await NoAccessPage())
  expect(html).toContain('请联系管理员为你分配模块和页面权限')
  expect(html).toContain('重新检查权限')
  expect(html).toContain('/auth/logout')
})
