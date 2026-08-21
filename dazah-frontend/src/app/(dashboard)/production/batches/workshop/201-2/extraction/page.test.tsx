/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
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

import ExtractionPage from './page'

const RECORD = {
  id: 'ex-1',
  extract_date: '2026-03-01',
  batch_no: 'MC-260129',
  filter_potency: 6000,
  filter_volume: 8,
  filter_product_qty: 48,
  carbon_usage: 2,
  wet_weight: 18,
  wet_content: 90,
  dry_loss: 5,
  dry_weight: 15.39,
  total_converted_qty: 50,
  total_crude_weight: 20,
  yield_rate: 88.5,
  inputs: [
    {
      id: 'in-1',
      crude_batch_no: 'MC-101-1',
      crude_weight: 20,
      crude_moisture: 5,
      crude_content: 90,
      converted_qty: 17.1,
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
  if (url.includes('/extraction-records/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('ExtractionPage', () => {
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

  it('renders the extraction ledger with input rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<ExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('提取工段')
    expect(text).toContain('MC-260129')
    expect(text).toContain('MC-101-1')
    expect(text).toContain('新建提取记录')
    expect(text).toContain('+ 粗品投入')
  })

  it('shows empty state without records', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] })))
    )

    act(() => {
      root.render(<ExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(container.textContent).toContain('暂无提取记录')
  })
})
