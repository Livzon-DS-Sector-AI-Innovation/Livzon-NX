/* @vitest-environment happy-dom */
import { act, StrictMode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
const state = vi.hoisted(() => ({ allowed: true, save: vi.fn(), invalidate: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (select: (auth: { hasPagePermission: (page: string) => boolean }) => boolean) => select({ hasPagePermission: page => page === 'energy:entry' && state.allowed }) }))
vi.mock('@/actions/energy-ledger', () => ({ saveDirectReadings: state.save }))
vi.mock('./EnergyWorkbookImport', () => ({ EnergyWorkbookImport: () => null }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: state.invalidate }), useQuery: ({ queryKey }: { queryKey: string[] }) => ({ data: queryKey[1] === 'workbook' ? {
  year: 2026, month: 7, dataset: '饮用水码', available_count: 0, expected_count: 2,
  columns: [2, 3].map(key => ({ key: String(key), label: `水表${key}`, unit: 'm³', value_kind: 'reading', quantity_kind: 'volume' })),
  rows: [{ date: '2026-07-01', cells: { '2': { value: null, status: 'missing_reading' }, '3': { value: null, status: 'missing_reading' } } }],
} : queryKey[1] === 'editable-fields' ? [2, 3].map(key => ({ id: `p${key}`, definition: { enabled: true, source_sheet: '饮用水码', source_column: key } })) : {
  items: [2, 3].map(key => ({ point_id: `p${key}`, value: null, version: 0, precision: 3 })),
}, isFetching: false }) }))
import { EnergyWorkbookClient } from './EnergyWorkbookClient'
let root: Root | undefined
async function mount() {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<StrictMode><App><EnergyWorkbookClient year={2026} month={7} dataset="饮用水码" /></App></StrictMode>))
}
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; vi.useRealTimers(); document.body.replaceChildren(); vi.clearAllMocks(); state.allowed = true })
async function edit(column: number, value: string) {
  await act(async () => document.querySelector(`[data-grid-row="0"][data-grid-column="${column}"]`)?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true })))
  const input = document.querySelector<HTMLInputElement>(`[data-grid-column="${column}"] input[aria-label="单元格数值"]`)!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
  await act(async () => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
}
it('keeps an earlier pending edit when entering another cell, and undoes only the chosen edit', async () => {
  state.save.mockResolvedValue({ ok: true, data: {} }); await mount(); vi.useFakeTimers()
  await edit(1, '12'); await edit(2, '13')
  expect(document.querySelectorAll('input[aria-label="单元格数值"]')).toHaveLength(2)
  const undo = Array.from(document.querySelectorAll('button')).filter(button => button.textContent === '撤销')
  expect(undo).toHaveLength(2)
  await act(async () => undo[0].click())
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(state.save).toHaveBeenCalledTimes(1)
  expect(state.save.mock.calls[0][0].values).toEqual([{ point_id: 'p3', value: '13', version: 0 }])
})
it('leaves every cell read-only without the original entry grant', async () => {
  state.allowed = false; await mount()
  await act(async () => document.querySelector('[data-grid-column="1"]')?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true })))
  expect(document.querySelector('input[aria-label="单元格数值"]')).toBeNull()
  expect(document.querySelectorAll('td[aria-readonly="false"]')).toHaveLength(0)
})
