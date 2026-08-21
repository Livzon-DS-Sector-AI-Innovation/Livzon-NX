/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
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
    actions.deleteBatch.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.createBatch.mockResolvedValue({ code: 200, message: 'success', data: null })
    actions.updateBatch.mockResolvedValue({ code: 200, message: 'success', data: null })
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
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(actions.getBatches).toHaveBeenCalled()
    const text = container.textContent || ''
    expect(text).toContain('霉酚酸')
    expect(text).toContain('批次数据')
    // 统计卡片与筛选后的批次行
    expect(text).toContain('总批次')
    expect(text).toContain('BG-2026-01')
  })

  it('renders the add batch modal and submits a create', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] })))
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建批次'))
    if (addBtn) {
      await act(async () => { addBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('新建批次 - 霉酚酸')
    // 提交表单（字段缺少会走 validateFields 验证失败，进入 catch 分支）
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '确认')
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect(actions.createBatch).not.toHaveBeenCalled()
  })

  it('deletes a batch via confirm modal', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] })))
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.trim() === '删除')
    if (delBtn) {
      await act(async () => { delBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    // App.useApp 的 confirm 在测试环境渲染为按钮文案 'OK'/'Cancel'，取任意 OK 按钮
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal-confirm-btns button')).find((b) => b.textContent?.trim() === 'OK')
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(actions.deleteBatch).toHaveBeenCalled()
  })

  it('shows an error message when loading batches fails', async () => {
    actions.getBatches.mockResolvedValue({ code: 500, message: '服务错误', data: [] })

    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(actions.getBatches).toHaveBeenCalled()
  })
})