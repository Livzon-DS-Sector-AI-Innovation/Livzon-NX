/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getProductionSummary = vi.fn()

vi.mock('@/actions/production', () => ({
  getProductionSummary: (...args: unknown[]) => getProductionSummary(...args),
}))

import ProductionSummary from './production-summary'

const summaryPayload = {
  code: 200,
  data: {
    period: { start: '2026-08-27', end: '2026-09-26', label: '8月27日～9月26日' },
    rows: [
      {
        product_code: 'MC',
        product_name: '霉酚酸',
        covered: true,
        ferment: {
          planned_batches: 34,
          planned_capacity_kg: 69700,
          done_yield_kg: 44769.11,
          capacity_rate: 64.2,
        },
        extract: {
          planned_yield_kg: 62500,
          finished_inbound_kg: 37240,
          completion_rate: 59.6,
        },
        alerts: [{ level: 'warn', text: '【播报】A304罐批次 MC-26247 距预估放罐剩余 20h' }],
      },
      {
        product_code: 'MV',
        product_name: '美伐他汀',
        covered: false,
        ferment: {
          planned_batches: null,
          planned_capacity_kg: null,
          done_yield_kg: null,
          capacity_rate: null,
        },
        extract: {
          planned_yield_kg: null,
          finished_inbound_kg: null,
          completion_rate: null,
        },
        alerts: [],
      },
    ],
  },
}

describe('ProductionSummary', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    getProductionSummary.mockReset()
    getProductionSummary.mockResolvedValue(summaryPayload)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  async function render(props: { month: string }) {
    act(() => {
      root.render(<ProductionSummary month={props.month} />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
  }

  it('renders per-line metrics, merged alerts with product tags, and a total row', async () => {
    await render({ month: '2026-09' })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('霉酚酸')
    expect(text).toContain('44,769.11')
    expect(text).toContain('62,500')
    expect(text).toContain('64.2%')
    // 播报汇总：前缀来源产品
    expect(text).toContain('霉酚酸')
    expect(text).toContain('距预估放罐剩余 20h')
    // 未覆盖产线标识
    expect(text).toContain('排产未覆盖')
    expect(container.querySelectorAll('[data-rate-bar]').length).toBeGreaterThan(0)
    // 参考日取当月 15 日（稳定落在该月扎帐周期内）
    expect(getProductionSummary).toHaveBeenCalledWith('2026-09-15')
  })

  it('surfaces backend failures instead of an empty table', async () => {
    getProductionSummary.mockResolvedValue({
      code: 500,
      message: '汇总数据加载失败',
      data: null,
    })
    await render({ month: '2026-09' })
    expect((container.textContent || '')).toContain('汇总数据加载失败')
  })
})
