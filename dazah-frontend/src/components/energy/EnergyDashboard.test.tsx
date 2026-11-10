/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { WorkbookReport } from '@/lib/api/energy-ledger'

const state = vi.hoisted(() => ({ failure: '', dark: false, pending: false, gap: false, empty: false, noReadings: false, filledDays: 31, delta: 0, query: 'year=2026&month=7', listeners: new Set<() => void>() }))
vi.mock('next/navigation', async () => {
  const { useSyncExternalStore } = await import('react')
  return { useSearchParams: () => new URLSearchParams(useSyncExternalStore(
    listener => { state.listeners.add(listener); return () => { state.listeners.delete(listener) } },
    () => state.query,
    () => state.query,
  )) }
})
vi.mock('@/lib/useAppearance', () => ({ useAppearance: () => ({ resolved: state.dark ? 'dark' : 'light' }) }))
vi.mock('echarts-for-react', () => ({ default: ({ option, theme: appearance }: { option: { series?: { type: string; name: string; data: unknown[] }[] }; theme?: string }) => <div data-chart={option.series?.[0]?.type} data-series={option.series?.[0]?.name} data-values={JSON.stringify(option.series?.[0]?.data)} data-theme={appearance || 'light'} /> }))
vi.mock('@/lib/api/energy-ledger', async importOriginal => {
  const original = await importOriginal<typeof import('@/lib/api/energy-ledger')>()
  return { ...original, ledgerRequest: vi.fn(async (path: string) => {
    if (state.pending) return new Promise(() => {})
    const params = new URLSearchParams(path.split('?')[1])
    if (params.get('month') === state.failure) throw new Error('无权查看当前表')
    const data = workbook(Number(params.get('month')), params.get('dataset')!, Number(params.get('year')))
    return state.empty ? { ...data, columns: [], rows: [] } : data
  }) }
})
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergyDashboard } from './EnergyDashboard'

function workbook(month: number, dataset = '日总量', year = 2026): WorkbookReport {
  const days = new Date(year, month, 0).getDate()
  return { dataset, year, month, available_count: days, expected_count: days,
    columns: ['4', '6', '7', '8', '9', '10'].map(key => ({ key, label: key === '6' ? '电日用量' : '用量', unit: key === '6' ? 'kWh' : 'm³', quantity_kind: 'volume', value_kind: dataset.endsWith('码') ? 'reading' : 'usage' })),
    rows: Array.from({ length: days }, (_, index) => ({ date: `${year}-${String(month).padStart(2, '0')}-${String(index + 1).padStart(2, '0')}`, cells: Object.fromEntries(['4', '6', '7', '8', '9', '10'].map(key => [key, { value: state.noReadings || index >= state.filledDays ? null : String(index + state.delta), status: state.noReadings || index >= state.filledDays ? 'missing_reading' : state.gap && month === 7 && key === '6' && index === 1 ? 'source_formula_error' : 'complete' }])) })),
  }
}
let root: Root | undefined
let client: QueryClient
let host: HTMLDivElement
async function settle() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 70)) }) }
async function render(dark: boolean) {
  state.dark = dark
  await act(async () => root!.render(<QueryClientProvider client={client}><ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyDashboard /></App></ConfigProvider></QueryClientProvider>))
  await settle(); await settle()
}
async function mount(dark = false) {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await render(dark)
  return host
}
beforeEach(() => {
  const replace = window.history.replaceState.bind(window.history)
  vi.spyOn(window.history, 'replaceState').mockImplementation((data, unused, url) => {
    replace(data, unused, url)
    state.query = window.location.search.slice(1)
    state.listeners.forEach(listener => listener())
  })
})
afterEach(async () => { await act(async () => root?.unmount()); client?.clear(); document.body.replaceChildren(); vi.clearAllMocks(); vi.restoreAllMocks(); vi.useRealTimers(); state.failure = ''; state.pending = false; state.gap = false; state.empty = false; state.noReadings = false; state.filledDays = 31; state.delta = 0; state.query = 'year=2026&month=7'; window.history.replaceState(null, '', '/') })

it.each([false, true])('shows the energy overview without the automatic calculation notice (dark=%s)', async dark => {
  await mount(dark)
  expect(host.querySelector('[aria-label="月度能源概览"]')).not.toBeNull()
  expect(host.querySelectorAll('button[aria-pressed]')).toHaveLength(6)
  expect(host.querySelectorAll('[data-chart]')).toHaveLength(2)
  expect(host.textContent).not.toContain('六张原始表填写后，关联用量、日总量及车间表自动计算')
  expect(host.querySelector('[data-platform-notice="info"]')).toBeNull()
})

it.each([false, true])('shows six summaries and only two charts, reading live reports for the selected and previous three months (dark=%s)', async dark => {
  await mount(dark)
  expect(host.querySelectorAll('button[aria-pressed]')).toHaveLength(6)
  expect(host.querySelectorAll('[data-chart]')).toHaveLength(2)
  expect(host.querySelector('[data-chart=pie]')).toBeNull()
  expect(host.textContent).toContain('7 月能源概览')
  expect(host.querySelector('[aria-label="年份"]')).not.toBeNull()
  expect(host.querySelector('[aria-label="月份"]')).not.toBeNull()
  expect(host.textContent).not.toContain('7—10 月连续数据')
  expect(host.textContent).toContain('电量每日趋势')
  const paths = vi.mocked(ledgerRequest).mock.calls.map(([path]) => path)
  expect(paths).toHaveLength(4)
  expect(paths.every(path => !path.includes('baseline') && path.startsWith('/reporting/workbook?'))).toBe(true)
  expect(paths.map(path => new URLSearchParams(path.split('?')[1]).get('month'))).toEqual(['7', '4', '5', '6'])
  expect([...host.querySelectorAll('[data-chart]')].every(chart => chart.getAttribute('data-theme') === (dark ? 'dark' : 'light'))).toBe(true)
  const water = [...host.querySelectorAll<HTMLButtonElement>('button[aria-pressed]')].find(button => button.textContent?.includes('饮用水'))!
  await act(async () => water.click())
  expect(host.textContent).toContain('饮用水每日趋势')
  expect(water.getAttribute('aria-pressed')).toBe('true')
})
it('defaults to the current year/month and never introduces a combined viewing range', async () => {
  state.query = ''
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-14T00:00:00+08:00'))
  await mount()
  expect(host.textContent).toContain('9 月能源概览')
  expect(host.textContent).not.toContain('连续日趋势')
  const values = JSON.parse(host.querySelector('[data-chart=line]')!.getAttribute('data-values')!)
  expect(values).toHaveLength(30)
  expect(host.textContent).toContain('已统计 30 天')
})
it.each(['year=2025&month=7', 'year=2026&month=11', 'year=2028&month=2'])('reads live configured data for %s without a sample-period restriction', async query => {
  state.query = query
  await mount()
  expect(host.querySelectorAll('[data-chart]')).toHaveLength(2)
  const paths = vi.mocked(ledgerRequest).mock.calls.map(([path]) => new URLSearchParams(path.split('?')[1]))
  expect(paths).toHaveLength(4)
  expect(paths[0]?.get('year')).toBe(new URLSearchParams(query).get('year'))
  expect(paths[0]?.get('month')).toBe(new URLSearchParams(query).get('month'))
})
it('shows the empty field state without chart totals', async () => {
  state.empty = true
  await mount()
  expect(host.textContent).toContain('2026 年 7 月暂无已配置的能源字段')
  expect(host.querySelector('[data-chart]')).toBeNull()
})
it('refreshes calculations after readings change', async () => {
  await mount()
  expect(JSON.parse(host.querySelector('[data-chart=line]')!.getAttribute('data-values')!)[0]).toBe(0)
  state.delta = 50
  const refresh = [...host.querySelectorAll('button')].find(button => button.textContent?.replaceAll(' ', '') === '刷新')!
  await act(async () => refresh.click()); await settle(); await settle()
  expect(JSON.parse(host.querySelector('[data-chart=line]')!.getAttribute('data-values')!)[0]).toBe(50)
})
it('updates chart appearance immediately when appearance switches', async () => {
  await mount(); await render(true)
  expect([...host.querySelectorAll('[data-chart]')].every(chart => chart.getAttribute('data-theme') === 'dark')).toBe(true)
  await render(false)
  expect([...host.querySelectorAll('[data-chart]')].every(chart => chart.getAttribute('data-theme') === 'light')).toBe(true)
})
it('keeps available months when another source fails, exposes retry and leaves a gap in the comparison', async () => {
  state.failure = '5'; await mount()
  expect(host.textContent).toContain('部分月份原表暂不可用')
  expect(host.textContent).toContain('电量每日趋势')
  expect(JSON.parse(host.querySelector('[data-chart=bar]')!.getAttribute('data-values')!)[1]).toBeNull()
  state.failure = ''
  const retry = [...host.querySelectorAll('button')].find(button => button.textContent?.replaceAll(' ', '') === '重试')!
  await act(async () => retry.click()); await settle(); await settle()
  expect(host.textContent).not.toContain('部分月份原表暂不可用')
})
it('shows loading without invented totals and prioritizes the selected month', async () => {
  state.pending = true; await mount()
  expect(host.querySelector('.ant-skeleton')).not.toBeNull()
  expect(host.querySelector('[data-chart]')).toBeNull()
  expect(vi.mocked(ledgerRequest).mock.calls.map(([path]) => new URLSearchParams(path.split('?')[1]).get('month'))).toEqual(['7'])
})
it('keeps source errors visible in daily details while comparing the valid daily totals', async () => {
  state.gap = true; await mount()
  expect(host.textContent).not.toContain('月累计和日均暂不可用')
  expect(JSON.parse(host.querySelector('[data-chart=bar]')!.getAttribute('data-values')!)[3]).toBe(464)
  expect(host.querySelector('.ant-statistic-content')?.textContent).toContain('15.47')
  const header = [...host.querySelectorAll<HTMLElement>('.ant-collapse-header')].find(item => item.textContent?.includes('电量每日数值'))!
  await act(async () => header.click()); await settle()
  expect(host.textContent).toContain('原表公式需核对')
  expect(host.textContent).toContain('原表值')
})
it('loads one source detail chart only after expanding the source explorer', async () => {
  await mount()
  const header = [...host.querySelectorAll<HTMLElement>('.ant-collapse-header')].find(item => item.textContent?.includes('查看分类用量、车间与原始表码'))!
  await act(async () => header.click()); await settle()
  expect(host.querySelector('[aria-label="明细数据表"]')).not.toBeNull()
  expect(host.querySelectorAll('[data-chart]')).toHaveLength(3)
  // Reuses the current month snapshot instead of fetching all 21 datasets.
  expect(vi.mocked(ledgerRequest).mock.calls).toHaveLength(4)
})
it('switches the monthly comparison to daily averages to account for month length', async () => {
  await mount()
  const average = [...host.querySelectorAll<HTMLElement>('.ant-segmented-item')].find(item => item.textContent === '日均')!
  await act(async () => average.click())
  expect(host.querySelector('[data-chart=bar]')!.getAttribute('data-series')).toBe('电量日均')
  expect(JSON.parse(host.querySelector('[data-chart=bar]')!.getAttribute('data-values')!)).toEqual([14.5, 15, 14.5, 15])
})

async function selectMonth(month: number) {
  const input = host.querySelector<HTMLInputElement>('[aria-label="月份"]')
  if (!input) throw new Error('月份控件不存在')
  await act(async () => input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await settle()
  const option = document.querySelector<HTMLElement>(`.ant-select-item-option[title="${month}月"]`)
  if (!option) throw new Error(`月份选项不存在：${month}`)
  await act(async () => option.click())
  await settle()
}
it.each([false, true])('switches data immediately on month and year selection, retaining metric and comparison (dark=%s)', async dark => {
  await mount(dark)
  expect([...host.querySelectorAll('button')].some(button => button.textContent?.replaceAll(' ', '') === '查询')).toBe(false)
  const water = [...host.querySelectorAll<HTMLButtonElement>('button[aria-pressed]')].find(button => button.textContent?.includes('饮用水'))
  if (!water) throw new Error('饮用水指标不存在')
  await act(async () => water.click())
  const average = [...host.querySelectorAll<HTMLElement>('.ant-segmented-item')].find(item => item.textContent === '日均')
  if (!average) throw new Error('日均口径不存在')
  await act(async () => average.click())
  await selectMonth(9)
  expect(host.textContent).toContain('9 月能源概览')
  expect(window.location.search).toBe('?year=2026&month=9')
  expect(water.getAttribute('aria-pressed')).toBe('true')
  expect(host.querySelector('[data-chart=bar]')?.getAttribute('data-series')).toBe('饮用水日均')
  expect(JSON.parse(host.querySelector('[data-chart=line]')?.getAttribute('data-values') ?? '[]')).toHaveLength(30)
  const year = host.querySelector<HTMLInputElement>('[aria-label="年份"]')
  if (!year) throw new Error('年份控件不存在')
  await act(async () => year.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await settle()
  await act(async () => year.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', keyCode: 38, bubbles: true })))
  await act(async () => year.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true })))
  await settle()
  expect(window.location.search).toBe('?year=2025&month=9')
  expect(vi.mocked(ledgerRequest).mock.calls.some(([path]) => path.includes('year=2025&month=9'))).toBe(true)
  expect(water.getAttribute('aria-pressed')).toBe('true')
})
it('allows another month to load while an earlier month is still pending', async () => {
  state.pending = true
  await mount()
  state.pending = false
  await selectMonth(9)
  expect(host.textContent).toContain('9 月能源概览')
  expect(host.textContent).toContain('已统计 30 天')
  expect(host.querySelector('[data-chart=line]')).not.toBeNull()
})

it('shows compact empty states when configured fields have no readings', async () => {
  state.noReadings = true
  await mount()
  expect(host.querySelectorAll('button[aria-pressed]')).toHaveLength(6)
  expect(host.textContent).toContain('本月暂无有效日数据')
  expect(host.textContent).toContain('暂无月度对比数据')
  expect(host.querySelector('[data-chart]')).toBeNull()
})

it.each([false, true])('updates cumulative usage, daily averages and comparisons as daily entries arrive (dark=%s)', async dark => {
  state.filledDays = 28
  await mount(dark)
  expect(host.querySelector('[data-platform-notice="warning"]')).toBeNull()
  expect(host.textContent).not.toContain('暂不可用')
  expect(host.textContent).toContain('已统计 28 天')
  expect(host.querySelector('.ant-statistic-content')?.textContent).toContain('13.5')
  expect(JSON.parse(host.querySelector('[data-chart=bar]')!.getAttribute('data-values')!)).toEqual([378, 378, 378, 378])
  const average = [...host.querySelectorAll<HTMLElement>('.ant-segmented-item')].find(item => item.textContent === '日均')!
  await act(async () => average.click())
  expect(JSON.parse(host.querySelector('[data-chart=bar]')!.getAttribute('data-values')!)).toEqual([13.5, 13.5, 13.5, 13.5])
  state.filledDays = 29
  const refresh = [...host.querySelectorAll('button')].find(button => button.textContent?.replaceAll(' ', '') === '刷新')!
  await act(async () => refresh.click()); await settle(); await settle()
  expect(host.textContent).toContain('已统计 29 天')
  expect(host.querySelector('[aria-pressed="true"]')?.textContent).toContain('406')
  expect(JSON.parse(host.querySelector('[data-chart=bar]')!.getAttribute('data-values')!)).toEqual([14, 14, 14, 14])
})
