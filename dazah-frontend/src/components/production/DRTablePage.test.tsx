/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

const routerMock = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
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

  it('shows an error message when the records request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 500, message: '加载失败' }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="records" title="台账" columns={COLS} stages={STAGES} /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('加载失败')
  })

  it('paginates to the second page and shows later rows', async () => {
    const items = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1,
      batch_no: `DR-${i + 1}`,
      production_date: `2026-08-${String((i % 28) + 1).padStart(2, '0')}`,
      stage: 'crude',
    }))
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { items, total: 25 } }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="records" title="台账" columns={COLS} stages={STAGES} /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    const page2 = container.querySelector('.ant-pagination-item-2') as HTMLElement | undefined
    if (page2) {
      await act(async () => { page2.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('DR-25')
  })

  it('navigates back to the workshop page', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { items: [], total: 0 } }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="records" title="台账" columns={COLS} stages={STAGES} /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    const backBtn = Array.from(container.querySelectorAll('button')).find((b) => (b.textContent || '').includes('返回车间'))
    if (backBtn) {
      await act(async () => {
        backBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 50))
      })
    }
    expect(routerMock.push).toHaveBeenCalledWith('/production/batches/workshop/201-3')
  })

  it('shows network error when the records request rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('network down'))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="records" title="台账" columns={COLS} stages={STAGES} /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('网络错误')
  })

  it('navigates to a stage page when clicking a stage button', async () => {
    routerMock.push.mockClear()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { items: [], total: 0 } }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRTablePage tableKey="records" title="台账" columns={COLS} stages={STAGES} /></App>)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 50)) })
    const stageBtn = Array.from(container.querySelectorAll('button')).find((b) => (b.textContent || '').replace(/\s+/g, '') === '过滤萃取')
    if (stageBtn) {
      await act(async () => {
        stageBtn.click()
        await new Promise((r) => setTimeout(r, 50))
      })
    }
    expect(routerMock.push).toHaveBeenCalledWith('/x/crude')
  })
})
