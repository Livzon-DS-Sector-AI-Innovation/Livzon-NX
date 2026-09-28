/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { UserModulePermissionsOut } from '@/actions/users'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  replace: vi.fn(),
  confirm: vi.fn(),
  info: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/actions/users', () => ({
  getUserModulePermissions: mocks.get,
  replaceUserModulePermissions: mocks.replace,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return {
    ...actual,
    App: {
      useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm, info: mocks.info } }),
    },
  }
})

import UserModuleAccessDrawer from './UserModuleAccessDrawer'

const result = (): UserModulePermissionsOut => ({
  user_id: '00000000-0000-0000-0000-000000000001',
  grant_version: 4,
  available_modules: [
    { module_code: 'production', module_name: '生产管理', description: '生产业务' },
    { module_code: 'quality', module_name: '质量管理', description: '质量业务' },
  ],
  grants: [{
    module_code: 'production',
    module_name: '生产管理',
    permissions: ['module.view', 'module.agent.read'],
    data_scope: { department_ids: ['dept-1'] },
    grant_version: 4,
    granted_by: '00000000-0000-0000-0000-000000000002',
    status: 'active',
    updated_at: '2026-09-01T00:00:00Z',
  }],
  livzon_sync_status: 'synced',
})

let root: Root
let host: HTMLDivElement

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  mocks.get.mockResolvedValue(result())
  mocks.replace.mockImplementation(async (_id: string, request: { grants: UserModulePermissionsOut['grants'] }) => ({
    ...result(),
    grant_version: 5,
    grants: request.grants,
  }))
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function show({ isSystemAdmin = false, onClose = vi.fn() } = {}) {
  await act(async () => {
    root.render(createElement(UserModuleAccessDrawer, {
      user: {
        id: '00000000-0000-0000-0000-000000000001',
        name: '测试用户',
        isSystemAdmin,
      },
      open: true,
      onClose,
    }))
  })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

async function setReason(value: string) {
  const reason = document.querySelector<HTMLTextAreaElement>('[aria-label="模块访问调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(reason, value)
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

function confirmationText() {
  return renderToStaticMarkup(mocks.confirm.mock.lastCall![0].content)
}

function button(label: string) {
  const found = [...document.querySelectorAll('button')].find(
    (node) => node.textContent?.replace(/\s/g, '') === label
  )
  expect(found, label).toBeTruthy()
  return found!
}

it('uses a concise unified notice with a read-only access rules entry', async () => {
  await show()
  const rulesButton = button('了解访问规则')
  const notice = rulesButton.closest('.ant-alert')!
  expect(notice.classList.contains('ant-alert-info')).toBe(true)
  expect(notice.classList.contains('ant-alert-with-description')).toBe(false)
  expect(notice.querySelector('.ant-alert-icon')).toBeTruthy()
  expect(notice.querySelector('.ant-alert-actions')?.contains(rulesButton)).toBe(true)
  expect(notice.textContent).toContain('模块控制访问入口，角色提供页面和操作权限基线。')
  await act(async () => rulesButton.click())
  const rules = mocks.info.mock.lastCall![0]
  expect(rules.title).toBe('模块访问与页面权限规则')
  expect(rules.okText).toBe('我知道了')
  expect(renderToStaticMarkup(rules.content)).toContain('具体页面和操作权限仍按已分配角色及用户页面配置生效')
  expect(renderToStaticMarkup(rules.content)).toContain('不会自动授予全部页面和操作权限')
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(mocks.confirm).not.toHaveBeenCalled()
})

it('closes unchanged module access on an outside click without saving', async () => {
  const onClose = vi.fn()
  await show({ onClose })
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-body')!.click())
  expect(onClose).not.toHaveBeenCalled()
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(onClose).toHaveBeenCalledOnce()
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('keeps module edits until an outside click discard is confirmed', async () => {
  const onClose = vi.fn()
  await show({ onClose })
  await act(async () => button('全部关闭').click())
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(mocks.confirm.mock.lastCall![0].title).toContain('放弃未保存')
  expect(onClose).not.toHaveBeenCalled()
  expect(document.querySelector<HTMLInputElement>('[aria-label="生产管理模块访问"]')!.checked).toBe(false)
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(onClose).toHaveBeenCalledOnce()
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('adds module access while preserving existing advanced permissions and data scope', async () => {
  await show()
  expect(document.querySelector('.ant-drawer-header')?.textContent).toContain('模块访问 · 测试用户')
  expect(document.body.textContent).toContain('角色提供页面和操作权限基线')

  const qualityRow = [...document.querySelectorAll('tr')].find((row) => row.textContent?.includes('质量管理'))
  const qualityCheckbox = qualityRow?.querySelector<HTMLInputElement>('input[type="checkbox"]')
  expect(qualityCheckbox).toBeTruthy()
  await act(async () => qualityCheckbox!.click())

  await setReason('岗位职责调整')
  await act(async () => button('保存').click())
  expect(confirmationText()).toContain('新增 1 个模块访问入口')
  expect(confirmationText()).toContain('质量管理')
  expect(confirmationText()).toContain('岗位职责调整')
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())

  expect(mocks.replace).toHaveBeenCalledWith(
    '00000000-0000-0000-0000-000000000001',
    expect.objectContaining({
      expected_grant_version: 4,
      reason: '岗位职责调整',
      grants: expect.arrayContaining([
        expect.objectContaining({
          module_code: 'production',
          permissions: expect.arrayContaining(['module.view', 'module.agent.read']),
          data_scope: { department_ids: ['dept-1'] },
        }),
        expect.objectContaining({ module_code: 'quality', permissions: ['module.view'] }),
      ]),
    })
  )
  expect(mocks.message.success).toHaveBeenCalledWith('模块访问权限已保存并生效')
})

it('requires an audit reason before saving access changes', async () => {
  await show()
  await act(async () => button('全部关闭').click())
  await act(async () => button('保存').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请填写本次模块访问调整原因')
  const reason = document.querySelector<HTMLTextAreaElement>('[aria-label="模块访问调整原因"]')!
  expect(reason.getAttribute('aria-invalid')).toBe('true')
  expect(document.querySelector('#module-access-reason-error')?.textContent).toContain('请填写')
  expect(document.activeElement).toBe(reason)
  await setReason('停用访问的原因')
  expect(reason.getAttribute('aria-invalid')).toBe('false')
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('shows only top navigation modules and preserves hidden grants when closing all visible access', async () => {
  const initial = result()
  mocks.get.mockResolvedValue({
    ...initial,
    available_modules: [
      ...(initial.available_modules || []),
      { module_code: 'environment', module_name: '环保管理', description: '环保业务' },
    ],
    grants: [
      ...(initial.grants || []),
      { ...initial.grants![0], module_code: 'environment', module_name: '环保管理' },
    ],
  })
  await show()

  expect(document.body.textContent).toContain('生产管理')
  expect(document.body.textContent).toContain('质量管理')
  expect(document.body.textContent).not.toContain('环保管理')
  await act(async () => button('全部关闭').click())
  expect(document.body.textContent).toContain('已允许 0 个模块')
  await setReason('导航模块调整')
  await act(async () => button('保存').click())
  const confirmation = mocks.confirm.mock.lastCall![0] as { onOk: () => Promise<void> }
  await act(async () => confirmation.onOk())

  expect(mocks.replace).toHaveBeenCalledWith(
    '00000000-0000-0000-0000-000000000001',
    expect.objectContaining({
      grants: [expect.objectContaining({ module_code: 'environment' })],
    }),
  )
})

it('opens a read-only preview without changes or a reason', async () => {
  await show()
  expect(button('保存').disabled).toBe(true)
  await act(async () => button('预览权限').click())
  const preview = mocks.info.mock.lastCall![0]
  expect(preview.title).toContain('模块访问配置预览')
  expect(renderToStaticMarkup(preview.content)).toContain('生产管理')
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.message.warning).not.toHaveBeenCalled()
})

it('filters modules without changing selected access and explains the batch operation scope', async () => {
  await show()
  const search = document.querySelector<HTMLInputElement>('[aria-label="搜索模块"]')!
  const typeSearch = async (value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(search, value)
    search.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await typeSearch('quality')
  expect(document.querySelector('[aria-label="模块访问配置"]')?.textContent).not.toContain('生产管理')
  expect(document.body.textContent).toContain('批量操作适用于全部 2 个可配置模块')
  await act(async () => button('全部允许').click())
  expect(document.body.textContent).toContain('已允许 2 个模块')
  await typeSearch('不存在的模块')
  expect(document.body.textContent).toContain('没有匹配的模块，请调整搜索条件')
  await typeSearch('')
  expect(document.querySelector<HTMLInputElement>('[aria-label="生产管理模块访问"]')!.checked).toBe(true)
  expect(document.querySelector<HTMLInputElement>('[aria-label="质量管理模块访问"]')!.checked).toBe(true)
})

it('shows system administrator access as allowed and prevents edits', async () => {
  await show({ isSystemAdmin: true })
  expect(document.body.textContent).toContain('系统管理员默认拥有全部模块访问权限')
  expect(document.body.textContent).toContain('已允许 2 个模块')
  for (const checkbox of document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')) {
    expect(checkbox.disabled).toBe(true)
    expect(checkbox.checked).toBe(true)
  }
  expect(button('保存').disabled).toBe(true)
  expect(button('全部允许').disabled).toBe(true)
  expect(button('全部关闭').disabled).toBe(true)
  expect(document.querySelector<HTMLTextAreaElement>('[aria-label="模块访问调整原因"]')!.disabled).toBe(true)
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('requires confirmation before refreshing unsaved adjustments', async () => {
  await show()
  await act(async () => button('全部关闭').click())
  await setReason('保留这个原因')
  await act(async () => button('刷新').click())
  expect(mocks.get).toHaveBeenCalledTimes(1)
  expect(confirmationText()).toContain('放弃未保存的模块访问调整和授权原因')
  expect(document.querySelector<HTMLTextAreaElement>('[aria-label="模块访问调整原因"]')!.value).toBe('保留这个原因')
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.get).toHaveBeenCalledTimes(2)
  expect(document.body.textContent).toContain('已允许 1 个模块')
  expect(document.querySelector<HTMLTextAreaElement>('[aria-label="模块访问调整原因"]')!.value).toBe('')
})

it('keeps access changes and the reason after failure and retries saving without reloading', async () => {
  mocks.replace.mockRejectedValueOnce(new Error('保存请求失败'))
  await show()
  await act(async () => button('全部关闭').click())
  await setReason('暂时停用访问')
  await act(async () => button('保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(document.body.textContent).toContain('本地修改已保留')
  expect(document.body.textContent).toContain('已允许 0 个模块')
  expect(document.querySelector<HTMLTextAreaElement>('[aria-label="模块访问调整原因"]')!.value).toBe('暂时停用访问')
  await act(async () => button('重试保存').click())
  await act(async () => mocks.confirm.mock.lastCall![0].onOk())
  expect(mocks.get).toHaveBeenCalledTimes(1)
  expect(mocks.replace).toHaveBeenCalledTimes(2)
  expect(document.body.textContent).not.toContain('本地修改已保留')
  expect(mocks.message.success).toHaveBeenCalled()
})

it('distinguishes loading failures from an empty module list and can reload', async () => {
  mocks.get.mockRejectedValueOnce(new Error('无权限读取模块配置'))
  await show()
  expect(document.body.textContent).toContain('无权限读取模块配置')
  expect(document.body.textContent).not.toContain('暂无可配置的业务模块')
  expect(button('保存').disabled).toBe(true)
  await act(async () => button('重新加载').click())
  expect(document.body.textContent).toContain('生产管理')
  expect(document.body.textContent).not.toContain('无权限读取模块配置')
})

it('shows registration guidance when there are no configurable modules', async () => {
  mocks.get.mockResolvedValue({ ...result(), available_modules: [], grants: [] })
  await show()
  expect(document.body.textContent).toContain('暂无可配置的业务模块，请检查模块注册与导航配置')
  expect(button('保存').disabled).toBe(true)
})

it('warns when access is saved but agent scope synchronization has failed', async () => {
  mocks.get.mockResolvedValue({ ...result(), livzon_sync_status: 'failed', livzon_last_error: '能力注册暂不可用' })
  await show()
  expect(document.body.textContent).toContain('模块访问已保存，但 Livzon 范围同步失败')
  const syncNotice = [...document.querySelectorAll<HTMLElement>('[data-platform-notice]')]
    .find((notice) => notice.textContent?.includes('Livzon 范围同步失败'))!
  expect(syncNotice.querySelector('.ant-alert-description')).toBeNull()
  await act(async () => syncNotice.querySelector<HTMLButtonElement>('.ant-btn-link')!.click())
  expect(document.body.textContent).toContain('能力注册暂不可用')
})

it('confirms before discarding edits and blocks closing while saving', async () => {
  const onClose = vi.fn()
  let completeSave: (value: UserModulePermissionsOut) => void = () => {}
  mocks.replace.mockImplementationOnce(() => new Promise<UserModulePermissionsOut>((resolve) => { completeSave = resolve }))
  await show({ onClose })
  await act(async () => button('全部关闭').click())
  await act(async () => button('取消').click())
  expect(mocks.confirm.mock.lastCall![0].title).toContain('放弃未保存')
  expect(onClose).not.toHaveBeenCalled()
  await setReason('停用访问')
  await act(async () => button('保存').click())
  let pendingSave: Promise<void> | undefined
  await act(async () => { pendingSave = mocks.confirm.mock.lastCall![0].onOk() })
  expect(button('取消').disabled).toBe(true)
  expect(button('刷新').disabled).toBe(true)
  expect(button('预览权限').disabled).toBe(true)
  await act(async () => button('取消').click())
  expect(onClose).not.toHaveBeenCalled()
  const confirmationCount = mocks.confirm.mock.calls.length
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(onClose).not.toHaveBeenCalled()
  expect(mocks.confirm).toHaveBeenCalledTimes(confirmationCount)
  await act(async () => { completeSave({ ...result(), grants: [], grant_version: 5 }); await pendingSave })
  expect(button('取消').disabled).toBe(false)
  await act(async () => document.querySelector<HTMLElement>('.ant-drawer-mask')!.click())
  expect(onClose).toHaveBeenCalledOnce()
})
