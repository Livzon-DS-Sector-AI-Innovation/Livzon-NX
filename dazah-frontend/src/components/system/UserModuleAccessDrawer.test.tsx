/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { UserPagePermissionsOut } from '@/actions/users'

const mocks = vi.hoisted(() => ({ get: vi.fn(), replace: vi.fn() }))
vi.mock('@/actions/users', () => ({
  getUserPagePermissions: mocks.get,
  replaceUserModulePermissions: mocks.replace,
}))
import UserModuleAccessDrawer from './UserModuleAccessDrawer'

const result = (id = 'user-1'): UserPagePermissionsOut => ({
  user_id: id, grant_version: 4, custom_page_keys: [], module_checks: {},
  definitions: [
    { page_key: 'production:overview', module_code: 'production', page_name: '生产管理概览', route_path: '/production', supported_scope_types: ['all'] },
    { page_key: 'quality:deviations:deviation-ledger', module_code: 'quality', page_name: '偏差台账', route_path: '/quality/deviations/ledger', supported_scope_types: ['all'] },
  ],
  grants: [
    { page_key: 'production:overview', module_code: 'production', permissions: ['access', 'query'],
      sensitive_actions: [], data_scope: { scope_type: 'all' }, source: 'role', source_role_names: ['生产查看员'] },
    { page_key: 'quality:deviations:deviation-ledger', module_code: 'quality', permissions: [],
      sensitive_actions: [], data_scope: { scope_type: 'all' }, source: 'none' },
  ],
})
let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  mocks.get.mockResolvedValue(result())
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})
async function show(id = 'user-1', isSystemAdmin = false, onClose = vi.fn()) {
  await act(async () => root.render(createElement(UserModuleAccessDrawer, {
    user: { id, name: id, isSystemAdmin }, open: true, onClose,
  })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find(
    (node) => node.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}
function moduleRow(name: string) {
  return [...document.querySelectorAll('.ant-table-tbody > tr')].find(
    (row) => row.textContent?.includes(name))!
}
it('shows read-only module access from effective pages and excludes denied pages', async () => {
  await show()
  expect(document.body.textContent).toContain('有效权限 · user-1')
  expect(document.body.textContent).toContain('已开通 1 个模块')
  expect(moduleRow('生产管理').textContent).toContain('自动开通')
  expect(moduleRow('质量管理').textContent).toContain('无可访问页面')
  expect(document.querySelector('input[type="checkbox"]')).toBeNull()
  expect([...document.querySelectorAll('button')].some((node) => node.textContent?.trim() === '保存')).toBe(false)
  await act(async () => moduleRow('生产管理').querySelector<HTMLButtonElement>('.ant-table-row-expand-icon')!.click())
  expect(moduleRow('生产管理概览').textContent).toContain('可查看')
  expect(moduleRow('生产管理概览').textContent).toContain('生产查看员')
  expect(mocks.replace).not.toHaveBeenCalled()
})
it('explains automatic opening, revocation and user overrides in the rules dialog', async () => {
  await show()
  await act(async () => button('了解访问规则').click())
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('撤销最后一个可访问页面后，入口自动关闭')
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('用户页面覆盖优先')
  expect(mocks.replace).not.toHaveBeenCalled()
})
it('refreshes revoked access and shows the no-page state', async () => {
  await show()
  mocks.get.mockResolvedValue({ ...result(), grants: [], grant_version: 5 })
  await act(async () => button('刷新').click())
  expect(document.body.textContent).toContain('已开通 0 个模块')
  expect(document.body.textContent).toContain('尚无可访问页面')
  expect(document.body.textContent).toContain('授权版本 5')
  expect(moduleRow('生产管理').textContent).toContain('无可访问页面')
})
it('shows user overrides as the permission source', async () => {
  const data = result()
  data.grants![0].source = 'user'
  mocks.get.mockResolvedValue(data)
  await show()
  await act(async () => moduleRow('生产管理').querySelector<HTMLButtonElement>('.ant-table-row-expand-icon')!.click())
  expect(moduleRow('生产管理概览').textContent).toContain('用户覆盖')
})
it('allows system administrators all navigation modules', async () => {
  mocks.get.mockResolvedValue({ ...result(), grants: [] })
  await show('user-1', true)
  expect(moduleRow('生产管理').textContent).toContain('自动开通')
  expect(moduleRow('质量管理').textContent).toContain('自动开通')
  expect(document.body.textContent).not.toContain('尚无可访问页面')
})
it('keeps failed loading distinct from no grants and supports retry', async () => {
  mocks.get.mockRejectedValueOnce(new Error('权限查询失败'))
  await show()
  expect(document.body.textContent).toContain('权限查询失败')
  expect(document.body.textContent).not.toContain('尚无可访问页面')
  await act(async () => button('重新加载').click())
  expect(document.body.textContent).toContain('已开通 1 个模块')
})
it('rejects a mismatched response', async () => {
  mocks.get.mockResolvedValue(result('other'))
  await show()
  expect(document.body.textContent).toContain('用户授权返回对象不一致')
  expect(document.querySelector('[aria-label="有效模块与页面权限"]')).toBeNull()
})
it('ignores an earlier user response after switching users', async () => {
  let resolve!: (value: UserPagePermissionsOut) => void
  mocks.get.mockImplementationOnce(() => new Promise<UserPagePermissionsOut>((done) => { resolve = done }))
  await show()
  mocks.get.mockResolvedValue({ ...result('user-2'), grants: [] })
  await show('user-2')
  await act(async () => resolve(result()))
  expect(document.body.textContent).toContain('有效权限 · user-2')
  expect(document.body.textContent).toContain('已开通 0 个模块')
})
it('searches modules and closes without writing or confirmation', async () => {
  const onClose = vi.fn()
  await show('user-1', false, onClose)
  const search = document.querySelector<HTMLInputElement>('[aria-label="搜索模块"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(search, '不存在')
    search.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(document.body.textContent).toContain('没有匹配的模块')
  await act(async () => button('关闭').click())
  expect(onClose).toHaveBeenCalledOnce()
  expect(mocks.replace).not.toHaveBeenCalled()
})
