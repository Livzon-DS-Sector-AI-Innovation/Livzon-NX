/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getSalesPlanDetails = vi.fn()

vi.mock('@/actions/production', () => ({
  getSalesPlanDetails: (...args: unknown[]) => getSalesPlanDetails(...args),
}))

import SalesPlanCard from './sales-plan-card'

const salesPayload = {
  code: 200,
  message: 'success',
  data: [
    {
      id: 'sp-mv',
      product_name: '美伐他汀',
      unit: 'KG',
      last_month_delivered_uninvoiced: null,
      month_planned_delivery: 32000,
      month_delivered_qty: 24000,
      undelivered_qty: 8000,
      // 完成率为飞书同步的百分数口径（源表 75 即 75%）
      delivery_completion_rate: 75,
      last_month_end_inventory: null,
      month_planned_capacity: null,
      month_end_inventory: -32000,
    },
    {
      id: 'sp-mc',
      product_name: '霉酚酸',
      unit: 'KG',
      last_month_delivered_uninvoiced: null,
      month_planned_delivery: 95670,
      month_delivered_qty: 95670,
      undelivered_qty: 0,
      delivery_completion_rate: 100,
      last_month_end_inventory: null,
      month_planned_capacity: null,
      month_end_inventory: -95670,
    },
    {
      id: 'sp-lm',
      product_name: '盐酸林可霉素',
      unit: '十亿',
      last_month_delivered_uninvoiced: null,
      month_planned_delivery: 6207.8,
      month_delivered_qty: 6207.8,
      undelivered_qty: 0,
      delivery_completion_rate: 100,
      last_month_end_inventory: null,
      month_planned_capacity: null,
      month_end_inventory: -6207.8,
    },
  ],
  meta: { total: 3 },
}

describe('SalesPlanCard', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    getSalesPlanDetails.mockReset()
    getSalesPlanDetails.mockResolvedValue(salesPayload)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function render(props: { month: string }) {
    act(() => {
      root.render(<SalesPlanCard month={props.month} />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
  }

  it('renders ten sales plan columns aligned with the summary table', async () => {
    await render({ month: '2026-09' })
    // 跟随概览月份取数
    expect(getSalesPlanDetails).toHaveBeenCalledWith({
      page: 1,
      page_size: 200,
      month: '2026-09',
    })
    const text = container.textContent || ''
    // 上下文行：数据月份（不含同步来源字样）
    expect(text).toContain('产销计划')
    expect(text).toContain('数据月份 2026-09')
    expect(text).not.toContain('飞书同步数据')
    for (const title of [
      '产品',
      '单位',
      '上月已发货未开票',
      '本月计划发货量',
      '本月已发货量',
      '未发货量',
      '本月发货完成率',
      '上月底库存',
      '本月预计产能',
      '本月底库存',
    ]) {
      expect(text).toContain(title)
    }
    // 空值与生产汇总表一致展示 --
    expect(text).toContain('--')
    // 完成率进度条：3 个产品行
    expect(container.querySelectorAll('[data-rate-bar]').length).toBe(3)
  })

  it('sorts rows to the shared product order and appends non-line products', async () => {
    await render({ month: '2026-09' })
    const text = container.textContent || ''
    // 固定行序与生产汇总表对齐：霉酚酸(MC) 在美伐他汀(MV) 之前
    expect(text.indexOf('霉酚酸')).toBeLessThan(text.indexOf('美伐他汀'))
    // 未收录产线（盐酸林可霉素）排在收录产线之后
    expect(text.indexOf('美伐他汀')).toBeLessThan(text.indexOf('盐酸林可霉素'))
  })

  it('shows the sync hint when the month has no data', async () => {
    getSalesPlanDetails.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [],
      meta: { total: 0 },
    })
    await render({ month: '2026-09' })
    expect((container.textContent || '')).toContain(
      '暂无销售计划数据，请先完成飞书同步设置并同步',
    )
  })

  it('shows a warning hint when the sales plan request fails', async () => {
    getSalesPlanDetails.mockRejectedValue(new Error('network down'))
    await render({ month: '2026-09' })
    expect((container.textContent || '')).toContain('销售计划数据加载失败')
  })
})
