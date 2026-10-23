/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import type { Report, WorkbookDataset, WorkbookReport } from '@/lib/api/energy-ledger'

const state = vi.hoisted(() => ({ failure: '', dark: false, pending: false, review: false }))
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams('year=2026&month=7') }))
vi.mock('@/lib/useAppearance', () => ({ useAppearance: () => ({ resolved: state.dark ? 'dark' : 'light' }) }))
vi.mock('echarts-for-react', () => ({ default: ({ option, theme: appearance }: { option: { series?: { type: string }[] }; theme?: string }) => <div data-chart={option.series?.[0]?.type} data-theme={appearance || 'light'} /> }))
vi.mock('@/lib/api/energy-ledger', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api/energy-ledger')>()
  return { ...original, ledgerRequest: vi.fn(async (path: string) => {
    if (state.pending) return new Promise(() => {})
    if (state.failure && path.includes(state.failure)) throw new Error('无权查看当前表')
    if (path === '/reporting/datasets') return datasets
    if (path.startsWith('/reporting/workbook?')) return workbook(new URLSearchParams(path.split('?')[1]).get('dataset')!)
    return state.review ? { ...report, quality_counts: { pending_review: 1 } } : report
  }) }
})
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergyDashboard } from './EnergyDashboard'

const datasets: WorkbookDataset[] = [
  ...['饮用水码', '冰水码', '蒸汽码', '循环水码', '空气码'].map(name => ({ name, kind: 'reading' as const })),
  { name: '电量', kind: 'mixed' },
  ...['饮用水量', '蒸汽量', '冰水量', '空气量', '循环水量', '日总量', '101车间', '102-1车间', '103-1车间', '103-2车间', '201-1车间', '201-2车间', '203-1车间', '203-2车间', '203-3车间'].map(name => ({ name, kind: 'usage' as const })),
]
function workbook(dataset: string): WorkbookReport {
  return { dataset, year: 2026, month: 7, available_count: 31, expected_count: 31,
    columns: [{ key: '2', label: '用量', unit: '万m³', quantity_kind: 'volume', value_kind: dataset.endsWith('码') ? 'reading' : 'usage' }, { key: '3', label: '热量', unit: 'GJ', quantity_kind: 'heat', value_kind: 'usage' }],
    rows: Array.from({ length: 31 }, (_, index) => ({ date: `2026-07-${String(index + 1).padStart(2, '0')}`, cells: { '2': state.review && index === 25 ? { value: null, calculated_value: '2049315', status: 'pending_review', provenance: { review: [{ reason: '底码跳变与手填冲突', source: '飞书N31', reported_value: '28674' }] } } : { value: String(index), status: 'complete' }, '3': { value: null, status: 'missing_reading' } } })),
  }
}
const total = { category: 'drinking_water' as const, unit: '万m³', quantity_kind: 'volume', temperature: '', value: '465', available_count: 31, expected_count: 31 }
const report: Report = { start_date: '2026-07-01', end_date: '2026-07-31', status: 'complete', total_count: 31, entry_total: 0, entry_completed: 0, rows: [], totals: [total], trend: [{ ...total, usage_date: '2026-07-31' }], distribution: [{ ...total, workshop: '101车间' }] }
let root: Root | undefined
let client: QueryClient
afterEach(async () => { await act(async () => root?.unmount()); client?.clear(); document.body.replaceChildren(); vi.clearAllMocks(); state.failure = ''; state.pending = false; state.review = false; window.history.replaceState(null, '', '/') })
async function settle() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 70)) }) }
async function mount(dark = false) {
  state.dark = dark
  const host = document.createElement('div'); document.body.append(host)
  root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => root!.render(<QueryClientProvider client={client}><ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyDashboard /></App></ConfigProvider></QueryClientProvider>))
  await settle(); await settle()
  return host
}
it.each([false, true])('covers all 21 sheets, loads each group on demand and renders charts in both modes (dark=%s)', async dark => {
  const host = await mount(dark)
  expect(host.textContent).toContain('21 张能源数据表')
  expect(host.textContent).toContain('原始表码 → 分类用量 → 日总量／车间台账')
  expect(host.textContent).toContain('同口径车间用量对比')
  expect(host.textContent).toContain('万m³')
  const tabs = [...host.querySelectorAll<HTMLElement>('[role=tab]')]
  expect(tabs.map(tab => tab.textContent)).toEqual(['日总量（1）', '分类用量（5）', '车间台账（9）', '原始数据（6）'])
  for (const tab of tabs) { await act(async () => tab.click()); await settle(); await settle() }
  const paths = vi.mocked(ledgerRequest).mock.calls.map(([path]) => path).filter(path => path.startsWith('/reporting/workbook?'))
  expect(new Set(paths.map(path => new URLSearchParams(path.split('?')[1]).get('dataset'))).size).toBe(21)
  const charts = host.querySelectorAll('[data-chart]')
  expect(charts.length).toBeGreaterThan(2)
  expect([...charts].every(chart => chart.getAttribute('data-theme') === (dark ? 'dark' : 'light'))).toBe(true)
  expect(host.querySelectorAll('[data-chart=pie]')).toHaveLength(1) // only the workshop partition; counters have no share
  const query = [...host.querySelectorAll('button')].find(button => button.textContent?.replaceAll(' ', '') === '查询')!
  await act(async () => query.click())
  expect(window.location.search).toBe('?year=2026&month=7')
})
it('keeps successful regions when a workbook fails and offers a working retry', async () => {
  state.failure = '/reporting/workbook?'
  const host = await mount()
  expect(host.textContent).toContain('日总量：无权查看当前表')
  expect(host.textContent).toContain('同口径车间用量对比')
  state.failure = ''
  const retry = [...host.querySelectorAll('button')].find(button => button.textContent?.replaceAll(' ', '') === '重试')!
  await act(async () => retry.click()); await settle(); await settle()
  expect(host.textContent).not.toContain('日总量：无权查看当前表')
  expect(host.textContent).toContain('月内每日贡献占比')
})
it('shows loading placeholders without fabricating values', async () => {
  state.pending = true
  const host = await mount()
  expect(host.querySelector('.ant-skeleton')).not.toBeNull()
  expect(host.querySelector('[data-chart]')).toBeNull()
})
it('switches independent fields and shows missing heat values without retaining the previous volume chart', async () => {
  const host = await mount()
  const field = host.querySelector<HTMLInputElement>('[aria-label="日总量统计字段"]')!
  await act(async () => { field.focus(); field.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })) })
  await settle()
  const option = document.querySelector<HTMLElement>('.ant-select-item-option[title="热量（GJ）"]')!
  expect(option).not.toBeNull()
  await act(async () => option.click()); await settle()
  expect(host.textContent).toContain('单位：GJ')
  expect(host.textContent).toContain('暂无完整有效的日数据')
  expect(host.textContent).toContain('占比暂不可用')
  expect(host.querySelectorAll('[data-chart=line]')).toHaveLength(0)
})

it.each([false, true])('shows pending reasons and both retained values without a daily share (dark=%s)', async dark => {
  state.review = true
  const host = await mount(dark)
  expect(host.textContent).toContain('本字段 1 天待确认，已排除在有效汇总和占比之外')
  expect(host.textContent).toContain('存在待确认用量，已排除在有效汇总和占比之外')
  expect(host.querySelector('a[href*="quality_status=pending_review"]')?.getAttribute('href')).toBe('/energy/data-quality?year=2026&month=7&quality_status=pending_review')
  expect(host.textContent).toContain('占比暂不可用')
  const values = [...host.querySelectorAll<HTMLElement>('.ant-collapse-header')].find(item => item.textContent?.includes('查看每日数值与占比'))!
  await act(async () => values.click()); await settle()
  expect(host.textContent).toContain('原表值（待确认）')
  expect(host.textContent).toContain('28674')
  expect(host.textContent).toContain('2049315')
  expect(host.textContent).toContain('底码跳变与手填冲突；飞书N31')
  expect(host.textContent).toContain('有效 30/31 天')
})
