/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, hydrateRoot, type Root } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { App, ConfigProvider, theme } from 'antd'
const access = vi.hoisted(() => ({ query: true, entry: true }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (selector: (state: { hasPagePermission: (key: string) => boolean }) => boolean) => selector({ hasPagePermission: key => key === 'energy:reports' ? access.query : access.entry }) }))
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams('month=7') }))
vi.mock('./EnergyEntryClient', () => ({ EnergyEntryClient: () => <p>直接原始录入</p> }))
vi.mock('./EnergyDashboard', () => ({ EnergyDashboard: () => <p>能源仪表盘内容</p> }))
vi.mock('./EnergySettingsClient', () => ({ EnergySettingsClient: ({ options }: { options?: { is_manager: boolean } }) => <p>配置管理：{String(options?.is_manager)}</p> }))
vi.mock('./EnergyReportsClient', () => ({ EnergyReportsClient: ({ mode }: { mode: string }) => <p>报表模式：{mode}</p> }))
vi.mock('@/lib/api/energy-ledger', () => ({ ledgerRequest: vi.fn(async () => ({ is_manager: true, people: [] })) }))
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergyWorkspace, type EnergyMode } from './EnergyWorkspace'
import { EnergyEvidence } from './EnergyEvidence'
let root: Root | undefined
let client: QueryClient | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; client?.clear(); document.body.replaceChildren(); vi.clearAllMocks(); access.query = true; access.entry = true })
async function mount(node: React.ReactNode) {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(node))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}
it.each<{ mode: EnergyMode; title: string; content: string }>([
  { mode: 'overview', title: '能源仪表盘', content: '能源仪表盘内容' },
  { mode: 'entry', title: '原始数据填写', content: '直接原始录入' },
  { mode: 'reports', title: '能源台账', content: '报表模式：reports' },
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
it.each([false, true])('shares the ledger navigation and retains query links (dark=%s)', async dark => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await mount(<QueryClientProvider client={client}><ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkspace mode="entry" /></App></ConfigProvider></QueryClientProvider>)
  const navigation = document.querySelector('nav[aria-label="能源台账操作"]')!
  expect(navigation.querySelector('.ant-menu-horizontal')).not.toBeNull()
  expect(navigation.querySelector('.ant-menu-item-selected')?.textContent).toContain('原始数据填写')
  expect(navigation.querySelector('[aria-current="page"]')?.textContent).toBe('原始数据填写')
  expect(navigation.querySelector('[aria-current="page"]')?.getAttribute('href')).toBe('/energy/entry?month=7')
  expect(navigation.querySelector('a')?.getAttribute('href')).toBe('/energy/reports')
})
it.each(['entry', 'reports'] as const)('does not expose the other operation without its query grant (%s)', async mode => {
  access.query = mode === 'reports'; access.entry = mode === 'entry'
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await mount(<QueryClientProvider client={client}><EnergyWorkspace mode={mode} /></QueryClientProvider>)
  const links = document.querySelectorAll('nav[aria-label="能源台账操作"] a')
  expect(links).toHaveLength(1)
  expect(links[0].getAttribute('aria-current')).toBe('page')
})
it('hydrates ledger links before showing client permission-dependent navigation', async () => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const node = <QueryClientProvider client={client}><EnergyWorkspace mode="reports" /></QueryClientProvider>
  const host = document.createElement('div')
  host.innerHTML = renderToString(node)
  document.body.append(host)
  expect(host.querySelectorAll('nav a')).toHaveLength(1)
  const recoverableError = vi.fn()
  await act(async () => { root = hydrateRoot(host, node, { onRecoverableError: recoverableError }) })
  expect(recoverableError).not.toHaveBeenCalled()
  expect(host.querySelectorAll('nav a')).toHaveLength(2)
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
