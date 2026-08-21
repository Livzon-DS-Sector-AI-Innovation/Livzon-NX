/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/SyncSettingsButton', () => ({
  default: () => <button>同步设置</button>,
}))

import PlanPage from './page'

const ROWS = [
  {
    id: 'sp-1',
    product_name: '霉酚酸',
    unit: 'kg',
    last_month_delivered_uninvoiced: 100,
    current_year_delivered: 500,
    month_planned_delivery: 600,
    month_delivered_qty: 300,
    undelivered_qty: 300,
    month_planned_invoice: 600,
    invoiced_qty: 280,
    delivery_completion_rate: 50,
    last_month_end_inventory: 50,
    month_planned_capacity: 700,
    month_end_inventory: 80,
    remarks: '',
  },
]

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('PlanPage', () => {
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

  it('renders the sales plan detail ledger', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('/sales-plan-details')
          ? Promise.resolve(jsonResponse({ code: 200, message: 'success', data: ROWS, meta: { total: 1 } }))
          : Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      )
    )

    act(() => {
      root.render(<PlanPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('生产计划')
    expect(text).toContain('产销计划')
  })
})
