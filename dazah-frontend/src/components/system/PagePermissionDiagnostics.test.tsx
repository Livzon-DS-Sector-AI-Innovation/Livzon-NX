/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import type { ChangeEvent } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  users: vi.fn(), permissions: vi.fn(), simulate: vi.fn(),
  message: { error: vi.fn() },
}))
vi.mock('@/actions/users', () => ({
  getUsers: mocks.users, getUserPagePermissions: mocks.permissions,
}))
vi.mock('@/actions/admin', () => ({ simulatePagePermission: mocks.simulate }))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const Select = ({ options = [], placeholder, value, onChange, disabled }: {
    options?: Array<{ value: string; label: string }>
    placeholder?: string
    value?: string
    onChange?: (value: string) => void
    disabled?: boolean
  }) => createElement('select', {
    'aria-label': placeholder, value: value || '', disabled,
    onChange: (event: ChangeEvent<HTMLSelectElement>) => onChange?.(event.target.value),
  }, createElement('option', { value: '' }, placeholder),
  ...options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label)))
  return { ...actual, Select, App: { useApp: () => ({ message: mocks.message }) } }
})
import { PagePermissionDiagnostics } from './PagePermissionDiagnostics'

let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  mocks.users.mockResolvedValue({ items: [{ id: 'user-1', name: '张三', department: '质量部' }] })
  mocks.permissions.mockResolvedValue({ definitions: [{
    page_key: 'quality:deviation', module_code: 'quality', page_name: '偏差管理',
    route_path: '/quality/deviation', sensitive_actions: [],
  }] })
  mocks.simulate.mockResolvedValue({ allowed: true, reason: '当前账号具备权限', effective: {
    page_key: 'quality:deviation', module_code: 'quality', permissions: ['access', 'query'],
    sensitive_actions: [], data_scope: { scope_type: 'department_tree', department_ids: [] },
    source: 'role', source_role_names: ['质量审核员'],
    resolution: ['合并 2 个角色的授权：权限和高风险动作取并集，数据范围按最大可见范围合并'],
    role_sources: [{ role_id: 'role-1', role_name: '质量审核员', permissions: ['access', 'query'],
      sensitive_actions: [], data_scope: { scope_type: 'department_tree', department_ids: [] } }],
  } })
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function flush() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
}

it('diagnoses effective permission with source and data scope', async () => {
  await act(async () => root.render(createElement(PagePermissionDiagnostics)))
  await flush()
  const user = document.querySelector<HTMLSelectElement>('select[aria-label="选择用户"]')!
  await act(async () => { user.value = 'user-1'; user.dispatchEvent(new Event('change', { bubbles: true })) })
  await flush()
  const page = document.querySelector<HTMLSelectElement>('select[aria-label="选择菜单页面"]')!
  await act(async () => { page.value = 'quality:deviation'; page.dispatchEvent(new Event('change', { bubbles: true })) })
  const button = [...document.querySelectorAll('button')].find((item) => item.textContent?.includes('验证当前权限'))!
  await act(async () => button.click())
  await flush()
  expect(mocks.simulate).toHaveBeenCalledWith({
    user_id: 'user-1', page_key: 'quality:deviation', permission: 'query', sensitive_action: null,
  })
  expect(document.body.textContent).toContain('允许执行')
  expect(document.body.textContent).toContain('角色：质量审核员')
  expect(document.body.textContent).toContain('数据范围：本部门及下级')
  expect(document.body.textContent).toContain('判定过程')
  expect(document.body.textContent).toContain('角色贡献')
  expect(document.body.textContent).toContain('合并 2 个角色')
})
