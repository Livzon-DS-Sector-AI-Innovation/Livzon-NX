/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ConfigProvider } from 'antd'
import type { RolePagePermissionsOut } from '@/actions/admin'
import type { RoleItem } from '@/lib/api/client/admin'
import { antdTheme } from '@/lib/antd-theme'

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

it('explains that module entries follow final role and user page access', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  const notice = document.querySelector('[data-platform-notice="info"]')!
  expect(notice.textContent).toContain('模块入口随有效页面访问权限自动生效')
  await act(async () => notice.querySelector<HTMLButtonElement>('button')!.click())
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('系统管理员默认拥有全部模块访问权限')
  expect(document.querySelector('.ant-modal-body')?.textContent).toContain('撤销最后一个可访问页面后关闭入口')
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('opens as a right drawer and closes from the left mask when no edits are pending', async () => {
  const onClose = vi.fn()
  mocks.get.mockResolvedValue(result('A'))
  await act(async () => root.render(createElement(RolePagePermissionsDrawer,
    { role: role('A'), departments: [], open: true, onClose })))
  expect(document.querySelector('.ant-drawer-right')).toBeTruthy()
  expect(document.querySelector('.ant-modal')).toBeNull()
  const mask = document.querySelector<HTMLElement>('.ant-drawer-mask')!
  expect(mask).toBeTruthy()
  await act(async () => mask.click())
  expect(onClose).toHaveBeenCalledOnce()
  expect(mocks.confirm).not.toHaveBeenCalled()
})

it('keeps edits after a mask click until discarding them is confirmed', async () => {
  const onClose = vi.fn()
  mocks.get.mockResolvedValue(result('A'))
  await act(async () => root.render(createElement(RolePagePermissionsDrawer,
    { role: role('A'), departments: [], open: true, onClose })))
  await act(async () => button('展开全部菜单').click())
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.click())
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(onClose).not.toHaveBeenCalled()
  expect(document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.checked).toBe(true)
  const confirmation = mocks.confirm.mock.lastCall![0] as { title: string; cancelText: string; onOk: () => void }
  expect(confirmation.title).toBe('放弃未保存的角色授权？')
  expect(confirmation.cancelText).toBe('继续编辑')
  expect(confirmation).toEqual(expect.objectContaining({ centered: true, okText: '放弃更改' }))
  await act(async () => confirmation.onOk())
  expect(onClose).toHaveBeenCalledOnce()
})

it('opens overview details across the table and preserves selections when collapsed and reopened', async () => {
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
  expect(visible.closest('.ant-table-cell')?.getAttribute('colspan')).toBe('4')
  expect(document.body.textContent).toContain('同步并更新批次数据')
  await act(async () => document.querySelector<HTMLInputElement>('input[value="sync"]')!.click())
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="折叠生产管理概览"]')!.click())
  expect(document.querySelector('section[aria-label="页面内可见项"]')).toBeNull()
  await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="展开生产管理概览"]')!.click())
  expect(document.querySelector<HTMLInputElement>('input[value="sync"]')!.checked).toBe(true)
  expect(document.querySelector<HTMLInputElement>('input[value="FA"]')!.checked).toBe(true)
  expect(document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="operate"]')!.checked).toBe(true)
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
  await act(async () => button('展开全部菜单').click())
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
  expect(button('可查看').disabled).toBe(true)
  expect(button('普通操作').disabled).toBe(true)
  await searchFor('')
  expect(button('可查看').disabled).toBe(false)
  expect(button('普通操作').disabled).toBe(false)
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

it('renders menu group and page headings at 15px with separate permission keys', async () => {
  mocks.get.mockResolvedValue(result('A'))
  await show('A')
  await act(async () => button('展开全部菜单').click())
  const headings = [...document.querySelectorAll('h4')]
  const group = headings.find((heading) => heading.textContent === '员工管理')
  const page = headings.find((heading) => heading.textContent === '员工档案A')
  expect(group).toBeTruthy()
  expect(page).toBeTruthy()
  for (const heading of [group!, page!]) {
    expect(heading.style.fontSize).toBe('15px')
  }
  expect(page!.parentElement!.textContent).not.toContain('hr:employee-management:profile')
  expect(document.body.textContent).toContain('hr:employee-management:profile')
})

it('keeps the requested 15px page heading size under a different theme and displays a long name in full', async () => {
  const data = result('A')
  const name = '生产数据汇总及批次追溯管理（用于检查长菜单页面标题换行）'
  data.definitions = [{ page_key: 'production:overview', module_code: 'production',
    page_name: name, route_path: '/production', supported_scope_types: ['all'] }]
  mocks.get.mockResolvedValue(data)
  await act(async () => root.render(createElement(ConfigProvider,
    { theme: { ...antdTheme, token: { ...antdTheme.token, fontSizeXL: 24 } } },
    createElement(RolePagePermissionsDrawer, { role: role('A'), departments: [], open: true, onClose: vi.fn() }))))
  const heading = document.querySelector('h4')!
  expect(heading.textContent).toBe(name)
  expect(heading.style.fontSize).toBe('15px')
  expect(heading.parentElement!.textContent).not.toContain('production:overview')
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
  expect(document.body.textContent).not.toContain('高风险权限需要有效期限')
  expect([...document.querySelectorAll('button')].some((item) => item.textContent?.includes('续期'))).toBe(false)
  expect(document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="operate"]')!.checked).toBe(true)
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.click())
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
  await act(async () => button('展开全部菜单').click())
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
  await act(async () => button('展开全部菜单').click())
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
  expect(batchConfirmation).toEqual(expect.objectContaining({ centered: true, cancelText: '取消' }))
  await act(async () => { await batchConfirmation.onOk() })
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
  await act(async () => button('展开全部菜单').click())
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.click())
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
  expect(document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.checked).toBe(true)
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

it('keeps edits and restores both buttons after a preview failure', async () => {
  mocks.get.mockResolvedValue(result('A'))
  mocks.preview.mockRejectedValue(new Error('影响预演失败'))
  await show('A')
  await act(async () => button('展开全部菜单').click())
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.click())
  await act(async () => button('预览').click())
  expect(document.body.textContent).toContain('影响预演失败')
  expect(document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.checked).toBe(true)
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
  await act(async () => button('展开全部菜单').click())
  await act(async () => document.querySelector<HTMLInputElement>('[aria-label="权限档位"] input[value="query"]')!.click())
  await act(async () => button('预览').click())
  expect(button('预览').disabled).toBe(true)
  expect(button('保存').disabled).toBe(true)
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
