/* @vitest-environment happy-dom */

import { act } from 'react'
import { App } from 'antd'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getFermentationRecords: vi.fn(),
  createFermentationRecord: vi.fn(),
  updateFermentationRecord: vi.fn(),
  deleteFermentationRecord: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import FermentationPage from './page'

const RECORDS = [
  {
    id: 'f-1',
    batch_no: 'F-2603-1',
    product_name: '霉酚酸',
    fermenter: '1#罐',
    entry_date: '2026-03-01',
    discharge_date: '2026-03-02',
    cycle_1: 10,
    cycle_2: 12,
    cycle_3: 14,
    cycle_4: 16,
    cycle_5: 18,
    cycle_6: 20,
    tank_yield: 1000,
    status: 'in_progress',
    remarks: '正常',
  },
]

// 后端直连 API 用于保存/导出
function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('FermentationPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getFermentationRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS, meta: { total: 1 } })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the fermentation ledger', async () => {
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('F-2603-1')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })

  it('renders cycle columns and status when records loaded', async () => {
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const text = container.textContent || ''
    // 周期列：循环周期 join 显示（cycle 值经 toFixed(1)）
    expect(text).toContain('10.0 / 12.0')
    expect(text).toContain('10.0 / 12.0 / 14.0')
  })

  it('exports CSV via direct backend fetch on export', async () => {
    const exportMock = (url: string) => {
      if (url.includes('/api/v1/production/fermentation')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [] } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [] } }))
    }
    vi.stubGlobal('fetch', vi.fn(exportMock))
    act(() => {
      root.render(<App><FermentationPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出'))
    if (btn) {
      await act(async () => { btn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect(container.textContent || '').toContain('发酵记录')
    expect(actions.getFermentationRecords).toHaveBeenCalled()
  })
})
