/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams('month=7') }))
vi.mock('./EnergyEntryClient', () => ({ EnergyEntryClient: ({ manager }: { manager: boolean }) => <p>录入管理：{String(manager)}</p> }))
vi.mock('./EnergySettingsClient', () => ({ EnergySettingsClient: ({ options }: { options?: { is_manager: boolean } }) => <p>配置管理：{String(options?.is_manager)}</p> }))
vi.mock('./EnergyReportsClient', () => ({ EnergyReportsClient: ({ mode }: { mode: string }) => <p>报表模式：{mode}</p> }))
vi.mock('@/lib/api/energy-ledger', () => ({ ledgerRequest: vi.fn(async () => ({ is_manager: true, people: [] })) }))
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergyWorkspace, type EnergyMode } from './EnergyWorkspace'
import { EnergyEvidence } from './EnergyEvidence'
let root: Root | undefined
let client: QueryClient | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; client?.clear(); document.body.replaceChildren(); vi.clearAllMocks() })
async function mount(node: React.ReactNode) {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(node))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}
it.each<{ mode: EnergyMode; title: string; content: string }>([
  { mode: 'overview', title: '能源总览', content: '报表模式：overview' },
  { mode: 'entry', title: '数据填报', content: '录入管理：true' },
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
