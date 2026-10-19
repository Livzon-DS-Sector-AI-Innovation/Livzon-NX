/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WorkbookReport } from '@/lib/api/energy-ledger'

const query = vi.hoisted(() => ({ data: undefined as WorkbookReport | undefined, error: undefined as Error | undefined, refetch: vi.fn() }))
vi.mock('@tanstack/react-query', () => ({ useQuery: (options: { queryKey: string[] }) => options.queryKey[1] === 'workbook' ? query : {} }))

import { EnergyWorkbookClient } from './EnergyWorkbookClient'

afterEach(() => { query.data = undefined; query.error = undefined; query.refetch.mockReset(); document.body.innerHTML = '' })

describe('monthly original workbook views', () => {
  it('distinguishes zero, missing and unconfirmed configuration and keeps the export month', async () => {
    query.data = { year: 2026, month: 7, dataset: '饮用水码', columns: [{ key: '2', label: '101水表', unit: 'm3', value_kind: 'reading', quantity_kind: 'volume' }], rows: [{ date: '2026-07-01', cells: { '2': { value: '0', status: 'complete' } } }, { date: '2026-07-02', cells: { '2': { value: null, status: 'missing_reading' } } }, { date: '2026-07-03', cells: { '2': { value: null, status: 'unconfigured' } } }], available_count: 1, expected_count: 3 }
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyWorkbookClient year={2026} month={7} dataset="饮用水码" /></App>))
    expect(node.textContent).toContain('已取得 1/3 项')
    expect(node.textContent).toContain('缺少读数')
    expect(node.textContent).toContain('待确认配置')
    expect(Array.from(node.querySelectorAll('td')).some(cell => cell.textContent === '0')).toBe(true)
    const exports = Array.from(node.querySelectorAll('a')).map(link => link.getAttribute('href'))
    expect(exports).toContain('/api/v1/energy/reporting/workbook/export?year=2026&month=7')
    expect(exports.some(url => url?.includes('dataset=%E9%A5%AE%E7%94%A8%E6%B0%B4%E7%A0%81'))).toBe(true)
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
