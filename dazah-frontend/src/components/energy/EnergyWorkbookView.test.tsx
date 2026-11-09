/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import type { WorkbookReport } from '@/lib/api/energy-ledger'
import { EnergyWorkbookView } from './EnergyWorkbookView'

const report: WorkbookReport = {
  year: 2026, month: 7, dataset: '饮用水码', available_count: 108, expected_count: 110,
  columns: Array.from({ length: 10 }, (_, index) => ({ key: String(index), label: `${index + 101}车间`, unit: 'm³', value_kind: 'reading', quantity_kind: 'volume' })),
  rows: Array.from({ length: 11 }, (_, index) => ({ date: `2026-07-${String(index + 1).padStart(2, '0')}`, cells: Object.fromEntries(Array.from({ length: 10 }, (_, column) => [String(column), { value: index === 2 && column === 0 ? null : String((11 - index) * 1000 + column), status: index === 2 && column === 0 ? 'missing_reading' : 'complete' }])) })),
}
let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.replaceChildren(); vi.restoreAllMocks() })
async function mount(dark = false) {
  const node = document.createElement('div'); document.body.append(node); root = createRoot(node)
  await act(async () => root?.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkbookView report={report} loading={false} /></App></ConfigProvider>))
  return node
}
const button = (name: string) => Array.from(document.querySelectorAll('button')).find(item => item.textContent === name || item.getAttribute('aria-label') === name)!
async function search(value: string) {
  const input = document.querySelector<HTMLInputElement>('[aria-label="搜索报表字段"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

it.each([false, true])('paginates dates, shows all fields, searches fields and resets the view (dark=%s)', async dark => {
  const node = await mount(dark)
  expect(node.querySelectorAll('tr[data-row-key]')).toHaveLength(10)
  expect(node.querySelectorAll('th')).toHaveLength(11)
  expect(node.textContent).not.toContain('下一组字段')
  expect(node.textContent).toContain('10 个字段')
  await search('110')
  expect(node.querySelectorAll('th')).toHaveLength(2)
  expect(node.querySelector('th:nth-child(2)')?.textContent).toContain('110车间')
  await search('不存在')
  expect(node.textContent).toContain('没有匹配的字段')
  await act(async () => button('重置视图').click())
  expect(node.querySelectorAll('th')).toHaveLength(11)
  await act(async () => node.querySelector<HTMLElement>('.ant-pagination-item-2')?.click())
  expect(node.querySelectorAll('tr[data-row-key]')).toHaveLength(1)
  expect(node.querySelector('tr[data-row-key]')?.getAttribute('data-row-key')).toBe('2026-07-11')
})

it('filters attention states, sorts values and copies the displayed order with headers', async () => {
  const node = await mount()
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(writeText)
  try {
    await act(async () => node.querySelector<HTMLInputElement>('input[type="checkbox"]')?.click())
    expect(node.querySelectorAll('tr[data-row-key]')).toHaveLength(1)
    expect(node.textContent).toContain('待补数')
    await act(async () => button('复制本页').click())
    expect(writeText.mock.calls[0][0].split('\n')).toHaveLength(2)
    expect(writeText.mock.calls[0][0]).toContain('2026-07-03\t待补数\t9001')
    await act(async () => button('重置视图').click())
    await act(async () => node.querySelector<HTMLElement>('th:nth-child(2)')?.click())
    expect(node.querySelector('tr[data-row-key]')?.getAttribute('data-row-key')).toBe('2026-07-11')
    await act(async () => button('复制本页').click())
    expect(writeText.mock.calls[1][0].split('\n')[1]).toContain('2026-07-11\t1000\t1001')
    expect(writeText.mock.calls[1][0]).not.toContain('1,000')
  } finally { vi.restoreAllMocks() }
})

it('reports clipboard failure and retains the grid for keyboard copying', async () => {
  const node = await mount()
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
  try {
    await act(async () => button('复制本页').click())
    expect(document.body.textContent).toContain('复制失败，请选中表格区域后按 Ctrl+C 复制')
    expect(node.querySelectorAll('[data-grid-row]')).not.toHaveLength(0)
  } finally { vi.restoreAllMocks() }
})

it('copies only the visible page and fields after paging and changing columns', async () => {
  const node = await mount()
  await act(async () => button('显示字段 10/10').click())
  for (const checkbox of Array.from(document.querySelectorAll<HTMLInputElement>('.ant-checkbox-group input')).slice(0, 6)) {
    await act(async () => checkbox.click())
  }
  await act(async () => button('显示字段 4/10').click())
  await act(async () => node.querySelector<HTMLElement>('.ant-pagination-item-2')?.click())
  const cell = node.querySelector<HTMLElement>('[data-grid-row="0"][data-grid-column="0"]')!
  cell.focus()
  await act(async () => cell.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', ctrlKey: true, bubbles: true, cancelable: true })))
  const setData = vi.fn()
  const copy = new Event('copy', { bubbles: true, cancelable: true })
  Object.defineProperty(copy, 'clipboardData', { value: { setData } })
  cell.dispatchEvent(copy)
  expect(setData).toHaveBeenCalledWith('text/plain', '2026-07-11\t1006\t1007\t1008\t1009')
})

it('keeps all fields on narrow screens and changes density', async () => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 500, 30))
  const node = await mount()
  expect(node.querySelectorAll('th')).toHaveLength(11)
  expect(node.querySelector('table')?.style.minWidth || node.querySelector('table')?.style.width).toBeTruthy()
  expect(node.querySelector('.ant-table-small')).toBeNull()
  expect(node.querySelector('.ant-segmented-item-selected')?.textContent).toBe('舒适')
  await act(async () => Array.from(node.querySelectorAll('label')).find(label => label.textContent === '紧凑')?.click())
  expect(node.querySelector('.ant-table-small')).not.toBeNull()
})
