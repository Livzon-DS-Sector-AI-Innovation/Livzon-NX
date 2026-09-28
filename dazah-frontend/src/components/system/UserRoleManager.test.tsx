/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AdminUserItem, RoleItem } from '@/lib/api/client/admin'

const mocks = vi.hoisted(() => ({
  fetchUsers: vi.fn(), fetchScopes: vi.fn(), assign: vi.fn(), deleteScope: vi.fn(),
  saveScope: vi.fn(), confirm: vi.fn(), info: vi.fn(),
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
  return { ...actual, App: { useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm, info: mocks.info } }) } }
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

async function setInputValue(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  await act(async () => {
    const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

it('opens assignment in a right drawer and cancels without saving', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  const drawer = document.querySelector('.ant-drawer-right.ant-drawer-open')
  expect(drawer).toBeTruthy()
  expect(document.querySelector('.ant-modal')).toBeNull()
  expect(drawer!.querySelector('.ant-drawer-body')?.textContent).toContain('添加角色')
  expect(drawer!.querySelector('.ant-drawer-footer')?.textContent).toContain('预览权限')
  await act(async () => button('取消').click())
  expect(document.querySelector('.ant-drawer-open')).toBeNull()
  expect(mocks.assign).not.toHaveBeenCalled()
  expect(mocks.saveScope).not.toHaveBeenCalled()
})

it('closes an unchanged assignment by clicking outside, but keeps it open for inside clicks', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-body')!.click())
  expect(document.querySelector('.ant-drawer-open')).toBeTruthy()
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(document.querySelector('.ant-drawer-open')).toBeNull()
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.assign).not.toHaveBeenCalled()
  expect(mocks.saveScope).not.toHaveBeenCalled()
})

it.each(['roles', 'reason'])('confirms before discarding unsaved %s on an outside click', async (change) => {
  await renderManager()
  await act(async () => button('分配角色').click())
  if (change === 'roles') await act(async () => roleCheckbox('体系QA').click())
  else await setInputValue(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!, '调整职责')
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(mocks.confirm.mock.lastCall![0].title).toContain('放弃未保存')
  expect(document.querySelector('.ant-drawer-open')).toBeTruthy()
  if (change === 'roles') expect(roleCheckbox('体系QA').checked).toBe(true)
  else expect(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!.value).toBe('调整职责')
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(document.querySelector('.ant-drawer-open')).toBeNull()
  expect(mocks.assign).not.toHaveBeenCalled()
  expect(mocks.saveScope).not.toHaveBeenCalled()
})

it('blocks outside clicks while saving and restores closing after a failed save', async () => {
  let rejectSave: (error: Error) => void = () => {}
  mocks.assign.mockImplementationOnce(() => new Promise<void>((_resolve, reject) => { rejectSave = reject }))
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('体系QA').click())
  await setInputValue(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!, '调整职责')
  await act(async () => button('保存').click())
  let pendingSave: Promise<void> | undefined
  await act(async () => { pendingSave = mocks.confirm.mock.lastCall![0].onOk() })
  mocks.confirm.mockClear()
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(document.querySelector('.ant-drawer-open')).toBeTruthy()
  expect(mocks.confirm).not.toHaveBeenCalled()
  await act(async () => { rejectSave(new Error('保存失败')); await pendingSave })
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(mocks.confirm.mock.lastCall![0].title).toContain('放弃未保存')
  expect(roleCheckbox('体系QA').checked).toBe(true)
})

it('removes a selected tag, keeps selection across searches, and explains empty results', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  expect(button('保存').disabled).toBe(true)
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="移除角色 物料QA"]')!.click())
  expect(roleCheckbox('物料QA').checked).toBe(false)
  expect(document.body.textContent).toContain('尚未选择角色')
  expect(button('保存').disabled).toBe(false)
  await act(async () => roleCheckbox('体系QA').click())
  const search = document.querySelector<HTMLInputElement>('[aria-label="搜索可分配角色"]')!
  await setInputValue(search, 'material_qa')
  expect(document.querySelector('[aria-label="添加角色"]')!.textContent).not.toContain('体系QA')
  expect(document.querySelector('[aria-label="已选择的角色"]')!.textContent).toContain('体系QA')
  await setInputValue(search, '不存在的角色')
  expect(document.body.textContent).toContain('没有匹配的角色，请调整搜索条件')
  await setInputValue(search, '')
  expect(roleCheckbox('体系QA').checked).toBe(true)
})

it('opens rules and a read-only preview without requiring changes or an audit reason', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => button('了解访问规则').click())
  const rules = mocks.info.mock.lastCall![0] as { title: string; content: React.ReactNode }
  expect(rules.title).toBe('角色与数据范围规则')
  await act(async () => root.render(rules.content))
  expect(host.textContent).toContain('用户页面覆盖优先')
  expect(host.textContent).toContain('尚未接入页面级数据范围')
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => button('预览权限').click())
  const preview = mocks.info.mock.lastCall![0] as { content: React.ReactNode }
  await act(async () => root.render(preview.content))
  expect(host.textContent).toContain('物料QA')
  expect(host.textContent).toContain('本部门 + 子部门')
  expect(host.textContent).toContain('有效权限还取决于用户页面覆盖')
  expect(mocks.assign).not.toHaveBeenCalled()
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.message.warning).not.toHaveBeenCalled()
})

it('requires a reason and validates specified departments before confirming a save', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('体系QA').click())
  await act(async () => button('保存').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请填写本次授权调整原因')
  await setInputValue(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!, '调整查看范围')
  const departmentOption = document.querySelector<HTMLInputElement>('input[type="radio"][value="departments"]')!
  await act(async () => departmentOption.click())
  await act(async () => button('保存').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('指定部门范围至少选择一个部门')
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.assign).not.toHaveBeenCalled()
})

it('saves the segmented department scope with the existing role assignment contract', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => document.querySelector<HTMLInputElement>('input[type="radio"][value="all"]')!.click())
  await setInputValue(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!, '覆盖全部部门')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.saveScope).toHaveBeenCalledWith('user-1', 'all', [])
  expect(mocks.assign).toHaveBeenCalledWith('user-1', ['role-a'], {
    expectedGrantVersion: 7, reason: '覆盖全部部门',
  })
})

it('preserves input after a failed save and allows retrying', async () => {
  mocks.assign.mockRejectedValueOnce(new Error('授权版本已变化，请刷新后重试'))
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('体系QA').click())
  await setInputValue(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!, '增加体系职责')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.message.error).toHaveBeenCalledWith('授权版本已变化，请刷新后重试')
  expect(roleCheckbox('体系QA').checked).toBe(true)
  expect(document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!.value).toBe('增加体系职责')
  expect(button('保存').disabled).toBe(false)
  expect(mocks.saveScope).not.toHaveBeenCalled()
})

it('previews added roles and submits a versioned full replacement with a reason', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  expect(document.body.textContent).toContain('角色决定功能权限，部门范围决定可查看的数据范围。')
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('分配角色 · QA部公用账号')
  await act(async () => roleCheckbox('体系QA').click())
  expect(document.body.textContent).toContain('新增 1')
  const reason = document.querySelector<HTMLTextAreaElement>('[aria-label="角色授权调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(reason, '增加体系文件维护职责')
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('保存').click())
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
