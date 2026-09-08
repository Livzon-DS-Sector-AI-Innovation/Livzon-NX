/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ list: vi.fn(), apply: vi.fn(), confirm: vi.fn(), close: vi.fn() }))
vi.mock('@/actions/admin', () => ({ applyDeptRolesToUser: mocks.apply, createDeptRule: vi.fn(), deleteDeptRule: vi.fn() }))
vi.mock('@/lib/api/client/admin', () => ({ fetchAdminUsers: mocks.list }))
vi.mock('antd', async (importOriginal) => ({
  ...await importOriginal<typeof import('antd')>(),
  App: { useApp: () => ({ modal: { confirm: mocks.confirm } }) },
}))
import { BatchApplyDeptRoles } from './BatchApplyDeptRoles'
import { DeptRoleMapper } from './DeptRoleMapper'

let root: Root
let host: HTMLDivElement
const users = [
  { id: 'u1', name: '张三', department: '质量部', roles: [{ id: 'old', name: '原有角色' }] },
  { id: 'u2', name: '李四', department: '生产部', roles: [] },
]
beforeEach(() => {
  vi.clearAllMocks()
  mocks.list.mockResolvedValue({ items: users, total: 2 })
  mocks.apply.mockResolvedValue({ ok: true, data: {} })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})
async function show() {
  await act(async () => root.render(createElement(BatchApplyDeptRoles, {
    role: { id: 'role1', code: 'reader', name: '质量查询', is_system: false, permissions: [] },
    departmentName: '质量部', onRunningChange: mocks.close,
  })))
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find((item) => item.textContent?.replace(/\s/g, '') === label)
  expect(found).toBeTruthy()
  return found!
}
async function selectAll() {
  await act(async () => document.querySelector<HTMLInputElement>('thead input[type="checkbox"]')!.click())
}
async function confirm() {
  await act(async () => button('保存应用角色').click())
  return mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void>; title: string }
}

it('requires selection and confirmation, then appends only configured roles for each selected user', async () => {
  await show()
  expect(button('保存应用角色').disabled).toBe(true)
  await selectAll()
  const dialog = await confirm()
  expect(mocks.apply).not.toHaveBeenCalled()
  expect(dialog.title).toContain('2 位用户应用“质量查询”')
  await act(async () => dialog.onOk())
  expect(mocks.apply.mock.calls).toEqual([['u1', ['role1']], ['u2', ['role1']]])
  expect(document.body.textContent).toContain('成功 2 位，失败 0 位')
  expect(document.body.textContent).toContain('已选 0 位用户')
  expect(mocks.list).toHaveBeenCalledTimes(2)
})

it('retains failed users and retries them without resubmitting successes', async () => {
  mocks.apply.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ ok: false, message: '管理员不能修改自己的角色' })
  await show()
  await selectAll()
  const dialog = await confirm()
  await act(async () => dialog.onOk())
  expect(document.body.textContent).toContain('成功 1 位，失败 1 位')
  expect(document.body.textContent).toContain('管理员不能修改自己的角色')
  expect(document.body.textContent).toContain('已选 1 位用户')
  await act(async () => button('重试所选用户').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.apply.mock.calls).toEqual([['u1', ['role1']], ['u2', ['role1']], ['u2', ['role1']]])
})

it('shows permission failures and offers a read retry without enabling writes', async () => {
  mocks.list.mockRejectedValueOnce(new Error('需要 identity:admin 权限'))
  await show()
  expect(document.body.textContent).toContain('需要 identity:admin 权限')
  expect(button('保存应用角色').disabled).toBe(true)
  await act(async () => button('重试').click())
  expect(document.body.textContent).toContain('张三')
  expect(mocks.apply).not.toHaveBeenCalled()
})

it.each([
  ['输入部门名称', '质量部', 'department_name'],
  ['输入飞书部门 ID', 'od-quality', 'department_id'],
])('requires a role and accepts the single selector %s', async (placeholder, value, field) => {
  await act(async () => root.render(createElement(DeptRoleMapper, {
    initialRules: [], initialDepartments: [], initialRoles: [
      { id: 'role1', code: 'reader', name: '质量查询', is_system: false, permissions: [] },
    ],
  })))
  expect(document.querySelector('.ant-alert')).toBeNull()
  await act(async () => button('查询部门用户').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 100)) })
  expect(document.body.textContent).toContain('请选择角色')
  expect(document.body.textContent).toContain('飞书部门 ID 或部门名称至少填写一个')
  expect(mocks.list).not.toHaveBeenCalled()
  await act(async () => document.querySelector('[role="combobox"]')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await act(async () => document.querySelector<HTMLElement>('.ant-select-item-option')!.click())
  const input = document.querySelector<HTMLInputElement>(`input[placeholder="${placeholder}"]`)!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('查询部门用户').click())
  expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ [field]: value, user_scope: 'department' }))
  expect(document.body.textContent).toContain('保存应用角色')
  await selectAll()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, `${value}2`)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(document.querySelector('section[aria-label="部门用户角色分配"]')).toBeNull()
})

it('allows supplementing missing-department users while retaining department selections', async () => {
  await show()
  await selectAll()
  const missing = [...document.querySelectorAll('label')].find((item) => item.textContent === '无部门名称')!
  await act(async () => missing.querySelector<HTMLInputElement>('input')!.click())
  expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ user_scope: 'missing' }))
  expect(document.body.textContent).toContain('已选 2 位用户')
  const all = [...document.querySelectorAll('label')].find((item) => item.textContent === '全部用户')!
  await act(async () => all.querySelector<HTMLInputElement>('input')!.click())
  expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ user_scope: 'all' }))
})

it('keeps processing remaining users after a transport exception', async () => {
  mocks.apply.mockRejectedValueOnce(new Error('连接中断，请核对后重试'))
  await show()
  await selectAll()
  const dialog = await confirm()
  await act(async () => dialog.onOk())
  expect(mocks.apply).toHaveBeenCalledTimes(2)
  expect(document.body.textContent).toContain('成功 1 位，失败 1 位')
  expect(document.body.textContent).toContain('连接中断，请核对后重试')
})

it('preserves selection across server pages and prevents duplicate submissions while running', async () => {
  mocks.list.mockResolvedValueOnce({ items: [users[0]], total: 21 }).mockResolvedValueOnce({ items: [users[1]], total: 21 })
  await show()
  await selectAll()
  await act(async () => document.querySelector<HTMLElement>('.ant-pagination-next')!.click())
  expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ keyword: '', offset: 20, limit: 20, user_scope: 'department' }))
  await selectAll()
  let finish!: () => void
  mocks.apply.mockImplementationOnce(() => new Promise((resolve) => { finish = () => resolve({ ok: true }) }))
  const dialog = await confirm()
  let pending!: Promise<void>
  await act(async () => { pending = dialog.onOk() })
  await act(async () => dialog.onOk())
  expect(mocks.apply).toHaveBeenCalledTimes(1)
  expect(button('保存应用角色').disabled).toBe(true)
  await act(async () => { finish(); await pending })
  expect(mocks.apply).toHaveBeenCalledTimes(2)
})
