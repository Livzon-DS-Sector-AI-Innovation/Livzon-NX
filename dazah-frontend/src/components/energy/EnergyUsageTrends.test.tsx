/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import type { Report } from '@/lib/api/energy-ledger'

type Chart = {
  theme?: string
  option: {
    xAxis: { data: string[]; axisLabel: { formatter: (value: string) => string } }
    yAxis: { name: string; axisLabel: { formatter: (value: number) => string } }
    series: { data: (number | null)[]; connectNulls: boolean; showSymbol: boolean }[]
    tooltip: { formatter: (params: { dataIndex: number }[]) => string; renderMode: string }
  }
}
const state = vi.hoisted((): { dark: boolean; charts: Chart[] } => ({ dark: false, charts: [] }))
vi.mock('@/lib/useAppearance', () => ({ useAppearance: () => ({ resolved: state.dark ? 'dark' : 'light' }) }))
vi.mock('echarts-for-react', () => ({ default: (props: Chart) => { state.charts.push(props); return <div aria-label="趋势图画布" /> } }))

import { EnergyUsageTrends } from './EnergyUsageTrends'

const total: Report['totals'][number] = { category: 'electricity', unit: 'kWh', quantity_kind: 'electricity', temperature: '', value: '12345.5', expected_count: 3, available_count: 2 }
const report: Report = {
  start_date: '2026-07-01', end_date: '2026-07-03', status: 'partial', total_count: 3,
  entry_completed: 0, entry_total: 0, rows: [], totals: [total],
  trend: [
    { ...total, usage_date: '2026-07-03', value: '0', expected_count: 1, available_count: 1 },
    { ...total, usage_date: '2026-07-01', value: '12345.5', expected_count: 1, available_count: 1 },
    { ...total, usage_date: '2026-07-04', value: '999', expected_count: 1, available_count: 1 },
  ],
}

afterEach(() => { state.dark = false; state.charts = []; document.body.innerHTML = '' })

it('keeps daily gaps and zero usage readable when switching appearance', async () => {
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  for (const dark of [false, true, false]) {
    state.dark = dark
    state.charts = []
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyUsageTrends report={report} /></App></ConfigProvider>))
    const chart = state.charts.at(-1)!
    expect(chart.theme).toBe(dark ? 'dark' : undefined)
    expect(chart.option.xAxis.data).toEqual(['2026-07-01', '2026-07-02', '2026-07-03'])
    expect(chart.option.series[0].data).toEqual([12345.5, null, 0])
    expect(chart.option.series[0].connectNulls).toBe(false)
    expect(chart.option.series[0].showSymbol).toBe(true)
    expect(chart.option.xAxis.axisLabel.formatter('2026-07-01')).toBe('7/1')
    expect(chart.option.yAxis.name).toBe('kWh')
    expect(chart.option.yAxis.axisLabel.formatter(20000)).toBe('2万')
    expect(chart.option.tooltip.renderMode).toBe('richText')
    expect(chart.option.tooltip.formatter([{ dataIndex: 0 }])).toContain('12,345.5 kWh')
    expect(chart.option.tooltip.formatter([{ dataIndex: 1 }])).toContain('数据缺失或不完整')
    expect(chart.option.tooltip.formatter([{ dataIndex: 2 }])).toContain('0 kWh')
    expect(node.querySelector('[role=alert]')).toBeNull()
    expect(node.textContent).not.toContain('了解访问规则')
    expect(node.textContent).toContain('有效 2 / 3 天')
    expect(node.textContent).not.toContain('原表数值单位')
    const toggle = node.querySelector<HTMLElement>('.ant-collapse-header')!
    expect(toggle.textContent).toContain('查看每日数值')
    if (toggle.getAttribute('aria-expanded') === 'false') await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(node.querySelector('.ant-collapse dl')?.textContent).toContain('12,345.5 kWh')
    expect(node.querySelectorAll('.ant-collapse dl > div')).toHaveLength(3)
  }
  await act(async () => root.unmount())
})

it.each([false, true])('shows an explicit empty state for incomplete and invalid days (dark=%s)', async dark => {
  state.dark = dark
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  const emptyReport: Report = { ...report, trend: [
    { ...total, usage_date: '2026-07-01', value: '10', expected_count: 2, available_count: 1 },
    { ...total, usage_date: '2026-07-02', value: '0', expected_count: 0, available_count: 0 },
    { ...total, usage_date: '2026-07-03', value: null, expected_count: 1, available_count: 1 },
  ] }
  await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyUsageTrends report={emptyReport} /></App></ConfigProvider>))
  expect(node.textContent).toContain('有效 0 / 3 天')
  expect(node.textContent).toContain('所选期间暂无完整日用量')
  expect(node.querySelector('[aria-label="趋势图画布"]')).toBeNull()
  await act(async () => node.querySelector<HTMLElement>('.ant-collapse-header')!.click())
  expect(node.querySelectorAll('dd')).toHaveLength(3)
  expect(Array.from(node.querySelectorAll('dd')).every(item => item.textContent === '数据缺失或不完整')).toBe(true)
  await act(async () => root.unmount())
})

it('separates chilled water temperatures and statistical units', async () => {
  const cold: Report['totals'][number] = { ...total, category: 'chilled_water', quantity_kind: 'volume', temperature: '7℃' }
  const colder = { ...cold, temperature: '-5℃' }
  const otherUnit = { ...cold, unit: 'm³' }
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<App><EnergyUsageTrends report={{ ...report, totals: [cold, colder, otherUnit], trend: [
    { ...cold, usage_date: '2026-07-01', value: '100', expected_count: 1, available_count: 1 },
    { ...colder, usage_date: '2026-07-01', value: '200', expected_count: 1, available_count: 1 },
    { ...otherUnit, usage_date: '2026-07-01', value: '300', expected_count: 1, available_count: 1 },
  ] }} /></App>))
  expect(node.querySelector('[aria-label="冰水 7℃ · 口径 1用量趋势"]')).not.toBeNull()
  expect(node.querySelector('[aria-label="冰水 -5℃用量趋势"]')).not.toBeNull()
  expect(node.querySelector('[aria-label="冰水 7℃ · 口径 2用量趋势"]')).not.toBeNull()
  expect(state.charts.map(chart => chart.option.series[0].data[0])).toEqual([100, 200, 300])
  expect(state.charts.map(chart => chart.option.yAxis.name)).toEqual(['kWh', 'kWh', 'm³'])
  await act(async () => root.unmount())
})
