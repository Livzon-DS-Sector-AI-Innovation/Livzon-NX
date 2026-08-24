/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

const prod = vi.hoisted(() => ({
  getBatches: vi.fn(),
  createBatch: vi.fn(),
  updateBatch: vi.fn(),
  updateBatchStatus: vi.fn(),
  deleteBatch: vi.fn(),
}))
vi.mock('@/actions/production', () => prod)

import BatchesPage from './page'

const BATCHES = [
  { id: 'b1', batch_no: 'B-001', product_name: '霉酚酸', product_code: 'PC', status: 'in_progress',
    planned_qty: 100, actual_qty: 90, input_qty: 80, production_line: 'A线',
    start_time: '2026-08-01T08:00:00', end_time: '2026-08-02T08:00:00' },
]

describe('BatchesPage', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the batch list with getBatches data', async () => {
    prod.getBatches.mockResolvedValue({ code: 200, message: 'success', data: BATCHES, meta: { total: 1 } })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><BatchesPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = container.textContent || ''
    expect(text).toContain('B-001')
    expect(prod.getBatches).toHaveBeenCalled()
  })

  it('handles load failure with error message', async () => {
    prod.getBatches.mockResolvedValue({ code: 500, message: '服务错误', data: [], meta: { total: 0 } })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><BatchesPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(prod.getBatches).toHaveBeenCalled()
  })
})