/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getPageKeyByPath } from '@/lib/menu-config'
import { useAuthStore } from '@/stores/auth'

vi.mock('next/navigation', () => ({
  usePathname: () => '/quality/inspection/instruments/maintenance',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchInspectionFeishuFields: vi.fn(async () => ({
    fields: [{ field_name: '设备名称', ui_type: 'Text', editable: true }], can_push: true,
  })),
  fetchInspectionFeishuRecordDetail: vi.fn(),
}))
import { InspectionFeishuTable } from './InspectionFeishuTable'

let root: Root
let container: HTMLElement
const pageKey = getPageKeyByPath('/quality/inspection/instruments/maintenance')!
function authorize(operate: boolean, actions: string[] = []) {
  act(() => useAuthStore.getState().setUser({
    id: 'tester', name: '普通测试用户', role: 'user', permissions: ['*', 'quality:write'],
    page_permissions: [{ page_key: pageKey, module_code: 'quality',
      permissions: operate ? ['access', 'query', 'operate'] : ['access', 'query'],
      sensitive_actions: actions, data_scope: { scope_type: 'all' }, source: 'user' }],
  }))
}
function button(text: string) {
  const result = [...container.querySelectorAll('button')].find((item) => item.textContent?.trim() === text)
  expect(result, text).toBeTruthy()
  return result!
}
beforeEach(async () => {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    data: [{ record_id: 'row1', 设备名称: '测试仪器' }],
    meta: { total: 1, page: 1, page_size: 20, configured: true, fields: ['设备名称'] },
  }), { status: 200, headers: { 'content-type': 'application/json' } })))
  authorize(false)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root.render(<QueryClientProvider client={client}><App>
    <InspectionFeishuTable title="测试维护记录" listApi="/api/v1/quality/instruments/maintenance"
      entityCode="qc_instr_maintenance" pullApi="/api/v1/quality/instruments/maintenance/pull" editable />
  </App></QueryClientProvider>))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 60)) })
})
afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  useAuthStore.getState().clearUser()
  vi.unstubAllGlobals()
})
it('uses the current page grant for create/edit and separate delete/sync grants, including revocation', () => {
  for (const text of ['新增', '编辑', '删除', '同步飞书数据']) expect(button(text).disabled).toBe(true)
  expect(button('详情').disabled).toBe(false)
  authorize(true)
  expect(button('新增').disabled).toBe(false)
  expect(button('编辑').disabled).toBe(false)
  expect(button('删除').disabled).toBe(true)
  expect(button('同步飞书数据').disabled).toBe(true)
  authorize(true, ['delete', 'sync_config'])
  expect(button('删除').disabled).toBe(false)
  expect(button('同步飞书数据').disabled).toBe(false)
  authorize(false, ['delete', 'sync_config'])
  for (const text of ['新增', '编辑', '删除', '同步飞书数据']) expect(button(text).disabled).toBe(true)
  act(() => button('同步飞书数据').click())
  expect(vi.mocked(fetch).mock.calls.every(([url]) => !String(url).endsWith('/pull'))).toBe(true)
})
