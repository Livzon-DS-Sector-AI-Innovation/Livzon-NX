/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/Dashboard', () => ({
  default: () => <div data-testid="dashboard" />,
}))
vi.mock('@/components/production/MCSheetsSyncButton', () => ({
  default: () => <button>同步</button>,
}))
vi.mock('@/components/production/MCTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import CrudeExtractionPage from './page'

const FULL_LIST_ITEM = {
  fermentation: { batch_no: 'MC-101-25202' },
  refining: {
    id: 'rb-1',
    batch_no: 'MC-251224',
    produce_date: '2026-03-01',
    workshop: '201-2',
    month: 3,
  },
  sub_tanks: [
    {
      sub_tank: {
        id: 'st-1',
        batch_no: 'MC-251224-1',
        fl_volume: 10,
        fl_potency: 5000,
        fl_product_qty: 50,
        total_input: 100,
        cumulative_qty: 100,
        crude_weight: 20,
        bag_weight: 10,
        crude_content: 90,
        crude_moisture: 5,
        crude_product_qty: 17.1,
        yield_rate: 92,
        cumulative_crude_qty: 20,
        cumulative_crude_yield: 92,
        remarks: '',
      },
      sodium_steps: [
        {
          id: 'na-1',
          na_before_volume: 10,
          na_after_volume: 9,
          na_potency: 6000,
          na_product_qty: 54,
          sodium_total: 54,
          ph_value: 7,
          alkali_usage: 1,
        },
      ],
      acid_steps: [
        {
          id: 'ac-1',
          acid_filter_volume: 8,
          acid_potency: 6000,
          acid_product_qty: 48,
          filter_subtotal: 48,
          ph_value: 6,
          acid_usage: 1,
          acid_filter_content: 90,
          filter_total: 48,
          na_to_fermentation_yield: 90,
          monthly_cumulative_yield: 90,
        },
      ],
    },
  ],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string) {
  if (url.includes('/crude-extract/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [FULL_LIST_ITEM] }))
  }
  if (url.includes('/crude-extract/fermentation-liquids')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ batch_no: 'MC-101-25202' }] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('CrudeExtractionPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders the ledger table with nested sub-tank rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<CrudeExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    // 导航与标题
    expect(text).toContain('粗提工段')
    expect(text).toContain('返回车间')
    // 批次与分罐数据渲染
    expect(text).toContain('MC-251224')
    expect(text).toContain('MC-101-25202')
    expect(text).toContain('MC-251224-1')
    // 新增按钮
    expect(text).toContain('新建发酵液')
    expect(text).toContain('新建提炼批次')
  })

  it('opens the create fermentation-liquid and refining-batch modals', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const flBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建发酵液'))
    if (flBtn) {
      await act(async () => { flBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建发酵液')
    const rbBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建提炼批次'))
    if (rbBtn) {
      await act(async () => { rbBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建提炼批次')
  })

  it('shows empty state when no batches exist', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('/crude-extract/full-list')
          ? Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
          : Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
      )
    )

    act(() => {
      root.render(<CrudeExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(container.textContent).toContain('暂无分罐数据')
  })
})
