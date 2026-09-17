/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { RolePagePermissionsOut } from '@/actions/admin'
import type { RoleItem } from '@/lib/api/client/admin'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), preview: vi.fn(), replace: vi.fn(), confirm: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/actions/admin', () => ({
  getRolePagePermissions: mocks.get, previewRolePagePermissions: mocks.preview,
  replaceRolePagePermissions: mocks.replace,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm } }) } }
})
import { RolePagePermissionsDrawer } from './RolePagePermissionsDrawer'

const role = (id: string): RoleItem => ({ id, name: `角色${id}`, code: id, is_system: false, permissions: [] })
const result = (id: string): RolePagePermissionsOut => ({
  role_id: id, grant_version: 3, grants: [],
  definitions: [{ page_key: 'hr:employee-management:profile', module_code: 'hr',
    page_name: `员工档案${id}`, route_path: '/hr/employee-management',
    supported_scope_types: ['department_tree', 'departments', 'all'] }],
})
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

it('shows high risk actions and editable data scope without changing it on save', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'role', permissions: ['access'],
    sensitive_actions: [], data_scope: { scope_type: 'departments', department_ids: ['stable-dept'] } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  expect(document.querySelector('details')).toBeNull()
  await act(async () => button('展开全部菜单').click())
  expect(document.body.textContent).toContain('删除员工档案')
  expect(document.body.textContent).toContain('数据范围')
  expect(document.body.textContent).toContain('指定部门及下级')
  expect(document.body.textContent).toContain('质量部')
  expect(document.querySelector<HTMLInputElement>('input[value="delete"]')!.checked).toBe(false)
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ grants: [expect.objectContaining({
    data_scope: { scope_type: 'departments', department_ids: ['stable-dept'] }, sensitive_actions: [],
  })] }))
})

it('presents high risk actions as add-ons to ordinary operation', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'role', permissions: ['access'],
    sensitive_actions: [], data_scope: { scope_type: 'department_tree', department_ids: [] } }]
  mocks.get.mockResolvedValue(data)
  await show('A')
  await act(async () => button('展开全部菜单').click())
  expect(document.body.textContent).toContain('附加高风险操作')
  expect(document.body.textContent).toContain('依赖普通操作')
  const action = document.querySelector<HTMLInputElement>('input[value="delete"]')!
  await act(async () => action.click())
  expect(document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="operate"]')!.checked).toBe(true)
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.click())
  expect(action.checked).toBe(false)
})
let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  mocks.preview.mockResolvedValue({ role_id: 'A', grant_version: 3, member_count: 2,
    affected_user_count: 1, expanded_user_count: 1, restricted_user_count: 0,
    mixed_user_count: 0, users_with_overrides: 1, affected_user_samples: [] })
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})
async function show(id: string) {
  await act(async () => {
    root.render(createElement(RolePagePermissionsDrawer, { role: role(id),
      departments: [{ id: 'dept-1', feishu_department_id: 'stable-dept', name: '质量部' }], open: true, onClose: vi.fn() }))
  })
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find((node) => node.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}
async function preview() {
  await act(async () => button('可查看').click())
  const batchConfirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
  await act(async () => { await batchConfirmation.onOk() })
  const input = document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '岗位调整')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('预览并保存基线').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(mocks.confirm).toHaveBeenCalled()
  return mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
}

it('disables saving during initial loading and ignores a previous role response', async () => {
  const first = deferred<RolePagePermissionsOut>()
  mocks.get.mockImplementation((id: string) => id === 'A' ? first.promise : Promise.resolve(result(id)))
  await show('A')
  expect(button('预览并保存基线').disabled).toBe(true)
  await show('B')
  await act(async () => first.resolve(result('A')))
  await act(async () => button('展开全部菜单').click())
  expect(document.body.textContent).toContain('员工档案B')
  expect(document.body.textContent).not.toContain('员工档案A')
})

it('does not submit a confirmation belonging to a previous role', async () => {
  mocks.get.mockImplementation(async (id: string) => result(id))
  await show('A')
  const confirmation = await preview()
  await show('B')
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('does not replace the new role state with a late save response', async () => {
  mocks.get.mockImplementation(async (id: string) => result(id))
  const pending = deferred<{ ok: true; data: RolePagePermissionsOut }>()
  mocks.replace.mockReturnValue(pending.promise)
  await show('A')
  const confirmation = await preview()
  expect(mocks.preview).toHaveBeenCalledWith('A', expect.objectContaining({
    expected_grant_version: 3, reason: '岗位调整',
  }))
  let save: Promise<void> | void
  await act(async () => { save = confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ expected_grant_version: 3, reason: '岗位调整' }))
  await show('B')
  await act(async () => { pending.resolve({ ok: true, data: result('A') }); await save })
  await act(async () => button('展开全部菜单').click())
  expect(document.body.textContent).toContain('员工档案B')
  expect(button('预览并保存基线').disabled).toBe(false)
  expect(mocks.message.success).not.toHaveBeenCalled()
})

it('keeps local edits and the reason after a version conflict', async () => {
  mocks.get.mockResolvedValue(result('A'))
  mocks.replace.mockResolvedValue({ ok: false, message: '授权版本冲突', status: 409 })
  await show('A')
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(document.body.textContent).toContain('本地修改已保留')
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!.value).toBe('岗位调整')
  expect(mocks.get).toHaveBeenCalledTimes(1)
})

it('rejects a mismatched load response instead of showing another role grants', async () => {
  mocks.get.mockResolvedValue(result('B'))
  await show('A')
  expect(document.body.textContent).toContain('角色授权返回对象不一致')
  expect(document.body.textContent).not.toContain('员工档案B')
  expect(button('预览并保存基线').disabled).toBe(true)
})

it('saves the current role once and clears the successful adjustment', async () => {
  mocks.get.mockResolvedValue(result('A'))
  const pending = deferred<{ ok: true; data: RolePagePermissionsOut }>()
  mocks.replace.mockReturnValue(pending.promise)
  await show('A')
  const confirmation = await preview()
  let save: Promise<void> | void
  await act(async () => { save = confirmation.onOk(); void confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledTimes(1)
  expect(button('可查看').disabled).toBe(true)
  await act(async () => { pending.resolve({ ok: true, data: { ...result('A'), grant_version: 4 } }); await save })
  expect(button('可查看').disabled).toBe(false)
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!.value).toBe('')
  expect(mocks.message.success).toHaveBeenCalledTimes(1)
})

it('recursively selects collapsed descendants and shows partial selection', async () => {
  const data = result('A')
  data.definitions!.push({ ...data.definitions![0], page_key: 'hr:employee-management:other', page_name: '其他档案' })
  mocks.get.mockResolvedValue(data)
  await show('A')
  const tier = (label: string) => {
    const [pageName, permission] = label.split('：')
    const values: Record<string, string> = { 访问: 'access', 查询: 'query', 操作: 'operate', 无权限: 'none' }
    return document.querySelector<HTMLInputElement>(`[data-page-name="${pageName}"] input[value="${values[permission]}"]`)!
  }
  await act(async () => tier('员工管理：查询').click())
  await act(async () => button('展开全部菜单').click())
  expect(tier('员工档案A：查询').checked).toBe(true)
  expect(tier('其他档案：查询').checked).toBe(true)
  await act(async () => tier('其他档案：访问').click())
  expect(tier('员工管理：查询').checked).toBe(false)
  expect(document.body.textContent).toContain('混合档位')
  await act(async () => button('折叠全部菜单').click())
  expect(tier('其他档案：查询')).toBeNull()
  await act(async () => tier('员工管理：无权限').click())
  await act(async () => button('展开全部菜单').click())
  expect(tier('员工档案A：无权限').checked).toBe(true)
  expect(tier('其他档案：无权限').checked).toBe(true)
})

it('keeps existing high risk actions when a batch remains at operable', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'role',
    permissions: ['access', 'query', 'operate'], sensitive_actions: ['delete'],
    data_scope: { scope_type: 'department_tree', department_ids: [] } }]
  mocks.get.mockResolvedValue(data)
  await show('A')
  await act(async () => button('普通操作').click())
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
  await act(async () => { await confirmation.onOk() })
  await act(async () => button('展开全部菜单').click())
  expect(document.querySelector<HTMLInputElement>('input[value="delete"]')!.checked).toBe(true)
})
