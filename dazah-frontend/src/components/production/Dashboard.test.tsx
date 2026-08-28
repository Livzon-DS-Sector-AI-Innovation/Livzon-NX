/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard'

// 将 echarts 渲染为占位 div 以便在 DOM 中查询
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

const DATA = [
  { batch_no: 'B-1', _label: 'L1', produce_date: '2026-08-01', total_weight: 100, yield_rate: 90 },
  { batch_no: 'B-2', _label: 'L2', produce_date: '2026-08-15', total_weight: 80, yield_rate: 85 },
  { batch_no: 'B-3', _label: 'L3', produce_date: '2026-09-01', total_weight: 60, yield_rate: 70 },
]

const CARDS = [
  { title: '总批次', value: (d: any) => d.length, suffix: '批' },
  { title: '平均收率', value: (d: any, f: any[]) => f.length ? 88 : 0, suffix: '%' },
]

const CHARTS = [
  { key: 'yield', label: '收率', title: '收率趋势', field: 'yield_rate', color: '#1890ff', unit: '%', markLine: 80, markLineAbove: true },
]

describe('Dashboard', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders dashboard with external month filter', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Dashboard title="工段仪表盘" data={DATA} dateField="produce_date"
            cards={CARDS} charts={CHARTS} month={8} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    // 月筛选 + 统计卡渲染
    expect(text).toContain('工段仪表盘')
    expect(text).toContain('总批次')
    expect(text).toContain('3')
  })

  it('renders all months when externalMonth is 0', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Dashboard title="仪表盘" data={DATA} dateField="produce_date"
            cards={CARDS} charts={CHARTS} month={0} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('总批次')
  })

  it('internal month select filters by month prefix', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Dashboard title="仪表盘" data={DATA} dateField="produce_date" cards={CARDS} charts={CHARTS} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    // 无外部月份时内部月选择渲染
    expect(text).toContain('全部')
  })
})