/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ConfigProvider } from 'antd'
import type { RolePagePermissionsOut } from '@/actions/admin'
import type { RoleItem } from '@/lib/api/client/admin'
import { antdTheme, getAntdTheme } from '@/lib/antd-theme'

const mocks = vi.hoisted(() => ({
  get: vi.fn(), preview: vi.fn(), replace: vi.fn(), confirm: vi.fn(), info: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('@/actions/admin', () => ({
  getRolePagePermissions: mocks.get, previewRolePagePermissions: mocks.preview,
  replaceRolePagePermissions: mocks.replace,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm, info: mocks.info } }) } }
})
import { RolePagePermissionsWorkbench } from './RolePagePermissionsWorkbench'

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

it('explains that module entries follow final role and user page access', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  expect(document.querySelectorAll('[data-platform-notice]')).toHaveLength(1)
  const notice = document.querySelector('[data-platform-notice="info"]')!
  expect(notice.textContent).toContain('模块入口随有效页面访问权限自动生效')
  expect(notice.textContent).toContain('高风险授权依赖普通操作')
  await act(async () => notice.querySelector<HTMLButtonElement>('button')!.click())
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('系统管理员默认拥有全部模块访问权限')
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('撤销最后一个可访问页面后关闭入口')
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('保存需填写调整原因，并预演和确认影响')
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('updates the combined notice count and warning after editing a permission', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  expect(document.querySelector('[role="status"]')?.textContent).toContain('暂无未保存调整')
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  expect(document.querySelectorAll('[data-platform-notice]')).toHaveLength(1)
  const notice = document.querySelector('[data-platform-notice="info"]')!
  expect(document.querySelector('[role="status"]')?.textContent).toContain('未保存调整 1 个页面')
  expect(notice.textContent).toContain('高风险授权依赖普通操作')
  expect(notice.querySelector('button')?.textContent).toContain('了解访问规则')
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('renders the three-column workbench and returns without prompting when clean', async () => {
  const onClose = vi.fn()
  mocks.get.mockResolvedValue(result('A'))
  await act(async () => root.render(createElement(RolePagePermissionsWorkbench,
    { role: role('A'), departments: [], onClose })))
  expect(host.querySelector('h1')?.textContent).toBe('页面权限基线配置')
  expect(host.querySelector('nav[aria-label="页面"]')).toBeTruthy()
  expect(host.querySelector('#role-page-permission-list')).toBeTruthy()
  expect(host.querySelector('#role-page-permission-detail')).toBeTruthy()
  expect(host.querySelector('.ant-drawer')).toBeNull()
  expect(host.textContent).not.toContain('继承上级')
  expect(host.textContent).not.toContain('继承关系说明')
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="返回权限管理"]')!.click())
  expect(onClose).toHaveBeenCalledOnce()
  expect(mocks.confirm).not.toHaveBeenCalled()
})

it('keeps edits until returning is confirmed', async () => {
  const onClose = vi.fn()
  mocks.get.mockResolvedValue(result('A'))
  await act(async () => root.render(createElement(RolePagePermissionsWorkbench,
    { role: role('A'), departments: [], onClose })))
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="返回权限管理"]')!.click())
  expect(onClose).not.toHaveBeenCalled()
  expect(document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.checked).toBe(true)
  const confirmation = mocks.confirm.mock.lastCall![0] as { title: string; cancelText: string; onOk: () => void }
  expect(confirmation.title).toBe('放弃未保存的角色授权？')
  expect(confirmation.cancelText).toBe('继续编辑')
  expect(confirmation).toEqual(expect.objectContaining({ centered: true, okText: '放弃更改' }))
  await act(async () => confirmation.onOk())
  expect(onClose).toHaveBeenCalledOnce()
})

it('puts overview details and separate controls in the right panel', async () => {
  const data = result('A')
  data.definitions = [{ page_key: 'production:overview', module_code: 'production', page_name: '生产管理概览',
    route_path: '/production', supported_scope_types: ['all'],
    sensitive_actions: [{ key: 'sync', name: '批次同步', category: 'integration_admin', description: '同步并更新批次数据' }] }]
  data.grants = [{ page_key: 'production:overview', module_code: 'production', source: 'role',
    permissions: ['access', 'query'], sensitive_actions: [], visible_sections: ['FA'], data_scope: { scope_type: 'all' } }]
  mocks.get.mockResolvedValue(data)
  await show('A')
  const visible = document.querySelector('section[aria-label="页面内可见项"]')!
  const sensitive = document.querySelector('section[aria-label="附加高风险操作"]')!
  expect(visible.parentElement).toBe(sensitive.parentElement)
  expect(visible.closest('#role-page-permission-detail')).toBeTruthy()
  expect(document.body.textContent).toContain('同步并更新批次数据')
  const sync = document.querySelector<HTMLInputElement>('input[value="sync"]')!
  expect(sync.disabled).toBe(true)
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="operate"]')!.click())
  expect(sync.disabled).toBe(false)
  expect(sync.checked).toBe(false)
  await act(async () => sync.click())
  expect(sync.checked).toBe(true)
  expect(document.querySelector<HTMLInputElement>('input[value="FA"]')!.checked).toBe(true)
  expect(document.querySelector<HTMLInputElement>('[data-page-name] input[value="operate"]')!.checked).toBe(true)
})

it('configures and saves exactly seven scheduling product visibility items', async () => {
  const pageKey = 'production:plan:scheduling'
  const data = result('A')
  data.definitions = [{ page_key: pageKey, module_code: 'production', page_name: '排产计划',
    route_path: '/production/scheduling', supported_scope_types: ['all'] }]
  data.grants = [{ page_key: pageKey, module_code: 'production', source: 'role',
    permissions: ['access', 'query'], visible_sections: null, data_scope: { scope_type: 'all' } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  const visible = document.querySelector('section[aria-label="页面内可见项"]')!
  const codes = ['MC', 'LN', 'DR', 'FA', 'LV', 'MV', 'TY']
  expect([...visible.querySelectorAll<HTMLInputElement>('input')].map((input) => input.value)).toEqual(codes)
  expect([...visible.querySelectorAll<HTMLInputElement>('input')].every((input) => input.checked)).toBe(true)
  await act(async () => visible.querySelector<HTMLInputElement>('input[value="MC"]')!.click())
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({
    grants: [expect.objectContaining({ page_key: pageKey, visible_sections: codes.filter((code) => code !== 'MC') })],
  }))
})

it.each([false, true])('independently toggles scheduling history correction for a role (existing=%s)', async (existing) => {
  const pageKey = 'production:plan:scheduling'
  const data = result('A')
  data.definitions = [{ page_key: pageKey, module_code: 'production', page_name: '排产计划',
    route_path: '/production/scheduling', supported_scope_types: ['all'], sensitive_actions: [
      { key: 'bulk_import', name: '批量导入或覆盖', category: 'bulk_change', description: '上传排产表' },
      { key: 'schedule-archive', name: '排产历史修正', category: 'bulk_change', description: '修正历史列并记录原因' },
    ] }]
  data.grants = [{ page_key: pageKey, module_code: 'production', source: 'role',
    permissions: ['access', 'query', 'operate'], sensitive_actions: existing ? ['bulk_import', 'schedule-archive'] : ['bulk_import'],
    data_scope: { scope_type: 'all' } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  const checkbox = document.querySelector<HTMLInputElement>('input[value="schedule-archive"]')!
  expect(checkbox.checked).toBe(existing)
  await act(async () => checkbox.click())
  expect(checkbox.checked).toBe(!existing)
  expect(document.querySelector<HTMLInputElement>('input[value="bulk_import"]')!.checked).toBe(true)
  const confirmation = await preview(false)
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ grants: [expect.objectContaining({
    page_key: pageKey, sensitive_actions: existing ? ['bulk_import'] : ['bulk_import', 'schedule-archive'],
  })] }))
})

it.each([
  { existing: false, mode: 'light' }, { existing: true, mode: 'light' },
  { existing: false, mode: 'dark' }, { existing: true, mode: 'dark' },
] as const)('saves and revokes pressure rejection independently ($mode, existing=$existing)', async ({ existing, mode }) => {
  const pageKey = 'production:pressure'
  const data = result('A')
  data.definitions = [{ page_key: pageKey, module_code: 'production', page_name: '压差管理',
    route_path: '/production/pressure', supported_scope_types: ['all'], sensitive_actions: [
      { key: 'approve', name: '批准业务申请', category: 'decision', description: '批准压差记录' },
      { key: 'reject', name: '驳回业务申请', category: 'decision', description: '驳回压差记录' },
    ] }]
  data.grants = [{ page_key: pageKey, module_code: 'production', source: 'role',
    permissions: ['access', 'query', 'operate'], sensitive_actions: existing ? ['approve', 'reject'] : ['approve'],
    data_scope: { scope_type: 'all' } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await act(async () => root.render(createElement(ConfigProvider, { theme: getAntdTheme(mode) },
    createElement(RolePagePermissionsWorkbench, { role: role('A'), departments: [], onClose: vi.fn() }))))
  const reject = document.querySelector<HTMLInputElement>('input[value="reject"]')!
  expect(reject.checked).toBe(existing)
  await act(async () => reject.click())
  expect(reject.checked).toBe(!existing)
  expect(document.querySelector<HTMLInputElement>('input[value="approve"]')!.checked).toBe(true)
  const confirmation = await preview(false)
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ grants: [expect.objectContaining({
    page_key: pageKey, sensitive_actions: existing ? ['approve'] : ['approve', 'reject'],
  })] }))
})

it('disables batch controls for an empty search and restores them after clearing it', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  const input = document.querySelector<HTMLInputElement>('[aria-label="搜索角色页面权限"]')!
  const searchFor = async (value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await searchFor('不存在的菜单')
  expect(document.body.textContent).toContain('当前筛选没有匹配页面')
  expect(batchButton().disabled).toBe(true)
  await searchFor('')
  expect(batchButton().disabled).toBe(false)
  expect(mocks.confirm).not.toHaveBeenCalled()
})

it('locks overview sections, risk actions and data scope while preview is pending', async () => {
  const data = result('A')
  data.definitions = [{ page_key: 'production:overview', module_code: 'production', page_name: '生产管理概览',
    route_path: '/production', supported_scope_types: ['all', 'production_fermentation'],
    sensitive_actions: [{ key: 'sync', name: '批次同步', category: 'integration_admin', description: '同步批次数据' }] }]
  data.grants = [{ page_key: 'production:overview', module_code: 'production', source: 'role',
    permissions: ['access', 'query'], data_scope: { scope_type: 'all' } }]
  mocks.get.mockResolvedValue(data)
  const pending = deferred<Awaited<ReturnType<typeof import('@/actions/admin').previewRolePagePermissions>>>()
  mocks.preview.mockReturnValue(pending.promise)
  await show('A')
  await act(async () => document.querySelector<HTMLInputElement>('input[value="FA"]')!.click())
  await act(async () => button('预览').click())
  expect(document.querySelector<HTMLInputElement>('input[value="FA"]')!.disabled).toBe(true)
  expect(document.querySelector<HTMLInputElement>('input[value="sync"]')!.disabled).toBe(true)
  expect(document.querySelector<HTMLInputElement>('[aria-label="生产管理概览数据范围"]')!.disabled).toBe(true)
  await act(async () => pending.resolve({ role_id: 'A', grant_version: 3, member_count: 0, affected_user_count: 0,
    expanded_user_count: 0, restricted_user_count: 0, mixed_user_count: 0, users_with_overrides: 0 }))
  expect(document.querySelector<HTMLInputElement>('input[value="FA"]')!.disabled).toBe(false)
})

it('keeps long page names readable and renders the route and identifier separately', async () => {
  const data = result('A')
  const name = '生产数据汇总及批次追溯管理（用于检查长菜单页面标题换行）'
  data.definitions = [{ page_key: 'production:overview', module_code: 'production',
    page_name: name, route_path: '/production', supported_scope_types: ['all'] }]
  mocks.get.mockResolvedValue(data)
  await act(async () => root.render(createElement(ConfigProvider, { theme: antdTheme },
    createElement(RolePagePermissionsWorkbench, { role: role('A'), departments: [], onClose: vi.fn() }))))
  const card = host.querySelector('article')
  expect(card?.querySelector('strong')?.textContent).toBe(name)
  expect(card?.textContent).toContain('/production')
  expect(card?.textContent).toContain('production:overview')
  expect(document.querySelector<HTMLInputElement>('input[value="FA"]')!.disabled).toBe(true)
})

it('shows high risk actions and editable data scope without changing it on save', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'role', permissions: ['access'],
    sensitive_actions: [], data_scope: { scope_type: 'departments', department_ids: ['stable-dept'] } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  expect(document.querySelector('details')).toBeNull()
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
  expect(document.body.textContent).toContain('附加高风险操作')
  expect(document.body.textContent).toContain('依赖普通操作')
  const action = document.querySelector<HTMLInputElement>('input[value="delete"]')!
  expect(action.disabled).toBe(true)
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="operate"]')!.click())
  expect(action.disabled).toBe(false)
  expect(action.checked).toBe(false)
  await act(async () => action.click())
  expect(action.checked).toBe(true)
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  expect(action.checked).toBe(false)
})

it('shows production overview stages instead of a department or inapplicable scope', async () => {
  const data = result('A')
  data.definitions = [{ page_key: 'production:overview', module_code: 'production',
    page_name: '生产管理概览', route_path: '/production',
    supported_scope_types: ['production_fermentation', 'production_extraction', 'all'] }]
  data.grants = [{ page_key: 'production:overview', module_code: 'production', source: 'role',
    permissions: ['access', 'query'], sensitive_actions: [], data_scope: { scope_type: 'all', department_ids: [] } }]
  mocks.get.mockResolvedValue(data)
  await show('A')
  expect(document.body.textContent).toContain('全部生产数据')
  expect(document.body.textContent).not.toContain('不适用')
})

it('saves selected overview sections separately from page query permission', async () => {
  const data = result('A')
  data.definitions = [{ page_key: 'production:overview', module_code: 'production',
    page_name: '生产管理概览', route_path: '/production', supported_scope_types: ['all'] }]
  data.grants = [{ page_key: 'production:overview', module_code: 'production', source: 'role',
    permissions: ['access', 'query'], visible_sections: null,
    data_scope: { scope_type: 'all' } }]
  mocks.get.mockResolvedValue(data)
  mocks.replace.mockResolvedValue({ ok: true, data })
  await show('A')
  const product = document.querySelector<HTMLInputElement>('input[value="FA"]')!
  expect(product.checked).toBe(true)
  await act(async () => product.click())
  const confirmation = await preview()
  await act(async () => { await confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ grants: [expect.objectContaining({
    permissions: ['access', 'query'],
    visible_sections: expect.not.arrayContaining(['FA']),
  })] }))
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
    root.render(createElement(RolePagePermissionsWorkbench, { role: role(id),
      departments: [{ id: 'dept-1', feishu_department_id: 'stable-dept', name: '质量部' }], onClose: vi.fn() }))
  })
}

it('opens the searchable role list from its label and switches using the full role name', async () => {
  const currentRole = role('A')
  const longRole = { ...role('B'), name: '质量管理中心原料药生产全过程质量审核与放行复核负责人' }
  const onRoleChange = vi.fn()
  await act(async () => root.render(createElement(RolePagePermissionsWorkbench, {
    role: currentRole, roles: [currentRole, longRole], departments: [], onClose: vi.fn(), onRoleChange,
    initialLoad: { ok: true, data: result('A') },
  })))

  const picker = host.querySelector('[role="combobox"][aria-labelledby="permission-role-label"]')
  const label = host.querySelector('#permission-role-label')
  expect(picker?.getAttribute('aria-expanded')).toBe('false')
  expect(label?.textContent).toBe('当前角色')
  await act(async () => label?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  expect(picker?.getAttribute('aria-expanded')).toBe('true')
  expect(document.querySelector('[role="option"][aria-selected="true"]')?.textContent).toBe(currentRole.name)
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')]
    .find((item) => item.textContent === longRole.name)
  expect(option).toBeTruthy()
  await act(async () => option?.click())
  expect(picker?.getAttribute('aria-expanded')).toBe('false')
  expect(onRoleChange).toHaveBeenCalledExactlyOnceWith(longRole.id)
})

it('uses server-loaded permissions on the first render without a second request', async () => {
  await act(async () => root.render(createElement(RolePagePermissionsWorkbench, {
    role: role('A'), departments: [], onClose: vi.fn(), initialLoad: { ok: true, data: result('A') },
  })))
  expect(host.querySelector('#role-page-permission-detail')?.getAttribute('aria-label')).toBe('页面权限详情：员工档案A')
  expect(button('保存').disabled).toBe(false)
  expect(mocks.get).not.toHaveBeenCalled()
})

it('can recover from an initial server load failure with one retry', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await act(async () => root.render(createElement(RolePagePermissionsWorkbench, {
    role: role('A'), departments: [], onClose: vi.fn(), initialLoad: { ok: false, message: '授权暂时不可用' },
  })))
  expect(host.textContent).toContain('授权暂时不可用')
  expect(button('保存').disabled).toBe(true)
  expect(mocks.get).not.toHaveBeenCalled()

  await act(async () => button('重新加载').click())
  expect(mocks.get).toHaveBeenCalledExactlyOnceWith('A')
  expect(host.querySelector('#role-page-permission-detail')?.getAttribute('aria-label')).toBe('页面权限详情：员工档案A')
})
function batchButton() {
  return button('批量设置')
}
async function selectBatchTier(label: string) {
  await act(async () => batchButton().click())
  const item = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')]
    .find((entry) => entry.textContent === `设为${label}`)
  expect(item).toBeTruthy()
  await act(async () => item!.click())
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find((node) => node.textContent?.replace(/\s/g, '') === label)
  expect(found, label).toBeTruthy()
  return found!
}
async function preview(changeTier = true) {
  if (changeTier) {
    await selectBatchTier('可查看')
    const batchConfirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
    expect(batchConfirmation).toEqual(expect.objectContaining({ centered: true, cancelText: '取消' }))
    await act(async () => { await batchConfirmation.onOk() })
  }
  const input = document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '岗位调整')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('保存').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(mocks.confirm).toHaveBeenCalled()
  expect(mocks.confirm.mock.lastCall![0]).toEqual(expect.objectContaining({
    centered: true, okText: '确认保存', cancelText: '返回修改',
  }))
  return mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
}

it('previews changes without requiring a reason or offering a save action', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  await act(async () => button('预览').click())
  expect(mocks.preview).toHaveBeenCalledWith('A', expect.objectContaining({
    expected_grant_version: 3, grants: [expect.objectContaining({ permissions: ['access', 'query'] })],
  }))
  expect(mocks.info).toHaveBeenCalledWith(expect.objectContaining({ title: '角色A的页面权限预览', okText: '返回修改' }))
  const content = renderToStaticMarkup(mocks.info.mock.lastCall![0].content)
  expect(content).toContain('角色成员 2 人，实际权限会变化 1 人')
  expect(content).toContain('权限扩大 1 人；权限收紧 0 人；混合变化 0 人')
  expect(mocks.info.mock.lastCall![0].onOk).toBeUndefined()
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(mocks.message.warning).not.toHaveBeenCalled()
  expect(document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.checked).toBe(true)
})

it('requires an adjustment reason before starting save confirmation', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  await act(async () => button('保存').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请填写本次角色授权调整原因')
  expect(mocks.preview).not.toHaveBeenCalled()
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('offers three reasons in the footer and sends the selected reason through save confirmation', async () => {
  mocks.get.mockResolvedValue(result('A'))
  mocks.replace.mockResolvedValue({ ok: true, data: { ...result('A'), grant_version: 4 } })
  await show('A')
  const input = host.querySelector<HTMLInputElement>('footer input[placeholder="填写角色授权调整原因"]')!
  const shortcuts = host.querySelector<HTMLButtonElement>('footer button[aria-label="快捷授权调整原因"]')!
  expect(input.maxLength).toBe(20)
  expect(host.querySelector('footer')?.textContent).toContain('0 / 20')
  await act(async () => shortcuts.click())
  const options = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')]
  expect(options.map((item) => item.textContent)).toEqual(['岗位权限调整', '数据范围调整', '收紧高风险权限'])
  await act(async () => options[1].click())
  expect(input.value).toBe('数据范围调整')
  expect(mocks.preview).not.toHaveBeenCalled()

  await act(async () => host.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ reason: '数据范围调整' }))
})

it('keeps edits and restores both buttons after a preview failure', async () => {
  mocks.get.mockResolvedValue(result('A'))
  mocks.preview.mockRejectedValue(new Error('影响预演失败'))
  await show('A')
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  await act(async () => button('预览').click())
  expect(document.body.textContent).toContain('影响预演失败')
  expect(document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.checked).toBe(true)
  expect(button('预览').disabled).toBe(false)
  expect(button('保存').disabled).toBe(false)
  expect(mocks.info).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
  await act(async () => button('重新加载').click())
  expect(mocks.confirm.mock.lastCall![0]).toEqual(expect.objectContaining({
    centered: true, title: '重新加载最新角色授权？', okText: '重新加载', cancelText: '继续编辑',
  }))
})

it('disables both actions during preview and ignores a late preview for a previous role', async () => {
  mocks.get.mockImplementation(async (id: string) => result(id))
  const pending = deferred<Awaited<ReturnType<typeof import('@/actions/admin').previewRolePagePermissions>>>()
  mocks.preview.mockReturnValue(pending.promise)
  await show('A')
  await act(async () => document.querySelector<HTMLInputElement>('[data-page-name] input[value="query"]')!.click())
  await act(async () => button('预览').click())
  expect(button('预览').disabled).toBe(true)
  expect(button('保存').disabled).toBe(true)
  expect(host.querySelector<HTMLButtonElement>('button[aria-label="快捷授权调整原因"]')?.disabled).toBe(true)
  await show('B')
  await act(async () => pending.resolve({ role_id: 'A', grant_version: 3, member_count: 2,
    affected_user_count: 1, expanded_user_count: 1, restricted_user_count: 0,
    mixed_user_count: 0, users_with_overrides: 1, affected_user_samples: [] }))
  expect(mocks.info).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(button('预览').disabled).toBe(false)
  expect(button('保存').disabled).toBe(false)
})

it('disables saving during initial loading and ignores a previous role response', async () => {
  const first = deferred<RolePagePermissionsOut>()
  mocks.get.mockImplementation((id: string) => id === 'A' ? first.promise : Promise.resolve(result(id)))
  await show('A')
  expect(button('保存').disabled).toBe(true)
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
  expect(mocks.preview).toHaveBeenCalledWith('A', expect.objectContaining({
    expected_grant_version: 3, reason: '岗位调整',
  }))
  let save: Promise<void> | void
  await act(async () => { save = confirmation.onOk() })
  expect(mocks.replace).toHaveBeenCalledWith('A', expect.objectContaining({ expected_grant_version: 3, reason: '岗位调整' }))
  await show('B')
  await act(async () => { pending.resolve({ ok: true, data: result('A') }); await save })
  expect(document.body.textContent).toContain('员工档案B')
  expect(button('保存').disabled).toBe(false)
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
  expect(button('保存').disabled).toBe(true)
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
  expect(batchButton().disabled).toBe(true)
  await act(async () => { pending.resolve({ ok: true, data: { ...result('A'), grant_version: 4 } }); await save })
  expect(batchButton().disabled).toBe(false)
  expect(document.querySelector<HTMLInputElement>('input[placeholder="填写角色授权调整原因"]')!.value).toBe('')
  expect(mocks.message.success).toHaveBeenCalledTimes(1)
})

it('shows only the selected module pages in the sidebar and opens leaf details', async () => {
  const data = result('A')
  data.definitions!.push(
    { ...data.definitions![0], page_key: 'hr:employee-management:contract', page_name: '合同档案' },
    { page_key: 'production:overview', module_code: 'production', page_name: '生产管理概览',
      route_path: '/production', supported_scope_types: ['all'] },
  )
  mocks.get.mockResolvedValue(data)
  await show('A')
  const tree = host.querySelector('nav[aria-label="页面"]')!
  expect(tree.querySelector('h2')?.textContent).toBe('页面')
  expect(tree.textContent).toContain('员工档案A')
  expect(tree.textContent).toContain('合同档案')
  expect(tree.textContent).not.toContain('生产管理概览')

  const treeButton = (label: string) => [...tree.querySelectorAll('button')].find((item) => item.textContent === label)!
  const collapse = tree.querySelector<HTMLButtonElement>('[aria-label="折叠员工管理导航"]')!
  await act(async () => collapse.click())
  expect(tree.textContent).not.toContain('合同档案')
  await act(async () => collapse.click())

  const input = host.querySelector<HTMLInputElement>('[aria-label="搜索角色页面权限"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '员工档案')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => treeButton('合同档案').click())
  expect(input.value).toBe('')
  expect(treeButton('合同档案').getAttribute('aria-pressed')).toBe('true')
  expect(host.querySelector('#role-page-permission-detail')?.getAttribute('aria-label')).toBe('页面权限详情：合同档案')
  expect(host.querySelector('#role-page-permission-list')?.textContent).toContain('2 个页面')

  const modules = host.querySelector('nav[aria-label="业务模块"]')!
  const production = [...modules.querySelectorAll('button')].find((item) => item.textContent === '生产管理')!
  await act(async () => production.click())
  expect(tree.textContent).toContain('生产管理概览')
  expect(tree.textContent).not.toContain('员工档案A')
  expect(tree.textContent).not.toContain('人事管理')
  expect(host.querySelector('#role-page-permission-detail')?.getAttribute('aria-label')).toBe('页面权限详情：生产管理概览')
})

it.each(['light', 'dark'] as const)('defaults to the selected page branch in %s mode', async (mode) => {
  const data = result('A')
  const definition = data.definitions![0]
  data.definitions = [
    { ...definition, page_key: 'hr:employee-management:profiles:detail' },
    { ...definition, page_key: 'hr:employee-management:contracts:detail', page_name: '合同档案' },
    { ...definition, page_key: 'hr:archives:detail', page_name: '历史档案' },
  ]
  mocks.get.mockResolvedValue(data)
  await act(async () => root.render(createElement(ConfigProvider, { theme: getAntdTheme(mode) },
    createElement(RolePagePermissionsWorkbench, { role: role('A'), departments: [], onClose: vi.fn() }))))
  const tree = host.querySelector('nav[aria-label="页面"]')!
  expect(tree.textContent).toContain('员工档案A')
  expect(tree.textContent).not.toContain('合同档案')
  expect(tree.textContent).not.toContain('历史档案')

  const input = host.querySelector<HTMLInputElement>('[aria-label="搜索角色页面权限"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '合同档案')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(tree.textContent).toContain('合同档案')
  expect(tree.textContent).not.toContain('员工档案A')
  expect(tree.textContent).not.toContain('历史档案')

  const archives = tree.querySelector<HTMLButtonElement>('[aria-label="展开archives导航"]')!
  await act(async () => archives.click())
  expect(archives.getAttribute('aria-expanded')).toBe('true')
  expect(tree.textContent).toContain('历史档案')
  await act(async () => archives.click())
  expect(archives.getAttribute('aria-expanded')).toBe('false')
  expect(tree.textContent).not.toContain('历史档案')
})

it('expands and collapses the inline summary independently of the detail panel', async () => {
  const data = result('A')
  data.definitions!.push({
    ...data.definitions![0], page_key: 'hr:employee-management:contracts', page_name: '合同档案',
  })
  mocks.get.mockResolvedValue(data)
  await show('A')
  const cardFor = (name: string) => [...host.querySelectorAll('article')]
    .find((card) => card.querySelector('strong')?.textContent === name)!
  const original = cardFor('员工档案A')
  const target = cardFor('合同档案')
  expect(original.textContent).toContain('当前配置')
  expect(target.textContent).not.toContain('当前配置')

  const toggle = target.querySelector<HTMLButtonElement>('[aria-expanded]')!
  await act(async () => toggle.click())
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  expect(target.textContent).toContain('当前配置')
  expect(original.textContent).not.toContain('当前配置')
  await act(async () => toggle.click())
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  expect(target.textContent).not.toContain('当前配置')
  expect(host.querySelector('#role-page-permission-detail')?.getAttribute('aria-label')).toBe('页面权限详情：合同档案')
})

it('focuses the search field with the advertised shortcut', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  const input = host.querySelector<HTMLInputElement>('[aria-label="搜索角色页面权限"]')!
  expect(input.getAttribute('aria-keyshortcuts')).toBe('Control+K Meta+K')
  const shortcut = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, cancelable: true })
  await act(async () => { window.dispatchEvent(shortcut) })
  expect(shortcut.defaultPrevented).toBe(true)
  expect(document.activeElement).toBe(input)
})

it('confirms the filtered group count and edits only matching pages', async () => {
  const data = result('A')
  data.definitions!.push(
    { ...data.definitions![0], page_key: 'hr:employee-management:other', page_name: '其他档案' },
    { ...data.definitions![0], page_key: 'hr:personnel:other', page_name: '合同档案' },
  )
  mocks.get.mockResolvedValue(data)
  await show('A')
  const tree = host.querySelector('nav[aria-label="页面"]')!
  const group = [...tree.querySelectorAll('button')].find((item) => item.textContent?.includes('员工管理'))!
  await act(async () => group.click())
  expect(host.querySelector('#role-page-permission-list')?.textContent).toContain('2 个页面')
  const input = host.querySelector<HTMLInputElement>('[aria-label="搜索角色页面权限"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '员工档案')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(host.querySelector('#role-page-permission-list')?.textContent).toContain('1 个页面')
  await selectBatchTier('可查看')
  const batch = mocks.confirm.mock.lastCall![0]
  expect(batch.content).toContain('员工管理的当前筛选结果中的 1 个页面')
  await act(async () => batch.onOk())
  await act(async () => button('预览').click())
  expect(mocks.preview.mock.lastCall![1].grants.map((grant: { page_key: string }) => grant.page_key))
    .toEqual(['hr:employee-management:profile'])
})

it('keeps existing high risk actions when a batch remains at operable', async () => {
  const data = result('A')
  data.definitions![0].sensitive_actions = [{ key: 'delete', name: '删除员工档案', category: 'destructive', description: '删除员工记录' }]
  data.grants = [{ page_key: 'hr:employee-management:profile', module_code: 'hr', source: 'role',
    permissions: ['access', 'query', 'operate'], sensitive_actions: ['delete'],
    data_scope: { scope_type: 'department_tree', department_ids: [] } }]
  mocks.get.mockResolvedValue(data)
  await show('A')
  await selectBatchTier('普通操作')
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> | void }
  await act(async () => { await confirmation.onOk() })
  expect(document.querySelector<HTMLInputElement>('input[value="delete"]')!.checked).toBe(true)
})
