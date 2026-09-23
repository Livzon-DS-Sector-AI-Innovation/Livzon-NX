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
  expect(container.textContent).not.toContain('新增台账')
  expect(useDeviationStore.getState().deviations).toEqual([])
})

it('keeps import restricted to administrators even with operate permission', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage()
  expect(container.textContent).not.toContain('导入')
})

it('keeps the local ledger columns and detail links independent of Feishu layouts', async () => {
  setGrant(['access', 'query'])
  mocks.fetchDeviations.mockResolvedValue({ items: [{
    id: 'local-record', deviation_code: 'PC-LOCAL', description: '本地调查记录',
    status: 'draft', corrective_actions: '详情中的措施',
  }], total: 1 })
  await renderPage()
  expect(Array.from(container.querySelectorAll('th')).map(node => node.textContent).filter(Boolean)).toEqual([
    '序号', '偏差编号', '产品名称/批号', '偏差简要描述', '偏差是否曾发生',
    '根本原因', '偏差等级', '调查完成时间', '操作',
  ])
  expect(container.textContent).toContain('PC-LOCAL')
  expect(container.textContent).not.toContain('详情中的措施')
  expect(container.querySelector('a[href="/quality/deviations/local-record"]')).not.toBeNull()
})

it('sends all visible filters and keeps read-only operations hidden', async () => {
  setGrant(['access', 'query'])
  useDeviationStore.getState().setStatusFilter('draft')
  useDeviationStore.getState().setLevelFilter('minor')
  useDeviationStore.getState().setDepartmentFilter('质量部')
  await renderPage()
  expect(mocks.fetchDeviations).toHaveBeenCalledWith(expect.objectContaining({ status: 'draft', level: 'minor', department: '质量部' }))
  for (const label of ['新增台账', '批量删除', '导入', '导出']) expect(container.textContent).not.toContain(label)
})

it('requires an independent export grant and sends the ledger context', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage()
  expect(container.textContent).toContain('新增台账')
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

it('titles the ledger page as 偏差台账', async () => {
  setGrant(['access', 'query'])
  await renderPage()
  expect(container.querySelector('h1')?.textContent).toBe('偏差台账')
})

it('downloads the ledger export under the ledger filename', async () => {
  setGrant(['access', 'query', 'operate'], ['sensitive_export'])
  await renderPage()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['ledger']) }))
  const originalCreate = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const originalRevoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:ledger'), configurable: true, writable: true })
  Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true, writable: true })
  const downloads: string[] = []
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click')
  clickSpy.mockImplementation(function (this: HTMLAnchorElement) { downloads.push(this.download) })
  try {
    const button = Array.from(container.querySelectorAll('button')).find((item) => item.textContent?.includes('导出'))
    await act(async () => button?.click())
  } finally {
    clickSpy.mockRestore()
    if (originalCreate) Object.defineProperty(URL, 'createObjectURL', originalCreate)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (originalRevoke) Object.defineProperty(URL, 'revokeObjectURL', originalRevoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
  }
  expect(downloads).toHaveLength(1)
  expect(downloads[0]).toMatch(/^偏差台账_\d{4}-\d{2}-\d{2}\.docx$/)
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
  for (const label of ['新增台账', '批量删除', '导入', '导出']) expect(container.textContent).toContain(label)
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

it('submits ledger fields without reporter and retains input after failed creation', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<CreateDeviation />)
  await act(async () => {
    setInput(container.querySelector('#affected_items')!, '产品批次')
    setInput(container.querySelector('#description')!, '偏差描述')
  })
  mocks.createDeviation.mockRejectedValueOnce(new Error('偏差内容不能为空'))
  const save = container.querySelector('button[type="submit"]') as HTMLButtonElement
  await act(async () => save.click())
  const payload = mocks.createDeviation.mock.calls[0][0]
  expect(payload).toMatchObject({ description: '偏差描述', affected_items: '产品批次', is_closed: false })
  expect(payload.reporter_open_id ?? null).toBeNull()
  expect(payload.department ?? null).toBeNull()
  expect((container.querySelector('#description') as HTMLTextAreaElement).value).toBe('偏差描述')
  expect(save.disabled).toBe(false)
  await act(async () => save.click())
  expect(mocks.createDeviation).toHaveBeenCalledTimes(2)
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

it('ordinary editing submits ledger close status without deletion rights', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<DeviationDetail />)
  expect(container.textContent).not.toContain('关闭状态由业务流程维护')
  expect(container.textContent).toContain('是否关闭')
  expect(container.textContent).not.toContain('删除')
  const save = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.replace(/\s/g, '') === '保存')
  await act(async () => save?.click())
  expect(mocks.updateDeviation).toHaveBeenCalledOnce()
  expect(mocks.updateDeviation.mock.calls[0][1]).toMatchObject({ is_closed: false, close_time: null })
})

it('registers the close date requirement and clears close state when reopened', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<DeviationDetail />)
  const save = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.replace(/\s/g, '') === '保存')

  const closedSelect = container.querySelector('#is_closed')!
  await act(async () => closedSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const yes = Array.from(document.querySelectorAll('.ant-select-item-option')).find((item) => item.textContent === '是')
  await act(async () => yes?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })

  // 已选关闭但未填关闭时间：校验拦截提交
  await act(async () => save?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  const closeTimeErrors = Array.from(container.querySelectorAll('.ant-form-item-explain-error'))
    .map((node) => node.textContent)
  expect(closeTimeErrors).toContain('请选择关闭时间')
  expect(mocks.updateDeviation).not.toHaveBeenCalled()

  // 取消关闭：关闭时间联动清空后可直接提交
  await act(async () => closedSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const no = Array.from(document.querySelectorAll('.ant-select-item-option')).find((item) => item.textContent === '否')
  await act(async () => no?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  await act(async () => save?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  expect(mocks.updateDeviation).toHaveBeenCalledOnce()
  expect(mocks.updateDeviation.mock.calls[0][1]).toMatchObject({ is_closed: false, close_time: null })
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

it('submits a manually filled deviation code on create', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<CreateDeviation />)
  await act(async () => {
    setInput(container.querySelector('#deviation_code')!, ' CS-TEST-01 ')
    setInput(container.querySelector('#affected_items')!, '产品批次')
    setInput(container.querySelector('#description')!, '偏差描述')
  })
  const save = container.querySelector('button[type="submit"]') as HTMLButtonElement
  await act(async () => save.click())
  expect(mocks.createDeviation).toHaveBeenCalledWith(expect.objectContaining({ deviation_code: 'CS-TEST-01' }))
})

it('submits a null deviation code when left blank on create', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<CreateDeviation />)
  await act(async () => {
    setInput(container.querySelector('#affected_items')!, '产品批次')
    setInput(container.querySelector('#description')!, '偏差描述')
  })
  const save = container.querySelector('button[type="submit"]') as HTMLButtonElement
  await act(async () => save.click())
  expect(mocks.createDeviation).toHaveBeenCalledWith(expect.objectContaining({ deviation_code: null }))
})

it('submits the edited deviation code from the detail form', async () => {
  setGrant(['access', 'query', 'operate'])
  await renderPage(<DeviationDetail />)
  await act(async () => setInput(container.querySelector('#deviation_code')!, 'PC-DETAIL-EDIT'))
  const save = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.replace(/\s/g, '') === '保存')
  expect(save).toBeDefined()
  await act(async () => save?.click())
  expect(mocks.updateDeviation).toHaveBeenCalledWith('record', expect.objectContaining({ deviation_code: 'PC-DETAIL-EDIT' }))
})
