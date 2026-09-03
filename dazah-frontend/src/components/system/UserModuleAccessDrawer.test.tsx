/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { UserModulePermissionsOut } from '@/actions/users'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  replace: vi.fn(),
  confirm: vi.fn(),
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
      useApp: () => ({ message: mocks.message, modal: { confirm: mocks.confirm } }),
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

async function show() {
  await act(async () => {
    root.render(createElement(UserModuleAccessDrawer, {
      user: {
        id: '00000000-0000-0000-0000-000000000001',
        name: '测试用户',
        isSystemAdmin: false,
      },
      open: true,
      onClose: vi.fn(),
    }))
  })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

function button(label: string) {
  const found = [...document.querySelectorAll('button')].find(
    (node) => node.textContent?.replace(/\s/g, '') === label
  )
  expect(found, label).toBeTruthy()
  return found!
}

it('adds module access while preserving existing advanced permissions and data scope', async () => {
  await show()
  expect(document.body.textContent).toContain('测试用户的模块访问权限')
  expect(document.body.textContent).toContain('模块内页面和操作权限仍由已分配角色决定')

  const qualityRow = [...document.querySelectorAll('tr')].find((row) => row.textContent?.includes('质量管理'))
  const qualityCheckbox = qualityRow?.querySelector<HTMLInputElement>('input[type="checkbox"]')
  expect(qualityCheckbox).toBeTruthy()
  await act(async () => qualityCheckbox!.click())

  const reason = document.querySelector<HTMLInputElement>('input[placeholder="填写模块访问调整原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(reason, '岗位职责调整')
    reason.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('预览并保存').click())
  expect(mocks.confirm).toHaveBeenCalledWith(expect.objectContaining({
    content: expect.stringContaining('新增 1 个模块访问入口'),
  }))
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
  expect(mocks.message.success).toHaveBeenCalledWith('模块访问权限已保存')
})

it('requires an audit reason before saving access changes', async () => {
  await show()
  await act(async () => button('全部关闭').click())
  await act(async () => button('预览并保存').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请填写本次模块访问调整原因')
  expect(mocks.confirm).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
})
