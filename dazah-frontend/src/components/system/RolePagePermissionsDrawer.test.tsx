/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { RolePagePermissionsOut } from '@/actions/admin'
import type { RoleItem } from '@/lib/api/client/admin'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), replace: vi.fn(), confirm: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/actions/admin', () => ({
  getRolePagePermissions: mocks.get, replaceRolePagePermissions: mocks.replace,
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

it('opens high risk actions automatically and retains hidden scope on save', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'role', permissions: ['access'],
    sensitive_actions: [], data_scope: { scope_type: 'departments', department_ids: ['stable-dept'] } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  expect(document.body.textContent).toContain('删除员工档案')
  expect(document.body.textContent).not.toContain('数据范围')
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
    root.render(createElement(RolePagePermissionsDrawer, { role: role(id), departments: [], open: true, onClose: vi.fn() }))
  })
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find((node) => node.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}
async function preview() {
  await act(async () => button('只读').click())
  const input = document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '岗位调整')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('预览并保存基线').click())
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
  let save: Promise<void> | void
  await act(async () => { save = confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ expected_grant_version: 3, reason: '岗位调整' }))
  await show('B')
  await act(async () => { pending.resolve({ ok: true, data: result('A') }); await save })
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
  expect(button('只读').disabled).toBe(true)
  await act(async () => { pending.resolve({ ok: true, data: { ...result('A'), grant_version: 4 } }); await save })
  expect(button('只读').disabled).toBe(false)
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!.value).toBe('')
  expect(mocks.message.success).toHaveBeenCalledTimes(1)
})
