/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WorkbookReport } from '@/lib/api/energy-ledger'

const query = vi.hoisted(() => ({ data: undefined as WorkbookReport | undefined, error: undefined as Error | undefined, refetch: vi.fn() }))
const access = vi.hoisted(() => ({ canImport: false }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (selector: (state: { hasPagePermission: () => boolean }) => boolean) => selector({ hasPagePermission: () => access.canImport }) }))
vi.mock('./EnergyWorkbookImport', () => ({ EnergyWorkbookImport: ({ year }: { year: number }) => <div>导入年份：{year}</div> }))
vi.mock('@tanstack/react-query', () => ({ useQuery: (options: { queryKey: string[] }) => options.queryKey[1] === 'workbook' ? query : {} }))

import { EnergyWorkbookClient } from './EnergyWorkbookClient'

afterEach(() => { query.data = undefined; query.error = undefined; query.refetch.mockReset(); access.canImport = false; document.body.innerHTML = '' })

describe('monthly original workbook views', () => {
  it.each([false, true])('retains pending originals and the reason in both appearances (dark=%s)', async dark => {
    query.data = { year: 2026, month: 7, dataset: '冰水量', available_count: 0, expected_count: 1,
      columns: [{ key: '14', label: '新北江发酵7°', unit: 'm³', quantity_kind: 'volume', value_kind: 'usage' }],
      rows: [{ date: '2026-07-26', cells: { '14': { value: null, calculated_value: '2049315', status: 'pending_review', provenance: { review: [{ reason: '底码跳变与手填冲突', source: '飞书N31', reported_value: '28674' }] } } } }],
    }
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkbookClient year={2026} month={7} dataset="冰水量" /></App></ConfigProvider>))
    expect(node.textContent).toContain('待确认')
    expect(node.textContent).toContain('原表值：28674')
    expect(node.textContent).toContain('系统计算值：2049315')
    expect(node.textContent).toContain('底码跳变与手填冲突；飞书N31')
    await act(async () => root.unmount())
  })
  it('hydrates exports before displaying the authorized import button', async () => {
    access.canImport = true
    const node = document.createElement('div'); document.body.append(node)
    const content = <App><EnergyWorkbookClient year={2026} month={7} dataset="日总量" /></App>
    node.innerHTML = renderToString(content)
    expect(node.textContent).not.toContain('导入 Excel')
    const recoverableError = vi.fn()
    let root: ReturnType<typeof hydrateRoot> | undefined
    await act(async () => { root = hydrateRoot(node, content, { onRecoverableError: recoverableError }) })
    expect(recoverableError).not.toHaveBeenCalled()
    expect(node.textContent).toContain('导入 Excel')
    await act(async () => root?.unmount())
  })
  it.each([false, true])('removes the persistent notice and opens imports only for authorized users (allowed=%s)', async allowed => {
    access.canImport = allowed
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyWorkbookClient year={2026} month={7} dataset="日总量" /></App>))
    expect(node.textContent).not.toContain('按原表逐日查看')
    expect(node.querySelector('[role=alert]')).toBeNull()
    const button = Array.from(node.querySelectorAll('button')).find(item => item.textContent?.replaceAll(' ', '') === '导入Excel')
    expect(Boolean(button)).toBe(allowed)
    if (button) {
      await act(async () => button.click())
      expect(document.querySelector('[role=dialog]')?.textContent).toContain('导入年份：2026')
    }
    await act(async () => root.unmount())
  })
  it('distinguishes zero from blank values and keeps the export month', async () => {
    query.data = { year: 2026, month: 7, dataset: '饮用水码', columns: [{ key: '2', label: '101水表', unit: 'm3', value_kind: 'reading', quantity_kind: 'volume' }], rows: [{ date: '2026-07-01', cells: { '2': { value: '0', status: 'complete' } } }, { date: '2026-07-02', cells: { '2': { value: null, status: 'missing_reading' } } }, { date: '2026-07-03', cells: { '2': { value: null, status: 'unconfigured' } } }], available_count: 1, expected_count: 3 }
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyWorkbookClient year={2026} month={7} dataset="饮用水码" /></App>))
    expect(node.textContent).toContain('已取得 1/3 项')
    expect(Array.from(node.querySelectorAll('td')).filter(cell => cell.textContent === '—')).toHaveLength(2)
    expect(Array.from(node.querySelectorAll('td')).some(cell => cell.textContent === '0')).toBe(true)
    const exports = Array.from(node.querySelectorAll('a')).map(link => link.getAttribute('href'))
    expect(exports).toContain('/api/v1/energy/reporting/workbook/export?year=2026&month=7')
    expect(exports.some(url => url?.includes('dataset=%E9%A5%AE%E7%94%A8%E6%B0%B4%E7%A0%81'))).toBe(true)
    await act(async () => root.unmount())
  })
  it.each([false, true])('shows original field names and plain values without evidence interactions (dark=%s)', async dark => {
    query.data = { year: 2026, month: 7, dataset: '日总量', columns: [
      { key: '2', label: '锅炉产气量', unit: '原表数值单位', value_kind: 'usage', quantity_kind: 'volume' },
      { key: '3', label: '外供蒸汽占比', unit: '比例', value_kind: 'usage', quantity_kind: 'ratio' },
    ], rows: [{ date: '2026-07-01', cells: {
      '2': { value: '1106.00000000', status: 'complete', trace_id: 'trace-1' },
      '3': { value: '0', status: 'adjusted', reading_id: 'reading-1' },
    } }], available_count: 2, expected_count: 2 }
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyWorkbookClient year={2026} month={7} dataset="日总量" /></App></ConfigProvider>))
    expect(Array.from(node.querySelectorAll('th')).map(cell => cell.textContent)).toEqual(['日期', '锅炉产气量', '外供蒸汽占比'])
    expect(Array.from(node.querySelectorAll('tr[data-row-key] td')).map(cell => cell.textContent)).toEqual(['2026-07-01', '1106', '0'])
    expect(node.querySelectorAll('td button, td a, td .ant-tag')).toHaveLength(0)
    await act(async () => node.querySelector('tr[data-row-key] td:nth-child(2)')?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(document.body.textContent).not.toContain('原表数据依据')
    expect(node.textContent).not.toContain('原表数值单位')
    await act(async () => root.unmount())
  })
  it('shows denied access and keeps an explicit retry', async () => {
    query.error = new Error('无权查询该计量范围')
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyWorkbookClient year={2026} month={7} dataset="饮用水码" /></App>))
    expect(node.textContent).toContain('无权查询该计量范围')
    const retry = Array.from(node.querySelectorAll('button')).find(button => button.textContent?.replaceAll(' ', '') === '重试')
    await act(async () => retry?.click())
    expect(query.refetch).toHaveBeenCalledOnce()
    await act(async () => root.unmount())
  })
})
