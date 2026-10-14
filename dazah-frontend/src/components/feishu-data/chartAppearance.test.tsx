/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import type { EChartsReactProps } from 'echarts-for-react'
import { AntdProvider } from '../AntdProvider'
import { TrendChart, DistributionChart, RankingChart } from './OverviewComponents'
const charts = vi.hoisted(() => ({ props: [] as EChartsReactProps[] }))
vi.mock('@/lib/useAppearance', () => ({ useAppearance: () => ({ resolved: 'dark' }) }))
vi.mock('echarts-for-react', () => ({ default: (props: EChartsReactProps) => {
  charts.props.push(props)
  return <div data-chart-theme={props.theme} />
} }))
it('renders business charts with dark tooltips and readable text, preserving the data', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<AntdProvider><TrendChart title="趋势" option={{ tooltip: {}, series: [{ type: 'line', data: [2, 5] }] }} /><DistributionChart title="分布" option={{ tooltip: {}, series: [{ type: 'pie', data: [{name:'合格',value:2}] }] }} /><RankingChart title="排行" option={{ tooltip: {}, series: [{ type: 'bar', data: [7] }] }} /></AntdProvider>))
    expect(host.querySelectorAll('[data-chart-theme="dark"]').length).toBe(3)
    for (const chart of charts.props) {
      expect(chart.option.tooltip.backgroundColor).toBe('#2b2b30')
      expect(chart.option.textStyle.color).toBe('#eeedf1')
      expect(chart.option.series.length).toBeGreaterThan(0)
    }
    expect(charts.props[0].option.series[0].data).toEqual([2, 5])
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
