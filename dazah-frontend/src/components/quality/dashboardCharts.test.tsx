/* @vitest-environment happy-dom */
import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import type { EChartsReactProps } from 'echarts-for-react'
import { AntdProvider } from '@/components/AntdProvider'
import { setAppearance } from '@/lib/useAppearance'
import { InstrumentsDashboard } from './inspection/InstrumentsDashboard'
import { SupplierDashboardPage } from './SupplierDashboardPage'

const mocks = vi.hoisted(() => ({ charts: [] as EChartsReactProps[], instruments: vi.fn(), suppliers: vi.fn(), qualifications: vi.fn() }))
vi.mock('@/lib/api/client/quality', () => ({ fetchInstrumentsDashboard: mocks.instruments, fetchSupplierStatistics: mocks.suppliers, fetchSupplierQualifications: mocks.qualifications }))
vi.mock('next/link', () => ({ default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a> }))
vi.mock('echarts-for-react', () => ({ default: (props: EChartsReactProps) => {
  mocks.charts.push(props)
  return <div data-chart-theme={props.theme || 'light'}><button onClick={() => props.onEvents?.click({ dataIndex: 0 })}>图表下钻</button></div>
} }))
const instruments = { configured: true, equipment: { total: 12, ok: 10, repairing: 2, key_count: 1 }, maintenance: { total: 4, unfinished: 2, due_soon_7d: 1 }, contracts: { total: 3 }, calibration_due: [], calibration_expired: [], equipment_status: [{ name: '完好', value: 10 }, { name: '维修', value: 2 }], calibration_upcoming: [{ month: '2026-10', count: 3 }], maintenance_due_buckets: [{ name: '已过期', value: 2 }] }
const supplierName = '测试供应商甲完整名称超过十二个字'
const suppliers = { total: 10, completion_rate: 80, supplier_count: 1, expired_count: 2, due_30_count: 1, due_60_count: 1, due_90_count: 1, normal_count: 5, material_type_compliance: [{ type: '固体', completed: 8, pending: 2 }], qualification_compliance: [{ name: '许可', total: 10, completed: 8, completion_rate: 80 }], supplier_risk_ranking: [{ name: supplierName, total: 10, completed: 8, pending: 2, expired: 2, due30: 1 }], expiry_timeline: [{ month: '2026-10', count: 2 }] }
let host: HTMLDivElement; let root: Root; let client: QueryClient
async function render(component: ReactNode, initial?: { key: string[]; data: unknown }) {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  if (initial) client.setQueryData(initial.key, initial.data)
  mocks.charts = []
  await act(async () => setAppearance('light'))
  await act(async () => root.render(<AntdProvider><QueryClientProvider client={client}>{component}</QueryClientProvider></AntdProvider>))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
}
afterEach(async () => { await act(async () => root?.unmount()); client?.clear(); host?.remove(); vi.resetAllMocks(); await act(async () => setAppearance('system')) })

it('keeps all instrument distribution values intact across both appearances', async () => {
  await render(<InstrumentsDashboard />, { key: ['quality-instruments', 'dashboard'], data: instruments })
  expect(host.querySelectorAll('[data-chart-theme="light"]')).toHaveLength(3)
  expect(mocks.charts[0].option.series[0].data.map((item: { value: number }) => item.value)).toEqual([10, 2])
  expect(mocks.charts[1].option.series[0].data.map((item: { value: number }) => item.value)).toEqual([3])
  expect(mocks.charts[2].option.series[0].data.map((item: { value: number }) => item.value)).toEqual([2])
  await act(async () => setAppearance('dark'))
  expect(host.querySelectorAll('[data-chart-theme="dark"]')).toHaveLength(3)
  expect(host.textContent).toContain('设备总数')
})

it('shows instrument loading/failure separately and retries with real statistics', async () => {
  let reject: (error: Error) => void = () => {}
  mocks.instruments.mockImplementationOnce(() => new Promise((_resolve, rejectPromise) => { reject = rejectPromise }))
  await render(<InstrumentsDashboard />)
  expect(host.textContent).toContain('正在读取仪器统计数据')
  expect(host.querySelector('[data-chart-theme]')).toBeNull()
  await act(async () => { reject(new Error('offline')); await new Promise((resolve) => setTimeout(resolve, 20)) })
  expect(host.textContent).toContain('仪器统计数据加载失败')
  mocks.instruments.mockResolvedValueOnce(instruments)
  await act(async () => [...host.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent?.replace(/\s/g, '') === '重试')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
  expect(host.querySelectorAll('[data-chart-theme]')).toHaveLength(3)
})

it('preserves supplier values, readable responsive options and full-name drilldown', async () => {
  mocks.qualifications.mockResolvedValue({ items: [], total: 0 })
  await render(<SupplierDashboardPage />, { key: ['quality-supplier', 'stats'], data: suppliers })
  const [risk, donut] = mocks.charts
  expect(risk.option.series[0].data).toEqual([8])
  expect(risk.option.tooltip.formatter([{ dataIndex: 0 }])).toContain(supplierName)
  expect(donut.option.media[0].option.series[0].label.show).toBe(false)
  expect(donut.option.media[1].option.series[0].label.show).toBe(true)
  expect(host.querySelector('[aria-label="到期状态数值"]')?.textContent).toContain('已延期 2')
  expect(host.querySelector('[aria-label="到期状态数值"]')?.textContent).toContain('正常 5')
  await act(async () => risk.onEvents?.click({ dataIndex: 0 }))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
  expect(document.body.textContent).toContain(`${supplierName} — 全部资质`)
  await act(async () => setAppearance('dark'))
  expect(host.querySelectorAll('[data-chart-theme="dark"]')).toHaveLength(5)
})

it('does not disguise supplier fetch failures as empty data and supports retry', async () => {
  mocks.suppliers.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ ...suppliers, total: 0 })
  await render(<SupplierDashboardPage />)
  expect(host.textContent).toContain('供应商统计数据加载失败')
  expect(host.textContent).not.toContain('暂无供应商资质数据')
  await act(async () => [...host.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent?.replace(/\s/g, '') === '重试')?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)) })
  expect(host.textContent).toContain('暂无供应商资质数据')
  expect(host.querySelector('[data-chart-theme]')).toBeNull()
})
