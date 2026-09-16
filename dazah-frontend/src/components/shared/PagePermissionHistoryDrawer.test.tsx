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
