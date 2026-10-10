/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/actions/hr', () => ({
  fetchOffboardingRecordsAction: vi.fn().mockRejectedValue(new Error('Minified React error #441')),
  deleteOffboardingRecord: vi.fn(),
  syncOffboardingFromFeishuAction: vi.fn(),
  updateOffboardingRecord: vi.fn(),
  generateOffboardingCertificateAction: vi.fn(),
}))
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({ canOperate: true, canDelete: false, canSync: false }),
}))
vi.mock('./OffboardingForm', () => ({ default: () => null }))
vi.mock('./OffboardingDetailDrawer', () => ({ default: () => null }))

import OffboardingClient from './OffboardingClient'
import { updateOffboardingRecord } from '@/actions/hr'
import type { OffboardingRecord } from '@/types/hr'

const record = { id: 'record-1', name: '测试员工', employee_number: 'TEST-001' } as OffboardingRecord
const response = (status: number, data: unknown = []) => new Response(
  JSON.stringify({ code: status, data, meta: { total: Array.isArray(data) ? data.length : 0 } }),
  { status, headers: { 'content-type': 'application/json' } },
)

describe('offboarding production reads', () => {
  let root: Root | undefined
  let container: HTMLElement

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  async function mount(initialRecords: OffboardingRecord[] = []) {
    window.history.replaceState(null, '', '/hr/offboarding')
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    await act(async () => root?.render(
      <App><OffboardingClient initialRecords={initialRecords} initialTotal={initialRecords.length} /></App>,
    ))
  }

  it('loads records through the authenticated API with actual page context', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200, [record]))
    vi.stubGlobal('fetch', fetchMock)
    await mount()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/hr/offboarding-records?page=1&page_size=20', {
      cache: 'no-store', headers: { 'X-Dazah-Page-Path': '/hr/offboarding' },
    })
    expect(container.textContent).toContain('TEST-001')
  })

  it('derives read-only employment status from the last working day instead of saved status', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 30, 23, 59, 59))
    const records = [
      { ...record, id: 'past', offboarding_date: '2026-09-29', status: '在职' },
      { ...record, id: 'today', offboarding_date: '2026-09-30', status: '离职' },
      { ...record, id: 'future', offboarding_date: '2026-10-01', status: '离职' },
      { ...record, id: 'missing', status: '离职' },
      { ...record, id: 'invalid', offboarding_date: '2026-02-30', status: '离职' },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, records)))
    await mount()
    const statusCell = (id: string) => container.querySelector(`tr[data-row-key="${id}"]`)?.querySelectorAll('td')[7]
    expect(statusCell('past')?.textContent).toBe('离职')
    expect(statusCell('today')?.textContent).toBe('在职')
    expect(statusCell('future')?.textContent).toBe('在职')
    expect(statusCell('missing')?.textContent).toBe('-')
    expect(statusCell('invalid')?.textContent).toBe('-')
    await act(async () => (statusCell('past')?.querySelector('.ant-tag') as HTMLElement)?.click())
    expect(statusCell('past')?.querySelector('.ant-select')).toBeNull()
    expect(updateOffboardingRecord).not.toHaveBeenCalled()
  })

  it('updates status across midnight while the page stays open and when focus returns', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date(2026, 8, 30, 23, 59, 30))
    const datedRecord = { ...record, offboarding_date: '2026-09-30', status: '离职' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(200, [datedRecord])))
    await mount()
    const statusCell = () => container.querySelector('tr[data-row-key="record-1"]')?.querySelectorAll('td')[7]
    expect(statusCell()?.textContent).toBe('在职')
    await act(async () => vi.advanceTimersByTime(60_000))
    expect(statusCell()?.textContent).toBe('离职')
    vi.setSystemTime(new Date(2026, 8, 30, 12))
    await act(async () => window.dispatchEvent(new Event('focus')))
    expect(statusCell()?.textContent).toBe('在职')
  })

  it('shows a persistent failure instead of empty data and recovers on retry', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(500)).mockResolvedValueOnce(response(200, [record]))
    vi.stubGlobal('fetch', fetchMock)
    await mount()
    expect(container.textContent).toContain('离职记录加载失败，请稍后重试')
    expect(container.textContent).not.toContain('暂无数据')
    expect(container.textContent).not.toContain('Minified React')
    const retry = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === '重试')
    expect(retry).toBeDefined()
    await act(async () => retry?.click())
    expect(container.textContent).toContain('TEST-001')
    expect(container.textContent).not.toContain('离职记录加载失败')
  })

  it.each([401, 403])('clears stale records and identifies access failure (%s)', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(status)))
    await mount([record])
    expect(container.textContent).toContain(status === 401 ? '登录已失效' : '没有执行此操作的权限')
    expect(container.textContent).not.toContain('TEST-001')
    expect(container.textContent).not.toContain('暂无数据')
  })

  it('retains last loaded records on temporary network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await mount([record])
    expect(container.textContent).toContain('网络连接失败')
    expect(container.textContent).toContain('TEST-001')
  })
})
