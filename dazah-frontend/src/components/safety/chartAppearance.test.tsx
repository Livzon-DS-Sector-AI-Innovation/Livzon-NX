/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import type { EChartsReactProps } from 'echarts-for-react'
import { theme } from 'antd'
import { getAntdTheme } from '@/lib/antd-theme'
import { AntdProvider } from '../AntdProvider'
import { setAppearance } from '@/lib/useAppearance'
import PageFeishuStatsBar from './PageFeishuStatsBar'

const charts = vi.hoisted(() => ({ props: [] as EChartsReactProps[] }))
vi.mock('echarts-for-react', () => ({ default: (props: EChartsReactProps) => {
  charts.props.push(props)
  return <div data-chart-theme={props.theme || 'light'} />
} }))

it('switches all safety charts immediately and drills into the original month key', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const onSelect = vi.fn()
  await act(async () => setAppearance('light'))
  try {
    await act(async () => root.render(<AntdProvider><PageFeishuStatsBar onSelect={onSelect} stats={{
      page_key: 'safety:test', page_name: '验收数据', total: 12,
      groups: [
        { field: '日期', kind: 'date', mode: 'month', buckets: [{ key: '2025-07', count: 5 }, { key: '2026-07', count: 7 }] },
        { field: '车间', kind: 'text', mode: 'value', buckets: [{ key: '201-1', count: 12 }] },
        { field: '整改', kind: 'select', mode: 'value', buckets: [{ key: '已整改', count: 10 }, { key: '未整改', count: 2 }] },
      ],
    }} /></AntdProvider>))
    expect(host.querySelectorAll('[data-chart-theme="light"]')).toHaveLength(3)
    expect(charts.props[0].option.xAxis.data).toEqual(['2025年7月', '2026年7月'])
    charts.props[0].onEvents?.click({ name: '7月', dataIndex: 1 })
    expect(onSelect).toHaveBeenCalledWith('日期', '2026-07')
    charts.props.length = 0
    await act(async () => setAppearance('dark'))
    expect(host.querySelectorAll('[data-chart-theme="dark"]')).toHaveLength(3)
    const [month, workshop, status] = charts.props.slice(-3)
    expect(month.option.tooltip.backgroundColor).toBe('#2b2b30')
    const darkToken = theme.getDesignToken(getAntdTheme('dark'))
    expect(month.option.xAxis.axisLine.lineStyle.color).toBe(darkToken.colorBorder)
    expect(workshop.option.xAxis.splitLine.lineStyle.color).toBe(darkToken.colorBorderSecondary)
    expect(status.option.title.textStyle.color).toBe('#eeedf1')
    expect(status.option.series[0].data.map((item: { value: number }) => item.value)).toEqual([10, 2])
    await act(async () => setAppearance('light'))
    expect(host.querySelectorAll('[data-chart-theme="light"]')).toHaveLength(3)
    expect(charts.props.at(-1)?.option.title.textStyle.color).toBe(getAntdTheme('light').token?.colorText)
  } finally {
    await act(async () => root.unmount())
    host.remove()
    await act(async () => setAppearance('system'))
  }
})
