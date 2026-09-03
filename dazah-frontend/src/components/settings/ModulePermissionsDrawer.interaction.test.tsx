/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { UserManagementItem, UserPagePermissionsOut } from '@/actions/users'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), departments: vi.fn(), replace: vi.fn(), confirm: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/actions/users', () => ({ getUserPagePermissions: mocks.get,
  getPermissionDepartments: mocks.departments, replaceUserPagePermissions: mocks.replace }))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm } }) } }
})
import ModulePermissionsDrawer from './ModulePermissionsDrawer'

const user = (id: string): UserManagementItem => ({
  id, name: `用户${id}`, role: 'user', status: 'active', auth_source: 'local', grant_version: 3,
})
const result = (id: string): UserPagePermissionsOut => ({
  user_id: id, grant_version: 3, grants: [], custom_page_keys: [], module_rollouts: { hr: 'draft' },
  definitions: [{ page_key: 'hr:employee-management:profile', module_code: 'hr',
    page_name: `员工档案${id}`, route_path: '/hr/employee-management',
    supported_scope_types: ['department_tree', 'departments', 'all'] }],
})
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

it('auto-expands high risk pages without granting actions and preserves hidden scope', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.custom_page_keys = ['hr:employee-management:profile']
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'user',
    permissions: ['access'], sensitive_actions: [], data_scope: { scope_type: 'departments', department_ids: ['stable-dept'] } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  expect(document.body.textContent).toContain('删除员工档案')
  expect(document.body.textContent).not.toContain('数据范围')
  expect(mocks.departments).not.toHaveBeenCalled()
  expect(document.querySelector<HTMLInputElement>('input[value="delete"]')!.checked).toBe(false)
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ grants: [expect.objectContaining({
    data_scope: { scope_type: 'departments', department_ids: ['stable-dept'] }, sensitive_actions: [],
  })] }))
})
let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  mocks.departments.mockResolvedValue([])
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
async function show(id: string, open = true) {
  await act(async () => {
    root.render(createElement(ModulePermissionsDrawer, { user: user(id), open, onClose: vi.fn() }))
  })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find((node) => node.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}
async function preview() {
  await act(async () => button('只读').click())
  const input = document.querySelector<HTMLInputElement>('input[placeholder="填写授权调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '职责调整')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('预览并保存授权').click())
  expect(mocks.confirm).toHaveBeenCalled()
  return mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
}

it('rejects a confirmation from the previous user', async () => {
  mocks.get.mockImplementation(async (id: string) => result(id))
  await show('A')
  const confirmation = await preview()
  await show('B')
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('员工档案B')
})

it.each([true, false])('ignores a previous user save result (success=%s)', async (ok) => {
  mocks.get.mockImplementation(async (id: string) => result(id))
  const pending = deferred<{ ok: true; data: UserPagePermissionsOut } | { ok: false; message: string }>()
  mocks.replace.mockReturnValue(pending.promise)
  await show('A')
  const confirmation = await preview()
  let save: Promise<void> | void
  await act(async () => { save = confirmation.onOk() })
  expect(button('只读').disabled).toBe(true)
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写授权调整原因"]')!.disabled).toBe(true)
  await act(async () => { void confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledTimes(1)
  await show('B')
  await act(async () => {
    pending.resolve(ok ? { ok: true, data: result('A') } : { ok: false, message: '旧用户版本冲突' })
    await save
  })
  expect(document.body.textContent).toContain('员工档案B')
  expect(document.body.textContent).not.toContain('旧用户版本冲突')
  expect(button('预览并保存授权').disabled).toBe(false)
  expect(mocks.message.success).not.toHaveBeenCalled()
})

it('preserves edits on conflict and invalidates confirmation after closing', async () => {
  mocks.get.mockResolvedValue(result('A'))
  mocks.replace.mockResolvedValue({ ok: false, message: '授权版本冲突', status: 409 })
  await show('A')
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(document.body.textContent).toContain('本地修改已保留')
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写授权调整原因"]')!.value).toBe('职责调整')
  await show('A', false)
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledTimes(1)
})

it('does not reset edits when the parent passes a new object for the same user', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  await preview()
  await show('A')
  expect(mocks.get).toHaveBeenCalledTimes(1)
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写授权调整原因"]')!.value).toBe('职责调整')
})

it('ignores a late load from a previous user', async () => {
  const pending = deferred<UserPagePermissionsOut>()
  mocks.get.mockImplementation((id: string) => id === 'A' ? pending.promise : Promise.resolve(result(id)))
  await show('A')
  expect(button('预览并保存授权').disabled).toBe(true)
  await show('B')
  await act(async () => pending.resolve(result('A')))
  expect(document.body.textContent).toContain('员工档案B')
  expect(document.body.textContent).not.toContain('员工档案A')
})

it('accepts the current save and refreshes the authoritative version', async () => {
  mocks.get.mockResolvedValue(result('A'))
  mocks.replace.mockResolvedValue({ ok: true, data: { ...result('A'), grant_version: 4 } })
  await show('A')
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({
    expected_grant_version: 3, reason: '职责调整',
    grants: [expect.objectContaining({ mode: 'custom', permissions: ['access', 'query'] })],
  }))
  expect(document.body.textContent).toContain('授权版本 4')
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写授权调整原因"]')!.value).toBe('')
  expect(mocks.message.success).toHaveBeenCalledTimes(1)
})
