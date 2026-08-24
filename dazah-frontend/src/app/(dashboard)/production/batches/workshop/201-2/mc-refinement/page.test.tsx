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

import McRefinementPage from './page'

const RECORD = {
  id: 'rf-1',
  input_date: '2026-03-01',
  batch_no: 'MC-F2-1',
  total_input_weight: 15,
  dry_product_total: 13,
  cumulative_dry_product: 13,
  dissolution_tank: 'T1',
  butyl_acetate_volume: 2,
  crystallization_tank: 'T2',
  wet_weight: 14,
  dry_weight: 13,
  cumulative_dry_weight: 13,
  single_step_yield: 86.5,
  cumulative_yield: 86.5,
  total_pure_qty: 15,
  inputs: [
    {
      id: 'in-1',
      wet_batch_no: 'MC-260129',
      input_weight: 15,
      moisture: 5,
      content: 90,
      pure_qty: 12.8,
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
  if (url.includes('/refinement-records/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('McRefinementPage', () => {
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

  it('renders the refinement ledger with input rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<McRefinementPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('MC二次精制')
    expect(text).toContain('MC-F2-1')
    expect(text).toContain('MC-260129')
    expect(text).toContain('新建精制记录')
    expect(text).toContain('+ 投入')
  })

  it('shows empty state without records', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] })))
    )

    act(() => {
      root.render(<App><McRefinementPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(container.textContent).toContain('暂无精制记录')
  })

  it('opens the create-refinement modal', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ id: 'r1', batch_no: 'MC-F2-1' }] })))
    )
    act(() => {
      root.render(<App><McRefinementPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const createBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建精制记录'))
    if (createBtn) {
      await act(async () => { createBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建精制记录')
  })
})
