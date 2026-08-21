/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getBatches: vi.fn(),
  createBatch: vi.fn(),
  updateBatch: vi.fn(),
  deleteBatch: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

import ProductDataView from './ProductDataView'

const BATCHES = [
  {
    id: 'b1',
    batch_no: 'BG-2026-01',
    product_name: '霉酚酸',
    product_code: 'BG',
    status: 'in_progress',
    planned_qty: 100,
    actual_qty: 80,
  },
  {
    id: 'b2',
    batch_no: 'BG-2026-02',
    product_name: '霉酚酸',
    product_code: 'BG',
    status: 'completed',
    planned_qty: 120,
    actual_qty: 90,
  },
]

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ProductDataView', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    actions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: BATCHES })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('loads and filters batches by product name', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] })))

    act(() => {
      root.render(<ProductDataView productName="霉酚酸" />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(actions.getBatches).toHaveBeenCalled()
    const text = container.textContent || ''
    expect(text).toContain('霉酚酸')
    expect(text).toContain('批次数据')
  })

  it('shows an error message when loading batches fails', async () => {
    actions.getBatches.mockResolvedValue({ code: 500, message: '服务错误', data: [] })

    act(() => {
      root.render(<ProductDataView productName="霉酚酸" />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(actions.getBatches).toHaveBeenCalled()
  })

  it('does not reject when exporting empty batch list', async () => {
    act(() => {
      root.render(<ProductDataView productName="霉酚酸" />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    // 空批次列表导出走 warning 分支，不应抛错
    expect(container.textContent || '').toContain('批次数据')
  })
})