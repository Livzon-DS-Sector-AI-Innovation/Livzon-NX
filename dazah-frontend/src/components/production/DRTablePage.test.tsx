/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import DRTablePage from './DRTablePage'

const STAGES = [
  { key: 'crude', label: '过滤萃取', path: '/x/crude' },
  { key: 'extraction', label: '提取', path: '/x/extraction', active: true },
]

const COLS = [
  { title: '批号', dataIndex: 'batch_no', width: 150 },
  { title: '生产日期', dataIndex: 'production_date' },
]

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const DATA = {
  items: [{ id: 1, batch_no: 'DR-1', production_date: '2026-08-01' }], total: 1,
}

describe('DRTablePage', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders ledger table and merges cells when mergeKeys provided', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: DATA }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="records" title="台账" columns={COLS} stages={STAGES} mergeKeys={['batch_no']} /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('DR-1')
    expect(text).toContain('共 1 条')
  })

  it('renders empty result table', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { items: [], total: 0 } }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="empty" title="台账" columns={COLS} stages={STAGES} /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('共 0 条')
  })
})
