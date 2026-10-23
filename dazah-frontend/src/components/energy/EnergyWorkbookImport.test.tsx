/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
const state = vi.hoisted(() => ({ error: undefined as Error | undefined, pending: false, invalidate: vi.fn(), refetch: vi.fn() }))
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: state.invalidate }),
  useQuery: ({ queryFn }: { queryFn: () => unknown }) => { void queryFn(); return { data: [], isPending: state.pending, error: state.error, refetch: state.refetch } },
}))
vi.mock('@/lib/api/energy-ledger', () => ({ ledgerRequest: vi.fn(async () => []) }))
vi.mock('./EnergyImportClient', () => ({ EnergyImportClient: ({ initialYear, excelOnly, onChanged }: { initialYear: number; excelOnly: boolean; onChanged: () => unknown }) => <button onClick={() => void onChanged()}>原始 Excel 导入 {initialYear} {String(excelOnly)}</button> }))
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergyWorkbookImport } from './EnergyWorkbookImport'
let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; state.error = undefined; state.pending = false; vi.clearAllMocks(); document.body.replaceChildren() })
async function mount() {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<App><EnergyWorkbookImport year={2026} /></App>))
}
it('loads settings-scoped mapping and refreshes all ledger queries after import', async () => {
  await mount()
  const context = { headers: { 'X-Dazah-Page-Path': '/energy/settings' } }
  expect(ledgerRequest).toHaveBeenCalledWith('/input-fields', context)
  expect(document.body.textContent).toContain('原始 Excel 导入 2026 true')
  await act(async () => document.querySelector('button')?.click())
  expect(state.invalidate).toHaveBeenCalledWith({ queryKey: ['energy-ledger'] })
})
it('keeps the form unavailable on configuration failures and offers retry', async () => {
  state.error = new Error('无权读取能源配置')
  await mount()
  expect(document.body.textContent).toContain('无权读取能源配置')
  expect(document.body.textContent).not.toContain('原始 Excel 导入')
  const retry = Array.from(document.querySelectorAll('button')).find(button => button.textContent?.replaceAll(' ', '') === '重试')
  await act(async () => retry?.click())
  expect(state.refetch).toHaveBeenCalledTimes(1)
})
it('waits for mapping configuration before showing the importer', async () => {
  state.pending = true
  await mount()
  expect(document.querySelector('.ant-skeleton')).not.toBeNull()
  expect(document.body.textContent).not.toContain('原始 Excel 导入')
})
