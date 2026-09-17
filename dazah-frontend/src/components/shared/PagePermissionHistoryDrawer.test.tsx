/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getRole: vi.fn(), previewRole: vi.fn(), rollbackRole: vi.fn(), exportRole: vi.fn(),
  getUser: vi.fn(), previewUser: vi.fn(), rollbackUser: vi.fn(), exportUser: vi.fn(),
  confirm: vi.fn(), info: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))
vi.mock('@/actions/admin', () => ({
  getRolePagePermissionHistory: mocks.getRole,
  previewRolePagePermissionRollback: mocks.previewRole,
  rollbackRolePagePermissions: mocks.rollbackRole,
  exportRolePagePermissionHistory: mocks.exportRole,
}))
vi.mock('@/actions/users', () => ({
  getUserPagePermissionHistory: mocks.getUser,
  previewUserPagePermissionRollback: mocks.previewUser,
  rollbackUserPagePermissions: mocks.rollbackUser,
  exportUserPagePermissionHistory: mocks.exportUser,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({
    message: mocks.message, modal: { confirm: mocks.confirm, info: mocks.info },
  }) } }
})
import { PagePermissionHistoryDrawer } from './PagePermissionHistoryDrawer'

let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  const item = {
    id: 'audit-1', actor_user_id: 'actor-1', actor_name: '授权管理员',
    action: 'replace_role_page_permissions', source: 'manual', reason: '岗位调整',
    grant_version: 4, old_grants: [], grants: [{ page_key: 'hr:recruitment' }],
    changes: [{ page_key: 'hr:recruitment', page_name: '招聘管理', kind: 'grant',
      summary: '新增页面授权', before: null, after: { page_key: 'hr:recruitment' } }],
    created_at: '2026-09-16T08:00:00Z', rollback_of: null,
  }
  mocks.getRole.mockResolvedValue({
    items: [item], total: 1, page: 1, page_size: 20,
    actor_options: [{ user_id: 'actor-1', user_name: '授权管理员' }],
    is_truncated: false,
  })
  mocks.previewRole.mockResolvedValue({
    target_type: 'role', target_id: 'role-1', current_grant_version: 5,
    history_grant_version: 4, changes: [], affected_user_count: 2,
    expanded_user_count: 0, restricted_user_count: 2, mixed_user_count: 0,
    users_with_overrides: 1, affected_user_samples: [],
  })
  mocks.rollbackRole.mockResolvedValue({ ok: true, data: { grant_version: 6 } })
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

function button(label: string) {
  const found = [...document.querySelectorAll('button')]
    .find((item) => item.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}

it('shows auditable history and previews impact before a versioned rollback', async () => {
  await act(async () => {
    root.render(createElement(PagePermissionHistoryDrawer, {
      targetType: 'role', targetId: 'role-1', targetName: '质量角色', grantVersion: 5,
      open: true, onClose: vi.fn(), onRolledBack: vi.fn(),
    }))
  })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
  expect(document.body.textContent).toContain('授权管理员')
  expect(document.body.textContent).toContain('手工调整')
  expect(document.body.textContent).toContain('招聘管理')

  await act(async () => button('恢复').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请填写回滚原因')
  const reason = document.querySelector<HTMLInputElement>('input[placeholder="填写回滚原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(reason, '恢复历史配置')
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => {
    button('恢复').click()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(mocks.previewRole).toHaveBeenCalledWith('role-1', {
    audit_id: 'audit-1', expected_grant_version: 5,
  })
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => { await confirmation.onOk() })
  expect(mocks.rollbackRole).toHaveBeenCalledWith('role-1', expect.objectContaining({
    audit_id: 'audit-1', expected_grant_version: 5, reason: '恢复历史配置',
    idempotency_key: expect.any(String),
  }))
})

it('filters user history, shows the snapshot, and uses the user rollback action', async () => {
  const item = {
    id: 'audit-user-1', actor_user_id: null, actor_name: null,
    action: 'replace_user_page_permissions', source: 'rollback', reason: null,
    grant_version: 2, rollback_of: 'audit-older', created_at: '2026-09-16T08:00:00Z',
    grants: [{ page_key: 'quality:documents', permissions: ['access'],
      sensitive_actions: [], scope_type: 'all', department_ids: [] }],
    changes: [],
  }
  mocks.getUser.mockResolvedValue({
    items: [item], total: 1, page: 1, page_size: 20,
    actor_options: [], is_truncated: true,
  })
  mocks.previewUser.mockResolvedValue({
    target_type: 'user', target_id: 'user-1', current_grant_version: 3,
    history_grant_version: 2, changes: [], affected_user_count: 0,
    expanded_user_count: 0, restricted_user_count: 0, mixed_user_count: 0,
    users_with_overrides: 0, affected_user_samples: [],
  })
  mocks.rollbackUser.mockResolvedValue({ ok: true, data: { grant_version: 4 } })
  const close = vi.fn()
  const rolledBack = vi.fn()
  await act(async () => root.render(createElement(PagePermissionHistoryDrawer, {
    targetType: 'user', targetId: 'user-1', targetName: '张三', grantVersion: 3,
    open: true, onClose: close, onRolledBack: rolledBack,
  })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
  expect(document.body.textContent).toContain('当前精细筛选仅扫描最近 5000 条历史')
  expect(document.body.textContent).toContain('历史回滚')
  expect(document.body.textContent).toContain('系统')

  const pageKey = document.querySelector<HTMLInputElement>('input[placeholder="页面键"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(pageKey, 'quality:documents')
    pageKey.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('查询').click())
  expect(mocks.getUser).toHaveBeenLastCalledWith('user-1', expect.objectContaining({
    page_key: 'quality:documents', page: 1,
  }))
  await act(async () => button('重置').click())
  expect(mocks.getUser).toHaveBeenLastCalledWith('user-1', expect.objectContaining({
    page_key: undefined, source: undefined,
  }))

  await act(async () => button('查看快照').click())
  expect(mocks.info).toHaveBeenCalledWith(expect.objectContaining({
    title: 'v2 完整快照',
  }))
  const reason = document.querySelector<HTMLInputElement>('input[placeholder="填写回滚原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(reason, '恢复用户授权')
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => {
    button('恢复').click()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  expect(mocks.previewUser).toHaveBeenCalledWith('user-1', {
    audit_id: 'audit-user-1', expected_grant_version: 3,
  })
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())
  expect(mocks.rollbackUser).toHaveBeenCalledWith('user-1', expect.objectContaining({
    audit_id: 'audit-user-1', reason: '恢复用户授权',
  }))
  expect(rolledBack).toHaveBeenCalled()
  expect(close).toHaveBeenCalled()
})

it('exports the complete role history as a CSV download', async () => {
  const createObjectURL = vi.fn(() => 'blob:permission-history')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  mocks.exportRole.mockResolvedValue({ filename: 'role-history.csv', content: '版本,页面\n4,招聘管理' })

  await act(async () => root.render(createElement(PagePermissionHistoryDrawer, {
    targetType: 'role', targetId: 'role-1', targetName: '质量角色', grantVersion: 5,
    open: true, onClose: vi.fn(), onRolledBack: vi.fn(),
  })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
  await act(async () => button('导出历史（最多5000条）').click())

  expect(mocks.exportRole).toHaveBeenCalledWith('role-1')
  expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
  expect(click).toHaveBeenCalledOnce()
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:permission-history')
  expect(mocks.message.success).toHaveBeenCalledWith('授权历史已导出')
  click.mockRestore()
})
