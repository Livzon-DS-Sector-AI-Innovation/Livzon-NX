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
