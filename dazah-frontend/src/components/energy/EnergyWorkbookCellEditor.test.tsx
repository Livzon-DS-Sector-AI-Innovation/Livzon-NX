/* @vitest-environment happy-dom */
import { act, StrictMode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
const state = vi.hoisted(() => ({ value: null as string | null, invalidate: vi.fn(), save: vi.fn(), close: vi.fn() }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: state.invalidate }), useQuery: () => ({ data: { items: [{ point_id: 'p1', value: state.value, draft_value: null, version: 7, precision: 3 }] }, isFetching: false }) }))
vi.mock('@/actions/energy-ledger', () => ({ saveDirectReadings: state.save }))
import { EnergyWorkbookCellEditor } from './EnergyWorkbookCellEditor'
let root: Root | undefined
let host: HTMLDivElement
async function mount(dark = false) {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<StrictMode><ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkbookCellEditor date="2026-07-01" dataset="饮用水码" pointId="p1" onClose={state.close} /></App></ConfigProvider></StrictMode>))
  expect(state.close).not.toHaveBeenCalled()
}
async function fill(label: string, value: string) {
  const input = host.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })) })
}
async function save() { await act(async () => Array.from(host.querySelectorAll('button')).find(button => button.textContent?.replaceAll(' ', '') === '保存')?.click()) }
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; vi.useRealTimers(); document.body.replaceChildren(); state.value = null; vi.clearAllMocks() })
it.each([false, true])('undoes a new value during the five second window without writing (dark=%s)', async dark => {
  await mount(dark); vi.useFakeTimers()
  await fill('单元格数值', '123.4'); await save()
  expect(document.body.textContent).toContain('5 秒后保存')
  expect(state.save).not.toHaveBeenCalled()
  await act(async () => Array.from(document.querySelectorAll('button')).find(button => button.textContent === '撤销')?.click())
  await act(async () => vi.advanceTimersByTimeAsync(5100))
  expect(state.save).not.toHaveBeenCalled(); expect(state.close).toHaveBeenCalled()
})
it('saves zero with the current version and refreshes related reports after the window', async () => {
  state.save.mockResolvedValue({ ok: true, data: {} }); await mount(); vi.useFakeTimers()
  await fill('单元格数值', '0'); await save()
  await act(async () => vi.advanceTimersByTimeAsync(4999)); expect(state.save).not.toHaveBeenCalled()
  await act(async () => vi.advanceTimersByTimeAsync(1))
  expect(state.save).toHaveBeenCalledExactlyOnceWith({ reading_date: '2026-07-01', dataset: '饮用水码', values: [{ point_id: 'p1', value: '0', version: 7 }], draft: false, reason: '' })
  expect(state.invalidate).toHaveBeenCalledWith({ queryKey: ['energy-ledger'] })
})
it('requires a correction reason and keeps failed input for retry', async () => {
  state.value = '10'; state.save.mockResolvedValue({ ok: false, message: '数据已被修改，请刷新后核对最新版本' })
  await mount(); vi.useFakeTimers(); await fill('单元格数值', '20'); await save()
  expect(host.textContent).toContain('请填写更正原因'); expect(state.save).not.toHaveBeenCalled()
  await fill('更正原因', '核对抄表记录'); await save()
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(host.textContent).toContain('数据已被修改')
  expect(host.querySelector<HTMLInputElement>('input[aria-label="单元格数值"]')?.value).toBe('20')
  expect(state.invalidate).not.toHaveBeenCalled(); expect(state.close).not.toHaveBeenCalled()
})
it('rejects excess precision and cancels a pending write when the cell leaves the view', async () => {
  await mount(); vi.useFakeTimers(); await fill('单元格数值', '1.2345'); await save()
  expect(host.textContent).toContain('最多 3 位小数'); expect(state.save).not.toHaveBeenCalled()
  await fill('单元格数值', '2'); await save()
  await act(async () => root?.unmount()); root = undefined
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(state.save).not.toHaveBeenCalled()
})
