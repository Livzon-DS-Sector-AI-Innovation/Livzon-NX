/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AdminUserItem, RoleItem } from '@/lib/api/client/admin'

const mocks = vi.hoisted(() => ({
  fetchUsers: vi.fn(), fetchScopes: vi.fn(), assign: vi.fn(), deleteScope: vi.fn(),
  saveScope: vi.fn(), confirm: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/lib/api/client/admin', () => ({
  fetchAdminUsers: mocks.fetchUsers,
  fetchDataScopes: mocks.fetchScopes,
}))
vi.mock('@/actions/admin', () => ({
  assignUserRoles: mocks.assign,
  deleteDataScope: mocks.deleteScope,
  saveUserDataScope: mocks.saveScope,
}))
vi.mock('./UserModuleAccessDrawer', () => ({
  default: ({ open }: { open: boolean }) => open ? <div>模块访问抽屉</div> : null,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm } }) } }
})
import { UserRoleManager } from './UserRoleManager'

const roles: RoleItem[] = [
  { id: 'role-a', name: '物料QA', code: 'material_qa', is_system: false, permissions: [], description: '物料质量页面基线' },
  { id: 'role-b', name: '体系QA', code: 'system_qa', is_system: false, permissions: [], description: '体系质量页面基线' },
  { id: 'role-admin', name: '系统管理员', code: 'super_admin', is_system: true, permissions: [] },
  { id: 'role-ordinary-admin', name: '普通管理员', code: 'ordinary_admin', is_system: true, permissions: [] },
]
const user: AdminUserItem = {
  id: 'user-1', name: 'QA部公用账号', department: 'QA部', position: '公用账号',
  role: 'user', status: 'active', auth_source: 'local', grant_version: 7,
  module_codes: ['quality'], roles: [roles[0]],
}

let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  mocks.fetchUsers.mockResolvedValue({ items: [user], total: 1 })
  mocks.fetchScopes.mockResolvedValue([])
  mocks.assign.mockResolvedValue({ message: '角色分配已更新' })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function renderManager() {
  await act(async () => {
    root.render(createElement(UserRoleManager, { initialRoles: roles, initialDepartments: [] }))
    await Promise.resolve()
  })
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')]
    .find((item) => item.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}
function roleCheckbox(label: string) {
  const container = [...document.querySelectorAll('label')]
    .find((item) => item.textContent?.includes(label))
  expect(container, label).toBeTruthy()
  return container!.querySelector<HTMLInputElement>('input[type="checkbox"]')!
}

it('previews added roles and submits a versioned full replacement with a reason', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  expect(document.body.textContent).toContain('角色决定页面权限基线')
  expect(document.body.textContent).toContain('用户页面覆盖优先')
  await act(async () => roleCheckbox('体系QA').click())
  expect(document.body.textContent).toContain('新增 1')
  const reason = document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(reason, '增加体系文件维护职责')
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('预览并保存').click())
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())
  expect(mocks.assign).toHaveBeenCalledWith('user-1', ['role-a', 'role-b'], {
    expectedGrantVersion: 7,
    reason: '增加体系文件维护职责',
  })
})

it('keeps system administrator exclusive', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('系统管理员').click())
  expect(roleCheckbox('系统管理员').checked).toBe(true)
  expect(roleCheckbox('物料QA').checked).toBe(false)
  expect(document.body.textContent).toContain('已自动取消其他普通角色')
  expect([...document.querySelectorAll('button')].some((item) => item.textContent?.includes('查看页面权限'))).toBe(false)
})

it('keeps ordinary administrator exclusive and explains the settings limit', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('普通管理员').click())
  expect(roleCheckbox('普通管理员').checked).toBe(true)
  expect(roleCheckbox('物料QA').checked).toBe(false)
  expect(document.body.textContent).toContain('不能进入系统设置')
})
