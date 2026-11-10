/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { App, ConfigProvider, theme } from 'antd'
const access = vi.hoisted(() => ({ query: true, entry: true, period: 'month=7', dashboardMounts: 0 }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (selector: (state: { hasPagePermission: (key: string) => boolean }) => boolean) => selector({ hasPagePermission: key => key === 'energy:reports' ? access.query : access.entry }) }))
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(access.period) }))
vi.mock('./EnergyEntryClient', () => ({ EnergyEntryClient: () => <p>直接原始录入</p> }))
vi.mock('./EnergyDashboard', async () => {
  const { useEffect } = await import('react')
  return { EnergyDashboard: () => {
    useEffect(() => { access.dashboardMounts += 1 }, [])
    return <><h3>能源仪表盘</h3><p>能源仪表盘内容</p></>
  } }
})
vi.mock('./EnergySettingsClient', () => ({ EnergySettingsClient: ({ options }: { options?: { is_manager: boolean } }) => <p>配置管理：{String(options?.is_manager)}</p> }))
vi.mock('./EnergyReportsClient', () => ({ EnergyReportsClient: ({ mode }: { mode: string }) => <p>报表模式：{mode}</p> }))
vi.mock('@/lib/api/energy-ledger', () => ({ ledgerRequest: vi.fn(async () => ({ is_manager: true, people: [] })) }))
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergyWorkspace, type EnergyMode } from './EnergyWorkspace'
import { EnergyEvidence } from './EnergyEvidence'
let root: Root | undefined
let client: QueryClient | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; client?.clear(); document.body.replaceChildren(); vi.clearAllMocks(); access.query = true; access.entry = true; access.period = 'month=7'; access.dashboardMounts = 0 })
async function mount(node: React.ReactNode) {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(node))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}
it.each<{ mode: EnergyMode; title: string; content: string }>([
  { mode: 'overview', title: '能源仪表盘', content: '能源仪表盘内容' },
  { mode: 'reports', title: '能源报表', content: '报表模式：reports' },
  { mode: 'analysis', title: '用量分析', content: '报表模式：analysis' },
  { mode: 'data-quality', title: '数据质量', content: '报表模式：data-quality' },
  { mode: 'settings', title: '配置管理', content: '配置管理：true' },
])('routes $mode to its correct task and passes manager options', async ({ mode, title, content }) => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await mount(<QueryClientProvider client={client}><EnergyWorkspace mode={mode} /></QueryClientProvider>)
  expect(document.querySelector('h3')?.textContent).toBe(title)
  expect(document.body.textContent).toContain(content)
  expect(ledgerRequest).toHaveBeenCalledWith('/ledger-options')
})
it.each([false, true])('removes the original-entry page and ledger tabs (dark=%s)', async dark => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await mount(<QueryClientProvider client={client}><ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkspace mode="reports" /></App></ConfigProvider></QueryClientProvider>)
  expect(document.querySelector('h3')?.textContent).toBe('能源报表')
  expect(document.querySelector('nav[aria-label="能源报表操作"]')).toBeNull()
  expect(document.body.textContent).not.toContain('原始数据填写')
})
it.each([null, 'raw source', [], 0])('does not present invalid provenance as evidence: %s', async value => {
  await mount(<EnergyEvidence value={value} />)
  expect(document.querySelector('section')).toBeNull()
})
it.each(['override', 'delta'])('shows nested original readings, zeroes, versions and %s adjustment reasons', async mode => {
  await mount(<EnergyEvidence value={{ reading_dates: ['2026-07-01', '2026-07-02'], reading_values: [null, '0'], versions: [1, 2], multiplier: 0, configuration_version: 3,
    adjustment: { mode, value: '0.1', reason: '校准后修正' },
    source_details: [null, { name: '水表', coefficient: '-1', value: null, evidence: { reading_values: ['12', '15'] } }],
  }} />)
  expect(document.body.textContent).toContain('读数日期：2026-07-01、2026-07-02')
  expect(document.body.textContent).toContain('原始读数：缺失 → 0')
  expect(document.body.textContent).toContain('原始记录版本：1、2')
  expect(document.body.textContent).toContain('倍率：0')
  expect(document.body.textContent).toContain('配置版本：3')
  expect(document.body.textContent).toContain(`${mode === 'override' ? '覆盖值' : '增减量'} 0.1；依据：校准后修正`)
  expect(document.body.textContent).toContain('水表 × -1 ＝ 缺失')
  expect(document.body.textContent).toContain('原始读数：12 → 15')
})

it.each([false, true])('shows exact original formula and source cells (dark=%s)', async dark => {
  await mount(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><EnergyEvidence value={{ business_sheet: '日总量', business_name: '用电量', source_sheet: '日用量', source_cell: 'B3', formula: '=电量!B2*3', sources: [null, { sheet: '电量', cell: 'B2', value: '20' }] }} /></ConfigProvider>)
  expect(document.body.textContent).toContain('业务字段：日总量·用电量')
  expect(document.body.textContent).toContain('原表位置：日用量!B3')
  expect(document.body.textContent).toContain('原表公式：=电量!B2*3')
  expect(document.body.textContent).toContain('引用：电量!B2 ＝ 20')
})

it('keeps the dashboard mounted when its year or month changes', async () => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const provider = client
  const content = () => <QueryClientProvider client={provider}><EnergyWorkspace mode="overview" /></QueryClientProvider>
  await mount(content())
  expect(access.dashboardMounts).toBe(1)
  access.period = 'year=2025&month=9'
  await act(async () => root?.render(content()))
  expect(access.dashboardMounts).toBe(1)
  expect(document.querySelectorAll('h3')).toHaveLength(1)
})
