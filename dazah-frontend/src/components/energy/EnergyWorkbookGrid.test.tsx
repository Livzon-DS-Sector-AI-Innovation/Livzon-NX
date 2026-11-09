/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import type { WorkbookReport } from '@/lib/api/energy-ledger'
import { EnergyWorkbookGrid } from './EnergyWorkbookGrid'

const report: WorkbookReport = {
  year: 2026, month: 7, dataset: '日总量', available_count: 3, expected_count: 4,
  columns: [
    { key: 'water', label: '饮用水', unit: 'm³', value_kind: 'usage', quantity_kind: 'volume' },
    { key: 'power', label: '用电量', unit: 'kWh', value_kind: 'usage', quantity_kind: 'electricity' },
  ],
  rows: [
    { date: '2026-07-01', cells: { water: { value: '0', status: 'complete' }, power: { value: '12.5000', status: 'complete' } } },
    { date: '2026-07-02', cells: { water: { value: null, status: 'missing_reading' }, power: { value: null, status: 'not_applicable' } } },
  ],
}
let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.replaceChildren() })
async function mount(dark = false, value = report) {
  const node = document.createElement('div'); document.body.append(node); root = createRoot(node)
  await act(async () => root?.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkbookGrid report={value} loading={false} /></App></ConfigProvider>))
  return node
}
function cell(row: number, column: number) { return document.querySelector<HTMLElement>(`[data-grid-row="${row}"][data-grid-column="${column}"]`)! }
async function key(target: HTMLElement, value: string, options: KeyboardEventInit = {}) {
  await act(async () => target.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true, ...options })))
}
function copy() {
  const setData = vi.fn()
  const event = new Event('copy', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'clipboardData', { value: { setData } })
  document.activeElement?.dispatchEvent(event)
  return setData
}

it.each([false, true])('selects rectangular ranges and copies plain values for Excel (dark=%s)', async dark => {
  const node = await mount(dark)
  expect(node.querySelector('table[role="grid"]')?.getAttribute('aria-label')).toBe('能源报表数据')
  await act(async () => cell(0, 1).dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
  expect(document.activeElement).toBe(cell(0, 1))
  await key(cell(0, 1), 'ArrowRight', { shiftKey: true })
  await key(cell(0, 2), 'ArrowDown', { shiftKey: true })
  expect(node.querySelectorAll('[aria-selected="true"]')).toHaveLength(4)
  expect(copy()).toHaveBeenCalledWith('text/plain', '0\t12.5\n待补数\t不适用')
  expect(node.querySelector('input, textarea')).toBeNull()
  await key(cell(1, 2), 'Escape')
  expect(node.querySelectorAll('[aria-selected="true"]')).toHaveLength(1)
})

it.each([false, true])('shows original source results and recalculation differences for review (dark=%s)', async dark => {
  const value: WorkbookReport = { ...report, rows: [{ date: '2026-10-01', cells: {
    water: { value: null, calculated_value: '50000', status: 'pending_review', provenance: { source_comparison: { reported_value: '53592', difference: '3592', calculation_status: 'complete', source: '循环水量!C6' } } },
    power: { value: null, calculated_value: null, status: 'pending_review', provenance: { source_comparison: { reported_value: '0', difference: null, calculation_status: 'abnormal_dependency', source: '日用量!H33' } } },
  } }] }
  await mount(dark, value)
  expect(cell(0, 1).textContent).toContain('53,592待核对')
  expect(cell(0, 1).textContent).toContain('系统计算值：50000')
  expect(cell(0, 1).textContent).toContain('差异（原表－系统）：3,592')
  expect(cell(0, 2).textContent).toContain('0待核对')
  expect(cell(0, 2).textContent).toContain('无法重算（来源存在异常）')
  expect(cell(0, 2).textContent).toContain('差异（原表－系统）：无法计算')
})

it('supports bounded arrows, tab, enter, home/end and select all', async () => {
  await mount()
  cell(0, 0).focus()
  await key(cell(0, 0), 'ArrowLeft')
  expect(document.activeElement).toBe(cell(0, 0))
  await key(cell(0, 0), 'End', { ctrlKey: true })
  expect(document.activeElement).toBe(cell(1, 2))
  await key(cell(1, 2), 'Home', { ctrlKey: true })
  await key(cell(0, 0), 'Tab')
  expect(document.activeElement).toBe(cell(0, 1))
  await key(cell(0, 1), 'Enter')
  expect(document.activeElement).toBe(cell(1, 1))
  await key(cell(1, 1), 'a', { metaKey: true })
  expect(copy()).toHaveBeenCalledWith('text/plain', '2026-07-01\t0\t12.5\n2026-07-02\t待补数\t不适用')
  const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
  await act(async () => cell(1, 2).dispatchEvent(event))
  expect(event.defaultPrevented).toBe(false)
})

it('extends a reversed mouse range and drag selection', async () => {
  await mount()
  await act(async () => cell(1, 2).dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 })))
  await act(async () => cell(0, 1).dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0, shiftKey: true })))
  expect(copy()).toHaveBeenCalledWith('text/plain', '0\t12.5\n待补数\t不适用')
  await act(async () => cell(0, 0).dispatchEvent(new MouseEvent('mouseover', { bubbles: true, buttons: 1 })))
  expect(document.querySelectorAll('[aria-selected="true"]')).toHaveLength(6)
})

it('opens editable cells on double click or F2 and leaves calculated cells read-only', async () => {
  const start = vi.fn()
  const node = document.createElement('div'); document.body.append(node); root = createRoot(node)
  await act(async () => root?.render(<EnergyWorkbookGrid report={report} loading={false} editing={{ canEdit: (_, key) => key === 'water', start, render: () => null }} />))
  expect(cell(0, 1).getAttribute('aria-readonly')).toBe('false')
  expect(cell(0, 2).getAttribute('aria-readonly')).toBe('true')
  await act(async () => cell(0, 1).dispatchEvent(new MouseEvent('dblclick', { bubbles: true })))
  expect(start).toHaveBeenLastCalledWith('2026-07-01', 'water')
  await key(cell(1, 1), 'F2')
  expect(start).toHaveBeenLastCalledWith('2026-07-02', 'water')
  await act(async () => cell(0, 2).dispatchEvent(new MouseEvent('dblclick', { bubbles: true })))
  expect(start).toHaveBeenCalledTimes(2)
})
