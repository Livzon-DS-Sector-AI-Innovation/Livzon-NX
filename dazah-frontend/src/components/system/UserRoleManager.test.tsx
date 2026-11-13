/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ConfigProvider } from 'antd'
import type { AdminUserItem, RoleItem } from '@/lib/api/client/admin'
import { getAntdTheme } from '@/lib/antd-theme'

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
  mocks.assign.mockResolvedValue({ ok: true, data: { grant_version: 8 } })
  mocks.saveScope.mockResolvedValue({ ok: true, data: { id: 'scope-1' } })
  mocks.deleteScope.mockResolvedValue({ ok: true, data: { message: '已删除' } })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function renderManager(appearance: 'light' | 'dark' = 'light', initialRoles = roles) {
  await act(async () => {
    root.render(createElement(ConfigProvider, { theme: getAntdTheme(appearance) },
      createElement(UserRoleManager, { initialRoles, initialDepartments: [] })))
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

async function selectDepartmentScope(value: 'all' | 'departments') {
  const trigger = footerPanelButton('部门数据范围')
  if (trigger.getAttribute('aria-expanded') === 'false') await act(async () => trigger.click())
  await act(async () => document.querySelector<HTMLInputElement>(`input[type="radio"][value="${value}"]`)!.click())
}

function footerPanelButton(label: string) {
  const trigger = [...document.querySelectorAll<HTMLButtonElement>('.ant-drawer-footer button[aria-expanded]')]
    .find((button) => button.textContent?.startsWith(label))
  expect(trigger, label).toBeTruthy()
  return trigger!
}

async function openReason() {
  const trigger = footerPanelButton('授权调整原因')
  if (trigger.getAttribute('aria-expanded') === 'false') await act(async () => trigger.click())
  return document.querySelector<HTMLInputElement>('#role-assignment-reason')!
}

async function setInputValue(element: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function searchUsers(keyword: string) {
  const input = host.querySelector<HTMLInputElement>('input[placeholder^="按姓名"]')!
  await setInputValue(input, keyword)
  await act(async () => host.querySelector<HTMLButtonElement>('.ant-input-search-btn')!.click())
}

it.each(['light', 'dark'] as const)('searches the full directory and resets pagination in %s mode', async (appearance) => {
  const match = { ...user, id: 'user-501', name: '后页用户', email: 'account@example.test' }
  mocks.fetchUsers.mockResolvedValueOnce({ items: [user], total: 501 })
    .mockResolvedValueOnce({ items: [{ ...user, name: '第二页用户' }], total: 501 })
    .mockResolvedValueOnce({ items: [match], total: 1 })
  await renderManager(appearance)
  expect(mocks.fetchUsers).toHaveBeenLastCalledWith({ keyword: '', offset: 0, limit: 20 })
  await act(async () => host.querySelector<HTMLElement>('.ant-pagination-next button')!.click())
  expect(mocks.fetchUsers).toHaveBeenLastCalledWith({ keyword: '', offset: 20, limit: 20 })
  expect(host.textContent).toContain('第二页用户')

  await searchUsers('  ACCOUNT@example.test  ')
  expect(mocks.fetchUsers).toHaveBeenLastCalledWith({ keyword: 'ACCOUNT@example.test', offset: 0, limit: 20 })
  expect(host.textContent).toContain(match.name)
  expect(host.textContent).not.toContain('第二页用户')

  await act(async () => host.querySelector<HTMLElement>('.ant-input-clear-icon')!.click())
  expect(mocks.fetchUsers).toHaveBeenLastCalledWith({ keyword: '', offset: 0, limit: 20 })
  expect(host.textContent).toContain(user.name)
})

it('ignores stale requests and lets the latest failed search be retried', async () => {
  let finishOldSearch: (result: { items: AdminUserItem[]; total: number }) => void = () => {}
  await renderManager()
  mocks.fetchUsers.mockImplementationOnce(() => new Promise((resolve) => { finishOldSearch = resolve }))
    .mockRejectedValueOnce(new Error('需要用户管理权限'))
    .mockResolvedValueOnce({ items: [], total: 0 })

  await searchUsers('旧关键词')
  await searchUsers('新关键词')
  expect(mocks.message.error).toHaveBeenCalledWith('需要用户管理权限')
  expect(host.textContent).toContain('需要用户管理权限')
  expect(host.textContent).not.toContain(user.name)
  await act(async () => finishOldSearch({ items: [user], total: 1 }))
  expect(host.textContent).not.toContain(user.name)

  await act(async () => button('重试').click())
  expect(mocks.fetchUsers).toHaveBeenLastCalledWith({ keyword: '新关键词', offset: 0, limit: 20 })
  expect(host.textContent).toContain('没有符合条件的用户')
})

it('distinguishes assigned role levels from gray unassigned tags', async () => {
  mocks.fetchUsers.mockResolvedValue({ items: [
    { ...user, id: 'admin', roles: [roles[2]] },
    { ...user, id: 'ordinary', roles: [roles[3]] },
    { ...user, id: 'custom', roles: [roles[0]] },
    { ...user, id: 'unassigned', roles: [] },
  ], total: 4 })
  await renderManager()
  const tags = [...host.querySelectorAll('tbody .ant-tag')]
  expect(tags.map(tag => tag.textContent)).toEqual(['系统管理员', '普通管理员', '物料QA', '未分配'])
  expect(tags[0].classList.contains('ant-tag-purple')).toBe(true)
  expect(tags[1].classList.contains('ant-tag-blue')).toBe(true)
  expect(tags[2].classList.contains('ant-tag-green')).toBe(true)
  expect(tags[3].className).not.toMatch(/ant-tag-(purple|blue|green|gold)/)
})

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

it('offers role assignment and read-only effective permissions with automatic module access', async () => {
  await renderManager()
  expect(host.textContent).toContain('只需分配角色；模块入口随有效页面访问权限自动生效')
  const actions = [...host.querySelectorAll('.ant-table-tbody button')].map((item) => item.textContent?.trim())
  expect(actions).toEqual(['分配角色', '有效权限'])
  await act(async () => button('分配角色').click())
  const drawer = document.querySelector('.ant-drawer-body')!
  expect(drawer.textContent).not.toContain('模块入口随有效页面访问权限自动生效')
  expect(drawer.textContent).not.toContain('了解访问规则')
  await act(async () => button('预览权限').click())
  await act(async () => root.render(mocks.info.mock.lastCall![0].content))
  expect(host.textContent).toContain('模块入口随有效页面访问权限自动开通或关闭')
  expect(mocks.assign).not.toHaveBeenCalled()
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
  else await setInputValue(await openReason(), '调整职责')
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(mocks.confirm.mock.lastCall![0].title).toContain('放弃未保存')
  expect(document.querySelector('.ant-drawer-open')).toBeTruthy()
  if (change === 'roles') expect(roleCheckbox('体系QA').checked).toBe(true)
  else expect(document.querySelector<HTMLInputElement>('[aria-label="角色授权调整原因"]')!.value).toBe('调整职责')
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
  await setInputValue(await openReason(), '调整职责')
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
  await act(async () => button('了解访问规则').click())
  const rules = mocks.info.mock.lastCall![0] as { title: string; content: React.ReactNode }
  expect(rules.title).toBe('角色与数据范围规则')
  await act(async () => root.render(rules.content))
  expect(host.textContent).toContain('用户页面覆盖优先')
  expect(host.textContent).toContain('撤销最后一个可访问页面后，入口自动关闭')
  expect(host.textContent).toContain('系统管理员默认拥有全部模块访问权限')
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
  expect(footerPanelButton('授权调整原因').getAttribute('aria-expanded')).toBe('true')
  await setInputValue(await openReason(), '调整查看范围')
  await selectDepartmentScope('departments')
  await act(async () => button('保存').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('指定部门范围至少选择一个部门')
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.assign).not.toHaveBeenCalled()
})

it.each(['light', 'dark'] as const)('fills the reason from three presets and saves it in %s mode', async (appearance) => {
  await renderManager(appearance)
  await act(async () => button('分配角色').click())
  const reason = await openReason()
  expect(reason.value).toBe('')
  expect(reason.maxLength).toBe(20)
  expect(reason.closest('section')?.textContent).toContain('0 / 20')

  const presets = ['岗位职责调整', '临时工作授权', '权限回收']
  const trigger = footerPanelButton('授权调整原因')
  expect(document.querySelectorAll('[aria-label="预设授权调整原因"] button')).toHaveLength(3)
  for (const preset of presets) {
    await openReason()
    await act(async () => button(preset).click())
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(trigger.textContent).toContain(preset)
  }
  expect(button('保存').disabled).toBe(true)
  expect(mocks.assign).not.toHaveBeenCalled()

  await act(async () => roleCheckbox('物料QA').click())
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.assign).toHaveBeenCalledWith('user-1', [], { expectedGrantVersion: 7, reason: '权限回收' })
  expect(document.querySelector('.ant-drawer-open')).toBeNull()
})

it('saves the segmented department scope with the existing role assignment contract', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await selectDepartmentScope('all')
  const scopeButton = footerPanelButton('部门数据范围')
  expect(scopeButton.getAttribute('aria-expanded')).toBe('false')
  expect(scopeButton.textContent).toContain('全部部门')
  await setInputValue(await openReason(), '覆盖全部部门')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.saveScope).toHaveBeenCalledWith('user-1', 'all', [])
  expect(mocks.assign).not.toHaveBeenCalled()
})

it('preserves input after a failed save and allows retrying', async () => {
  mocks.assign.mockResolvedValueOnce({ ok: false, status: 409, message: '授权版本已变化，请刷新后重试' })
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('体系QA').click())
  await openReason()
  await act(async () => button('岗位职责调整').click())
  await setInputValue(await openReason(), '岗位职责调整：增加体系职责')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.message.error).toHaveBeenCalledWith('授权版本已变化，请刷新后重试')
  expect(roleCheckbox('体系QA').checked).toBe(true)
  expect((await openReason()).value).toBe('岗位职责调整：增加体系职责')
  expect(button('保存').disabled).toBe(false)
  expect(mocks.saveScope).not.toHaveBeenCalled()
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.assign).toHaveBeenLastCalledWith('user-1', ['role-a', 'role-b'], {
    expectedGrantVersion: 7, reason: '岗位职责调整：增加体系职责',
  })
  expect(document.querySelector('.ant-drawer-open')).toBeNull()
})

it('retries only the failed scope after roles have already been saved', async () => {
  mocks.saveScope.mockResolvedValueOnce({ ok: false, status: 500, message: '权限服务暂时不可用，请稍后重试' })
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('体系QA').click())
  await selectDepartmentScope('all')
  await setInputValue(await openReason(), '调整职责范围')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.message.error).toHaveBeenCalledWith('角色已保存，部门数据范围保存失败：权限服务暂时不可用，请稍后重试')
  expect(mocks.message.success).not.toHaveBeenCalled()
  expect(roleCheckbox('体系QA').checked).toBe(true)
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.assign).toHaveBeenCalledTimes(1)
  expect(mocks.saveScope).toHaveBeenCalledTimes(2)
  expect(mocks.message.success).toHaveBeenCalled()
})

it('uses the returned grant version when roles change again after a scope failure', async () => {
  mocks.saveScope.mockResolvedValueOnce({ ok: false, status: 500, message: '服务暂时不可用' })
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('体系QA').click())
  await selectDepartmentScope('all')
  await setInputValue(await openReason(), '调整职责范围')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  await act(async () => roleCheckbox('体系QA').click())
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.assign).toHaveBeenLastCalledWith('user-1', ['role-a'], {
    expectedGrantVersion: 8, reason: '调整职责范围',
  })
})

it('previews added roles and submits a versioned full replacement with a reason', async () => {
  await renderManager()
  await searchUsers('QA部')
  mocks.fetchUsers.mockClear()
  await act(async () => button('分配角色').click())
  expect(document.body.textContent).toContain('模块入口随有效页面访问权限自动生效')
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('分配角色 · QA部公用账号')
  await act(async () => roleCheckbox('体系QA').click())
  expect(document.body.textContent).toContain('新增 1')
  const reason = await openReason()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(reason, '增加体系文件维护职责')
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('保存').click())
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())
  expect(mocks.assign).toHaveBeenCalledWith('user-1', ['role-a', 'role-b'], {
    expectedGrantVersion: 7,
    reason: '增加体系文件维护职责',
  })
  expect(mocks.fetchUsers).toHaveBeenCalledExactlyOnceWith({ keyword: 'QA部', offset: 0, limit: 20 })
  expect(mocks.saveScope).not.toHaveBeenCalled()
  expect(mocks.deleteScope).not.toHaveBeenCalled()
})

it.each(['系统管理员', '普通管理员'])('requires confirmation before replacing six selected roles with %s', async (administrator) => {
  const extraRoles = Array.from({ length: 6 }, (_, index) => ({
    id: `extra-${index + 1}`, name: `自定义角色 ${index + 1}`, code: `extra_${index + 1}`,
    is_system: false, permissions: [],
  }))
  await renderManager('dark', [...roles, ...extraRoles])
  await act(async () => button('分配角色').click())
  const selected = document.querySelector('[aria-label="已选择的角色"]')!
  for (const role of extraRoles.slice(0, 5)) await act(async () => roleCheckbox(role.name).click())
  expect(selected.textContent).toContain('已选择 6 个角色')

  await act(async () => roleCheckbox(administrator).click())
  const confirmation = mocks.confirm.mock.lastCall![0]
  expect(confirmation.title).toBe(`切换为「${administrator}」？`)
  expect(confirmation.cancelText).toBe('保留当前选择')
  expect(selected.textContent).toContain('已选择 6 个角色')
  expect(roleCheckbox(administrator).checked).toBe(false)
  expect(roleCheckbox('物料QA').checked).toBe(true)

  await act(async () => confirmation.onOk())
  expect(selected.textContent).toContain('已选择 1 个角色')
  expect(roleCheckbox(administrator).checked).toBe(true)
  expect(roleCheckbox('物料QA').checked).toBe(false)
  expect(mocks.assign).not.toHaveBeenCalled()
})

it('keeps all seven compatible roles selected and submits their IDs', async () => {
  const extraRoles = Array.from({ length: 6 }, (_, index) => ({
    id: `extra-${index + 1}`, name: `自定义角色 ${index + 1}`, code: `extra_${index + 1}`,
    is_system: false, permissions: [],
  }))
  await renderManager('light', [...roles, ...extraRoles])
  await act(async () => button('分配角色').click())
  for (const role of extraRoles) await act(async () => roleCheckbox(role.name).click())
  expect(document.querySelector('[aria-label="已选择的角色"]')?.textContent).toContain('已选择 7 个角色')
  expect(roleCheckbox('物料QA').checked).toBe(true)
  expect(mocks.confirm).not.toHaveBeenCalled()
  await openReason()
  await act(async () => button('岗位职责调整').click())
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.assign).toHaveBeenCalledWith('user-1', ['role-a', ...extraRoles.map((role) => role.id)],
    { expectedGrantVersion: 7, reason: '岗位职责调整' })
})

it('lists administrators first and clears all selected roles across the current search', async () => {
  await renderManager('light', [roles[0], roles[3], roles[1], roles[2]])
  await act(async () => button('分配角色').click())
  const available = document.querySelector('[aria-label="添加角色"]')!
  expect([...available.querySelectorAll('label strong')].map((name) => name.textContent))
    .toEqual(['系统管理员', '普通管理员', '物料QA', '体系QA'])

  await act(async () => roleCheckbox('体系QA').click())
  const search = available.querySelector<HTMLInputElement>('[aria-label="搜索可分配角色"]')!
  await setInputValue(search, 'system_qa')
  await act(async () => button('取消全部选择').click())
  expect(document.querySelector('[aria-label="已选择的角色"]')?.textContent).toContain('已选择 0 个角色')
  expect(roleCheckbox('体系QA').checked).toBe(false)
  expect(button('取消全部选择').disabled).toBe(true)
  expect(mocks.assign).not.toHaveBeenCalled()

  await setInputValue(search, '')
  expect(roleCheckbox('物料QA').checked).toBe(false)
  await openReason()
  await act(async () => button('权限回收').click())
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.assign).toHaveBeenCalledWith('user-1', [], { expectedGrantVersion: 7, reason: '权限回收' })
})

it.each(['light', 'dark'] as const)('restores the opening roles after clearing a filtered selection in %s mode', async (appearance) => {
  await renderManager(appearance)
  await act(async () => button('分配角色').click())
  const restore = button('恢复原有选择')
  expect(restore.disabled).toBe(true)
  await act(async () => roleCheckbox('体系QA').click())
  const search = document.querySelector<HTMLInputElement>('[aria-label="搜索可分配角色"]')!
  await setInputValue(search, 'system_qa')
  await act(async () => button('取消全部选择').click())
  await act(async () => restore.click())
  expect(document.querySelector('[aria-label="已选择的角色"]')?.textContent).toContain('已选择 1 个角色')
  expect(search.value).toBe('system_qa')
  expect(roleCheckbox('体系QA').checked).toBe(false)
  expect(restore.disabled).toBe(true)
  expect(button('保存').disabled).toBe(true)
  await setInputValue(search, '')
  expect(roleCheckbox('物料QA').checked).toBe(true)
  expect(mocks.assign).not.toHaveBeenCalled()
})

it('keeps system administrator exclusive when switching back to a regular role', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('系统管理员').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(roleCheckbox('系统管理员').checked).toBe(true)
  expect(roleCheckbox('物料QA').checked).toBe(false)
  expect(document.body.textContent).toContain('保存后将授予全部系统权限')
  expect([...document.querySelectorAll('button')].some((item) => item.textContent?.includes('查看页面权限'))).toBe(false)
  await act(async () => roleCheckbox('物料QA').click())
  expect(roleCheckbox('系统管理员').checked).toBe(true)
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(roleCheckbox('系统管理员').checked).toBe(false)
  expect(roleCheckbox('物料QA').checked).toBe(true)
})

it('keeps ordinary administrator exclusive and explains the settings limit', async () => {
  await renderManager()
  await act(async () => button('分配角色').click())
  await act(async () => roleCheckbox('普通管理员').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(roleCheckbox('普通管理员').checked).toBe(true)
  expect(roleCheckbox('物料QA').checked).toBe(false)
  expect(document.body.textContent).toContain('不能进入系统设置')
})
