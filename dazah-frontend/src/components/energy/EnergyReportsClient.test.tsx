/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import type { Report } from '@/lib/api/energy-ledger'

const state = vi.hoisted((): { report?: Report; error?: Error; search?: string; queries: string[][] } => ({ queries: [] }))

vi.mock('next/navigation', () => ({
  usePathname: () => '/energy/reports',
  useSearchParams: () => new URLSearchParams(state.search ?? 'year=2026&month=7&dataset=饮用水码'),
}))
vi.mock('@tanstack/react-query', () => ({ useQuery: ({ queryKey }: { queryKey: string[] }) => { state.queries.push(queryKey); return { data: ['overview', 'reports', 'analysis', 'data-quality'].includes(queryKey[1]) ? state.report : undefined, error: queryKey[1] === 'overview' ? state.error : undefined, isFetching: false } } }))
vi.mock('./EnergyWorkbookClient', () => ({ EnergyWorkbookClient: ({ dataset }: { dataset: string }) => <div>原表结果 · {dataset}</div> }))
vi.mock('@/components/shared/ThemedEChart', () => ({ default: () => null }))

import { EnergyReportsClient } from './EnergyReportsClient'

afterEach(() => { state.report = undefined; state.error = undefined; state.search = undefined; state.queries = []; document.body.innerHTML = ''; window.history.replaceState(null, '', '/') })

it.each([false, true])('explains empty reports without directing users to retired historical pages (dark=%s)', async dark => {
  state.report = { start_date: '2026-07-01', end_date: '2026-07-31', status: 'complete', rows: [], total_count: 0, entry_completed: 0, entry_total: 0, totals: [] }
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyReportsClient mode="analysis" /></App></ConfigProvider>))
  const notice = [...node.querySelectorAll('[role=alert]')].find(item => item.textContent?.includes('当前筛选范围没有可展示的能源结果'))
  expect(notice).toBeDefined()
  await act(async () => notice!.querySelector('button')!.click())
  const dialog = document.querySelector('[role=dialog]')!
  expect(dialog.textContent).toContain('请先配置并启用计量点、填报计划和计算关系')
  expect(dialog.textContent).not.toContain('历史来源')
  await act(async () => root.unmount())
})

it.each([false, true])('applies and resets client report filters without server navigation (dark=%s)', async dark => {
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyReportsClient mode="reports" /></App></ConfigProvider>))
  const labels = Array.from(node.querySelectorAll('label'))
  expect(labels.map(label => label.firstChild?.textContent?.trim())).toEqual(['年份', '月份', '数据表'])
  expect(labels[0].querySelector('[aria-label="年份"]')).not.toBeNull()
  expect(labels[1].querySelector('[aria-label="月份"]')).not.toBeNull()
  expect(labels[2].htmlFor).toBe('energy-report-dataset')
  expect(labels[2].querySelector('[aria-label="数据表"]')?.id).toBe('energy-report-dataset')
  const button = (label: string) => Array.from(node.querySelectorAll('button')).find(item => item.textContent?.replaceAll(' ', '') === label)
  await act(async () => button('查询')?.click())
  const params = new URLSearchParams(window.location.search)
  expect(params.get('dataset')).toBe('饮用水码')
  expect(params.get('year')).toBe('2026')
  expect(params.get('month')).toBe('7')
  expect(params.has('report_scope')).toBe(false)
  expect(params.has('page')).toBe(false)
  expect(node.textContent).toContain('原表结果')
  await act(async () => button('重置')?.click())
  expect(window.location.pathname).toBe('/energy/reports')
  expect(window.location.search).toBe('')
  await act(async () => root.unmount())
})

it.each(['overview', 'analysis', 'data-quality'] as const)('labels every %s filter and preserves submitted filter parameters', async mode => {
  for (const dark of [false, true]) {
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyReportsClient mode={mode} /></App></ConfigProvider>))
    const labels = Array.from(node.querySelectorAll('label'))
    expect(labels.map(label => label.firstChild?.textContent?.trim())).toEqual([
      '年份', '月份', ...(mode === 'analysis' ? ['单项指标'] : []),
      ...(mode !== 'data-quality' ? ['统计范围'] : []), '能源类别', '车间',
      ...(mode === 'data-quality' ? ['异常类型'] : []),
    ])
    for (const label of labels) {
      expect(label.htmlFor).toBeTruthy()
      expect(label.querySelector('input')?.id).toBe(label.htmlFor)
    }
    const workshop = node.querySelector<HTMLInputElement>('[aria-label="车间"]')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(workshop, '201车间')
      workshop.dispatchEvent(new Event('input', { bubbles: true }))
      workshop.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const query = Array.from(node.querySelectorAll('button')).find(button => button.textContent?.replaceAll(' ', '') === '查询')!
    await act(async () => query.click())
    const params = new URLSearchParams(window.location.search)
    expect(params.get('workshop')).toBe('201车间')
    expect(params.get('year')).toBe('2026')
    expect(params.get('month')).toBe('7')
    expect(params.get('report_scope')).toBe(mode === 'overview' ? 'plant' : 'detail')
    await act(async () => root.unmount()); node.remove()
  }
})

it('uses daily trend data for overview cards even without a shared complete date', async () => {
  const total = { category: 'electricity', unit: '原表数值单位', quantity_kind: 'electricity', temperature: '', value: '100', expected_count: 31, available_count: 1 } as const
  state.report = { start_date: '2026-07-01', end_date: '2026-07-31', status: 'partial', rows: [], total_count: 31, entry_completed: 0, entry_total: 0, totals: [total], trend: [{ ...total, usage_date: '2026-07-19', value: '0', expected_count: 1, available_count: 1 }], latest_complete_date: null }
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<App><EnergyReportsClient mode="overview" /></App>))
  const card = node.querySelector('[aria-label="电量用量摘要"]')!
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(node.textContent).not.toContain('了解访问规则')
  expect(card.textContent).toContain('用量日期 2026-07-19')
  expect(card.querySelector('.ant-statistic-content-value')?.textContent).toBe('0')
  expect(card.textContent).toContain('有效天数1 / 31 天')
  expect(card.textContent).toContain('原表数值单位')
  expect(node.querySelector('[aria-label="原始读数填报进度"]')).toBeNull()
  const trend = node.querySelector('[aria-label="电量用量趋势"]')!
  expect(trend.textContent).toContain('单位：千瓦时')
  expect(trend.textContent).toContain('有效 1 / 31 天')
  expect(trend.textContent).not.toContain('原表数值单位')
  expect(state.queries.some(key => key[1] === 'overview' && new URLSearchParams(key[2]).get('include_basis') === 'true')).toBe(true)
  await act(async () => root.unmount())
})

it('shows the overview request failure without inventing usage cards', async () => {
  state.error = new Error('能源报表暂不可用')
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<App><EnergyReportsClient mode="overview" /></App>))
  expect(node.textContent).toContain('能源报表暂不可用')
  expect(node.querySelector('[aria-label="原始读数填报进度"]')).toBeNull()
  await act(async () => root.unmount())
})

it.each([false, true])('hides daily usage details only in overview (dark=%s)', async dark => {
  state.search = 'year=2026&month=7&report_scope=plant'
  state.report = {
    start_date: '2026-07-01', end_date: '2026-07-31', status: 'partial', total_count: 1,
    entry_completed: 0, entry_total: 0, totals: [], trend: [],
    rows: [{ id: 'usage-1', metric_key: 'electricity-total', name: '电日用量明细', usage_date: '2026-07-31', department: '', workshop: '', category: 'electricity', temperature: '', unit: 'kWh', quantity_kind: 'electricity', report_scope: 'plant', calculated_value: null, effective_value: null, status: 'missing_dependency', provenance: {} }],
  }
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  for (const mode of ['reports', 'overview', 'analysis', 'data-quality'] as const) {
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyReportsClient key={mode} mode={mode} /></App></ConfigProvider>))
    if (mode === 'overview' || mode === 'reports') {
      expect(node.textContent).not.toContain('电日用量明细')
      expect(node.textContent).not.toContain('查看来源')
      expect(node.querySelector('table')).toBeNull()
      expect(node.querySelector('.ant-pagination')).toBeNull()
      expect(node.querySelector('[aria-label="原始读数填报进度"]')).toBeNull()
    } else {
      expect(node.textContent).toContain('电日用量明细')
      expect(node.textContent).toContain('查看来源')
      expect(node.querySelector('table')).not.toBeNull()
    }
  }
  await act(async () => root.unmount())
})

it.each(['year=2026&month=7&report_scope=plant', 'year=2026&month=7&dataset=&report_scope=detail'])('uses an original dataset for legacy aggregate links (%s)', async search => {
  state.search = search
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<App><EnergyReportsClient mode="reports" /></App>))
  expect(node.textContent).toContain('原表结果 · 日总量')
  expect(node.textContent).not.toContain('按统计范围汇总')
  expect(node.querySelector('[aria-label="统计范围"]')).toBeNull()
  expect(node.querySelector('[aria-label="能源类别"]')).toBeNull()
  expect(node.querySelector('[aria-label="车间"]')).toBeNull()
  const query = Array.from(node.querySelectorAll('button')).find(button => button.textContent?.replaceAll(' ', '') === '查询')
  await act(async () => query?.click())
  expect(new URLSearchParams(window.location.search).get('dataset')).toBe('日总量')
  expect(new URLSearchParams(window.location.search).has('report_scope')).toBe(false)
  await act(async () => root.unmount())
})


it.each([false, true])('keeps an empty overview free of notice boxes and entry progress (dark=%s)', async dark => {
  state.report = { start_date: '2026-07-01', end_date: '2026-07-31', status: 'pending', rows: [], total_count: 0, entry_completed: 11, entry_total: 11, totals: [] }
  const node = document.createElement('div'); document.body.append(node)
  const root = createRoot(node)
  await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyReportsClient mode="overview" /></App></ConfigProvider>))
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(node.textContent).not.toContain('了解访问规则')
  expect(node.querySelector('[aria-label="原始读数填报进度"]')).toBeNull()
  expect(node.textContent).not.toContain('已有值记录 / 已生成记录')
  expect(node.textContent).not.toContain('已有值占比')
  expect(node.querySelector('[aria-label="统计范围"]')).not.toBeNull()
  await act(async () => root.unmount())
})
