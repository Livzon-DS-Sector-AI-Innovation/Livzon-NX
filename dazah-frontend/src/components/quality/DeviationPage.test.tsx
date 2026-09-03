/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'
import { useDeviationStore } from '@/stores/quality'
import { getPageKeyByPath } from '@/lib/menu-config'
import { DEVIATION_LEDGER_PAGE } from './useDeviationPermissions'

const mocks = vi.hoisted(() => ({ fetchDeviations: vi.fn(), fetchDeviation: vi.fn(), updateDeviation: vi.fn(), createDeviation: vi.fn(), fetchReporters: vi.fn(), batchDelete: vi.fn() }))
vi.mock('@/lib/api/client/deviation-reporters', () => ({ fetchDeviationReporters: mocks.fetchReporters }))
vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'record' }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/api/client/quality', () => ({ fetchDeviations: mocks.fetchDeviations, fetchDeviation: mocks.fetchDeviation }))
vi.mock('@/actions/quality-deviation', () => ({ createDeviation: mocks.createDeviation, deleteDeviation: vi.fn(), batchDeleteDeviations: mocks.batchDelete, updateDeviation: mocks.updateDeviation }))
vi.mock('./DeviationImportDrawer', () => ({ DeviationImportDrawer: () => null }))
import { DeviationPage } from './DeviationPage'
import { DeviationDetail } from './DeviationDetail'
import { CreateDeviation } from './CreateDeviation'

let root: Root
let container: HTMLDivElement
let client: QueryClient

function setGrant(permissions: Array<'access' | 'query' | 'operate'>, actions: string[] = [], role = 'user') {
  useAuthStore.getState().setUser({ id: 'ledger-reader', name: '台账用户', role,
    page_permission_rollouts: { quality: 'enforced' },
    page_permissions: [{ page_key: DEVIATION_LEDGER_PAGE, module_code: 'quality', permissions,
      sensitive_actions: actions, data_scope: { scope_type: 'all', department_ids: [] }, source: 'user' }],
  })
}

beforeEach(() => {
  mocks.fetchDeviations.mockReset().mockResolvedValue({ items: [], total: 0 })
  mocks.fetchDeviation.mockReset().mockResolvedValue({ id: 'record', deviation_code: 'PC-DETAIL', status: 'draft', has_occurred_before: false })
  mocks.updateDeviation.mockReset().mockResolvedValue({ success: true })
  mocks.createDeviation.mockReset().mockResolvedValue({ id: 'created' })
  mocks.fetchReporters.mockReset().mockResolvedValue({ data: [{ open_id: 'reporter-id', name: '王报告', department: '质量部' }], meta: { total: 1 } })
  mocks.batchDelete.mockReset().mockResolvedValue({ deleted: 2, failed: [] })
  useDeviationStore.getState().resetFilters()
  useDeviationStore.getState().setDeviations([])
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  useAuthStore.getState().clearUser()
  vi.unstubAllGlobals()
})

async function renderPage(component: React.ReactNode = <DeviationPage />) {
  await act(async () => root.render(<App><QueryClientProvider client={client}>{component}</QueryClientProvider></App>))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
}

it('does not request or retain data with access-only permission', async () => {
  setGrant(['access'])
  await renderPage()
  expect(container.textContent).toContain('尚未获得查询数据权限')
  expect(mocks.fetchDeviations).not.toHaveBeenCalled()
  expect(container.textContent).not.toContain('新建偏差')
  expect(useDeviationStore.getState().deviations).toEqual([])
})

it('sends all visible filters and keeps read-only operations hidden', async () => {
  setGrant(['access', 'query'])
  useDeviationStore.getState().setStatusFilter('draft')
  useDeviationStore.getState().setLevelFilter('minor')
  useDeviationStore.getState().setDepartmentFilter('质量部')
  await renderPage()
  expect(mocks.fetchDeviations).toHaveBeenCalledWith(expect.objectContaining({ status: 'draft', level: 'minor', department: '质量部' }))
  for (const label of ['新建偏差', '批量删除', '导入', '导出']) expect(container.textContent).not.toContain(label)
})

it('requires an independent export grant and sends the ledger context', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage()
  expect(container.textContent).toContain('新建偏差')
  expect(container.textContent).not.toContain('导出')
  await act(async () => setGrant(['access', 'query', 'operate'], ['sensitive_export']))
  const fetch = vi.fn().mockResolvedValue({ ok: false })
  vi.stubGlobal('fetch', fetch)
  const button = Array.from(container.querySelectorAll('button')).find((item) => item.textContent?.includes('导出'))
  expect(button).toBeDefined()
  await act(async () => button?.click())
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/deviations/export?'), { headers: { 'X-Dazah-Page-Key': DEVIATION_LEDGER_PAGE } })
  expect(container.textContent).not.toContain('批量删除')
  expect(container.textContent).not.toContain('导入')
})

it('clears cached rows after query permission is revoked', async () => {
  setGrant(['access', 'query'])
  mocks.fetchDeviations.mockResolvedValue({ items: [{ id: 'record', deviation_code: '撤销后不可见', title: '记录', status: 'draft' }], total: 1 })
  await renderPage()
  expect(container.textContent).toContain('撤销后不可见')
  await act(async () => setGrant(['access']))
  expect(container.textContent).not.toContain('撤销后不可见')
  expect(useDeviationStore.getState().deviations).toEqual([])
})

it('system administrators retain every operation', async () => {
  setGrant([], [], 'admin')
  await renderPage()
  for (const label of ['新建偏差', '批量删除', '导入', '导出']) expect(container.textContent).toContain(label)
})

it('refetches when the authorization version changes without different grant content', async () => {
  setGrant(['access', 'query'])
  await renderPage()
  expect(mocks.fetchDeviations).toHaveBeenCalledOnce()
  await act(async () => useAuthStore.getState().setUser({ ...useAuthStore.getState().user!, grant_version: 2 }))
  expect(mocks.fetchDeviations).toHaveBeenCalledTimes(2)
})

it('maps only reviewed auxiliary URLs to the ledger', () => {
  expect(getPageKeyByPath('/quality/deviations/new')).toBe(DEVIATION_LEDGER_PAGE)
  expect(getPageKeyByPath('/quality/deviations/00000000-0000-0000-0000-000000000001')).toBe(DEVIATION_LEDGER_PAGE)
  expect(getPageKeyByPath('/quality/deviations/records')).toBe('quality:deviations:deviation-records')
  expect(getPageKeyByPath('/quality/deviations/00000000-0000-0000-0000-000000000001/ai')).not.toBe(DEVIATION_LEDGER_PAGE)
})

it('does not fetch a detail without query permission', async () => {
  setGrant(['access'])
  await renderPage(<DeviationDetail />)
  expect(container.textContent).toContain('尚未获得偏差台账查询权限')
  expect(mocks.fetchDeviation).not.toHaveBeenCalled()
})

it('does not expose a creation form through a read-only direct URL', async () => {
  setGrant(['access', 'query'])
  await renderPage(<CreateDeviation />)
  expect(container.textContent).toContain('尚未获得新增偏差记录的操作权限')
  expect(container.querySelector('form')).toBeNull()
  expect(mocks.fetchReporters).not.toHaveBeenCalled()
})

function setInput(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, value)
  element.dispatchEvent(new Event('input', { bubbles: true }))
}

it('selects a reporter, derives department and retains input after failed creation', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<CreateDeviation />)
  const selector = container.querySelector('#reporter_open_id')!
  await act(async () => selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find((item) => item.textContent?.includes('王报告'))
  expect(option).toBeDefined()
  await act(async () => option?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  expect((container.querySelector('#department') as HTMLInputElement).value).toBe('质量部')
  await act(async () => {
    setInput(container.querySelector('#affected_items')!, '产品批次')
    setInput(container.querySelector('#description')!, '偏差描述')
  })
  mocks.createDeviation.mockRejectedValueOnce(new Error('报告人部门已变化，请重新选择'))
  const save = container.querySelector('button[type="submit"]') as HTMLButtonElement
  await act(async () => save.click())
  expect(mocks.createDeviation).toHaveBeenCalledWith(expect.objectContaining({ reporter_open_id: 'reporter-id', department: '质量部', description: '偏差描述', is_closed: false }))
  expect((container.querySelector('#description') as HTMLTextAreaElement).value).toBe('偏差描述')
  expect(save.disabled).toBe(false)
  await act(async () => save.click())
  expect(mocks.createDeviation).toHaveBeenCalledTimes(2)
})

it('shows reporter load failures and supports retry', async () => {
  setGrant(['access', 'query', 'operate'])
  mocks.fetchReporters.mockRejectedValueOnce(new Error('报告人目录暂不可用'))
  await renderPage(<CreateDeviation />)
  expect(container.textContent).toContain('报告人目录暂不可用')
  expect((container.querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(true)
  const retry = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.replace(/\s/g, '') === '重试')
  await act(async () => retry?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
  expect(mocks.fetchReporters).toHaveBeenCalledTimes(2)
  expect(container.textContent).not.toContain('报告人目录暂不可用')
})

it('allows batch deletion only after explicit confirmation and retains selection on failure', async () => {
  setGrant(['access', 'query', 'operate'], ['delete'])
  mocks.fetchDeviations.mockResolvedValue({ items: [{ id: 'a', deviation_code: 'PC-A', status: 'draft' }, { id: 'b', deviation_code: 'PC-B', status: 'draft' }], total: 2 })
  await renderPage()
  await act(async () => (container.querySelector('thead input[type="checkbox"]') as HTMLInputElement).click())
  const batch = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('批量删除'))!
  await act(async () => batch.click())
  expect(document.body.textContent).toContain('本批不会删除任何记录')
  expect(mocks.batchDelete).not.toHaveBeenCalled()
  mocks.batchDelete.mockRejectedValueOnce(new Error('所选偏差记录已删除，整批未执行'))
  const confirm = Array.from(document.querySelectorAll('.ant-modal button')).find((button) => button.textContent?.replace(/\s/g, '') === '确认') as HTMLButtonElement
  await act(async () => confirm.click())
  expect(mocks.batchDelete).toHaveBeenCalledWith(['a', 'b'])
  expect((container.querySelector('thead input[type="checkbox"]') as HTMLInputElement).checked).toBe(true)
  expect(mocks.fetchDeviations).toHaveBeenCalledOnce()
})

it('renders read-only details without save or delete actions', async () => {
  setGrant(['access', 'query'])
  await renderPage(<DeviationDetail />)
  expect(container.textContent).toContain('偏差台账详情（只读）')
  expect(container.textContent).not.toContain('保存')
  expect(container.textContent).not.toContain('删除')
  expect(Array.from(container.querySelectorAll('textarea')).every((input) => input.disabled)).toBe(true)
})

it('ordinary editing never submits workflow state or grants deletion', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<DeviationDetail />)
  expect(container.textContent).toContain('关闭状态由业务流程维护')
  expect(container.textContent).not.toContain('删除')
  const save = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.replace(/\s/g, '') === '保存')
  await act(async () => save?.click())
  expect(mocks.updateDeviation).toHaveBeenCalledOnce()
  expect(mocks.updateDeviation.mock.calls[0][1]).not.toHaveProperty('status')
})

it('does not seed a new authorization version with stale server detail props', async () => {
  setGrant(['access', 'query'])
  const initial = { id: 'record', deviation_code: '旧范围详情', status: 'draft', has_occurred_before: false }
  mocks.fetchDeviation.mockResolvedValue(initial)
  await renderPage(<DeviationDetail initialDeviation={initial as NonNullable<NonNullable<React.ComponentProps<typeof DeviationDetail>>['initialDeviation']>} />)
  expect(container.textContent).toContain('旧范围详情')
  mocks.fetchDeviation.mockImplementation(() => new Promise(() => {}))
  await act(async () => useAuthStore.getState().setUser({ ...useAuthStore.getState().user!, grant_version: 3 }))
  expect(container.textContent).not.toContain('旧范围详情')
  expect(container.textContent).toContain('加载中')
})
