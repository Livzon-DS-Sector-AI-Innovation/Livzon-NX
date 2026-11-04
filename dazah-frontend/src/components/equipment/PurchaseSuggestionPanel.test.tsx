/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchPurchaseSuggestionsClient: vi.fn(),
  submitPurchaseSuggestions: vi.fn(),
  updateSuggestionQty: vi.fn(),
  registerSuggestionArrival: vi.fn(),
  cancelPurchaseSuggestion: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchPurchaseSuggestionsClient: api.fetchPurchaseSuggestionsClient,
}))
vi.mock('@/actions/equipment', () => ({
  submitPurchaseSuggestions: api.submitPurchaseSuggestions,
  updateSuggestionQty: api.updateSuggestionQty,
  registerSuggestionArrival: api.registerSuggestionArrival,
  cancelPurchaseSuggestion: api.cancelPurchaseSuggestion,
}))

import { PurchaseSuggestionPanel } from './PurchaseSuggestionPanel'

const suggestions = [
  {
    id: 'sg-1',
    spare_part_id: 'sp-1',
    spare_part_code: 'SP-001',
    spare_part_name: '机械密封',
    specification: null,
    unit: '套',
    workshop_code: '201-1',
    default_supplier: null,
    current_qty: 2,
    safety_qty: 6,
    suggest_qty: 10,
    arrived_qty: 0,
    status: 'suggested' as const,
    source: 'auto',
    purchase_request_id: null,
    purchase_ref: null,
    unit_price: 150,
    submitted_at: null,
    created_at: '2026-11-03T07:30:00Z',
  },
  {
    id: 'sg-2',
    spare_part_id: 'sp-2',
    spare_part_code: 'SP-002',
    spare_part_name: '轴承',
    specification: null,
    unit: '个',
    workshop_code: '201-1',
    default_supplier: null,
    current_qty: 0,
    safety_qty: 4,
    suggest_qty: 8,
    arrived_qty: 3,
    status: 'partial' as const,
    source: 'auto',
    purchase_request_id: 'pr-1',
    purchase_ref: '采购申请 pr-1',
    unit_price: 80,
    submitted_at: '2026-11-01T10:00:00Z',
    created_at: '2026-10-31T07:30:00Z',
  },
]

describe('PurchaseSuggestionPanel', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchPurchaseSuggestionsClient.mockResolvedValue({
      items: suggestions,
      total: 2,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('renders suggestions with status tags, quantities and totals', async () => {
    act(() => {
      root.render(
        <AntApp>
          <PurchaseSuggestionPanel workshopCode="201-1" />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('机械密封')
    expect(text).toContain('待提交')
    expect(text).toContain('部分到货')
    expect(text).toContain('2 / 6')
    expect(text).toContain('共 2 条')
    // 待提交行可勾选，其他状态禁用
    const checkboxes = [
      ...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    ]
    expect(checkboxes.length).toBeGreaterThan(2)
    expect(checkboxes.some((c) => c.disabled)).toBe(true)
  })

  it('batch submits selected suggestions and reloads', async () => {
    api.submitPurchaseSuggestions.mockResolvedValue({
      submitted: 1,
      purchase_request_id: 'pr-new-1',
      failed: [],
    })
    act(() => {
      root.render(
        <AntApp>
          <PurchaseSuggestionPanel workshopCode="201-1" />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    // 勾选第一条（待提交）
    const cb = document.querySelectorAll<HTMLInputElement>(
      'input[type="checkbox"]',
    )[1]
    await act(async () => {
      cb.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    const submitBtn = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('提交采购'),
    ) as HTMLButtonElement
    expect(submitBtn).toBeTruthy()
    expect(submitBtn.textContent).toContain('1')
    await act(async () => {
      submitBtn.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(api.submitPurchaseSuggestions).toHaveBeenCalledWith(['sg-1'])
    expect(api.fetchPurchaseSuggestionsClient).toHaveBeenCalledTimes(2)
  })
})
