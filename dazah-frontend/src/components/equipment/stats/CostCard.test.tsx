/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchCostReportClient: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchCostReportClient: api.fetchCostReportClient,
}))

import { CostCard } from './CostCard'

const report = {
  month: '2026-11',
  workshop: null,
  group_by: 'equipment',
  totals: {
    orders: 5,
    spare_cost: 1200.5,
    labor_cost: 300,
    external_cost: 500,
    total_cost: 2000.5,
  },
  top: [
    {
      label: '离心泵A（LB-001）',
      orders: 3,
      spare_cost: 900,
      labor_cost: 200,
      external_cost: 0,
      total_cost: 1100,
    },
    {
      label: '压滤机B（LB-002）',
      orders: 2,
      spare_cost: 300.5,
      labor_cost: 100,
      external_cost: 500,
      total_cost: 900.5,
    },
  ],
}

describe('CostCard', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchCostReportClient.mockReset().mockResolvedValue(report)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('renders totals and top buckets with three cost segments', async () => {
    act(() => {
      root.render(<CostCard />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('维修成本')
    expect(text).toContain('2026-11 月')
    expect(text).toContain('¥2001') // 合计四舍五入
    expect(text).toContain('离心泵A（LB-001）')
    expect(text).toContain('压滤机B（LB-002）')
    // 三段成本列头
    expect(text).toContain('备件')
    expect(text).toContain('工时')
    expect(text).toContain('外委')
  })

  it('refetches with new group_by when segmented switches', async () => {
    act(() => {
      root.render(<CostCard />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(api.fetchCostReportClient).toHaveBeenCalledWith({ group_by: 'equipment' })

    const seg = [...document.querySelectorAll('.ant-segmented-item')].find((el) =>
      el.textContent?.includes('按车间'),
    ) as HTMLElement | undefined
    expect(seg).toBeTruthy()
    await act(async () => {
      seg!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(api.fetchCostReportClient).toHaveBeenCalledWith({ group_by: 'workshop' })
  })

  it('shows failure state without crashing', async () => {
    api.fetchCostReportClient.mockRejectedValue(new Error('network'))
    act(() => {
      root.render(<CostCard />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(document.body.textContent).toContain('成本报表加载失败')
  })
})
