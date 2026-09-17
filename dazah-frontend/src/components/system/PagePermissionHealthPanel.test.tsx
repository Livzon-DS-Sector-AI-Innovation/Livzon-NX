/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  health: vi.fn(), remediate: vi.fn(), roles: vi.fn(), departments: vi.fn(), users: vi.fn(),
  confirm: vi.fn(),
  message: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))
vi.mock('@/actions/admin', () => ({
  getPagePermissionHealth: mocks.health,
  remediatePagePermissionHealth: mocks.remediate,
}))
vi.mock('@/actions/users', () => ({
  getPermissionDepartments: mocks.departments,
  getUsers: mocks.users,
}))
vi.mock('@/lib/api/client/admin', () => ({ fetchRoles: mocks.roles }))
vi.mock('./RolePagePermissionsDrawer', () => ({
  RolePagePermissionsDrawer: ({ open }: { open: boolean }) =>
    open ? createElement('div', { 'data-testid': 'role-editor' }) : null,
}))
vi.mock('@/components/settings/ModulePermissionsDrawer', () => ({
  default: ({ open }: { open: boolean }) =>
    open ? createElement('div', { 'data-testid': 'user-editor' }) : null,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({
    message: mocks.message, modal: { confirm: mocks.confirm },
  }) } }
})
import { PagePermissionHealthPanel } from './PagePermissionHealthPanel'

let root: Root
let host: HTMLDivElement
const issues = [
  { code: 'invalid_department', detail: '部门已失效', grant_version: 3,
    module_code: 'hr', page_key: 'hr:profile', page_name: '员工管理',
    remediation: 'prune_departments', severity: 'error',
    target_id: 'role-1', target_name: '人事角色', target_type: 'role' },
  { code: 'redundant_user_override', detail: '与角色基线相同', grant_version: 4,
    module_code: 'quality', page_key: 'quality:documents', page_name: '文件管理',
    remediation: 'remove_grant', severity: 'warning',
    target_id: 'user-1', target_name: '张三', target_type: 'user' },
  { code: 'sensitive_without_expiry', detail: '高风险授权需要到期日', grant_version: 5,
    module_code: 'hr', page_key: 'hr:contracts', page_name: '合同管理',
    remediation: 'edit', severity: 'warning',
    target_id: 'role-1', target_name: '人事角色', target_type: 'role' },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  mocks.health.mockResolvedValue({
    checked_at: '2026-09-16T08:00:00Z', issue_count: 3,
    error_count: 1, warning_count: 2, issues,
  })
  mocks.roles.mockResolvedValue([{ id: 'role-1', name: '人事角色', code: 'hr', permissions: [] }])
  mocks.departments.mockResolvedValue([])
  mocks.users.mockResolvedValue({ items: [{ id: 'user-1', name: '张三' }] })
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function renderPanel() {
  await act(async () => root.render(createElement(PagePermissionHealthPanel)))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

function rowFor(label: string) {
  const row = [...document.querySelectorAll('tr')].find((item) => item.textContent?.includes(label))
  expect(row, label).toBeTruthy()
  return row!
}

it('shows health findings and opens the matching role or user editor', async () => {
  await renderPanel()
  expect(document.body.textContent).toContain('当前显示 3 条')
  expect(document.body.textContent).toContain('高风险权限无期限')

  await act(async () => {
    rowFor('部门已失效').querySelector<HTMLButtonElement>('button')!.click()
  })
  expect(mocks.roles).toHaveBeenCalled()
  expect(document.querySelector('[data-testid="role-editor"]')).toBeTruthy()

  await act(async () => {
    rowFor('与角色基线相同').querySelector<HTMLButtonElement>('button')!.click()
  })
  expect(mocks.users).toHaveBeenCalledWith({ status: 'active' })
  expect(document.querySelector('[data-testid="user-editor"]')).toBeTruthy()
})

it('previews automatic cleanup, then reloads after a successful repair', async () => {
  await renderPanel()
  const fix = [...rowFor('与角色基线相同').querySelectorAll('button')]
    .find((item) => item.textContent?.includes('修复'))!
  await act(async () => fix.click())
  expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({
    title: '自动修复此权限问题？', okText: '确认修复',
  }))
  mocks.remediate.mockResolvedValue({ ok: true, data: { message: '冗余覆盖已移除' } })
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())
  expect(mocks.remediate).toHaveBeenCalledWith(expect.objectContaining({
    code: 'redundant_user_override', target_type: 'user', target_id: 'user-1',
    page_key: 'quality:documents', expected_grant_version: 4,
  }))
  expect(mocks.message.success).toHaveBeenCalledWith('冗余覆盖已移除')
  expect(mocks.health).toHaveBeenCalledTimes(2)
})

it('warns and opens the editor when invalid departments need manual repair', async () => {
  await renderPanel()
  const fix = [...rowFor('部门已失效').querySelectorAll('button')]
    .find((item) => item.textContent?.includes('修复'))!
  await act(async () => fix.click())
  mocks.remediate.mockResolvedValue({ ok: false, message: '需重新选择授权部门' })
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())

  expect(mocks.message.warning).toHaveBeenCalledWith('需重新选择授权部门')
  expect(mocks.roles).toHaveBeenCalled()
  expect(document.querySelector('[data-testid="role-editor"]')).toBeTruthy()
  expect(mocks.health).toHaveBeenCalledTimes(1)
})
