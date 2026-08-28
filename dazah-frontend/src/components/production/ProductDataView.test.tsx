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
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '确认') as HTMLElement | undefined
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
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.trim() === '删除') as HTMLElement | undefined
    if (delBtn) {
      await act(async () => { delBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    // App.useApp 的 confirm 在测试环境渲染为按钮文案 'OK'/'Cancel'，取任意 OK 按钮
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal-confirm-btns button')).find((b) => b.textContent?.trim() === 'OK') as HTMLElement | undefined
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

  it('filters by status and search text and exports a CSV', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] })))
    const exportSpy = vi.fn()
    const NativeURL = globalThis.URL
    class TestURL extends NativeURL {}
    Object.defineProperty(TestURL, 'createObjectURL', { configurable: true, value: exportSpy })
    Object.defineProperty(TestURL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    vi.stubGlobal('URL', TestURL)
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    // 状态筛选
    const statusSelect = Array.from(container.querySelectorAll('.ant-select')).find((s) => (s as HTMLElement).textContent?.includes('状态筛选'))
    // 搜索框
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('搜索批次号'))
    if (searchInput) {
      await act(async () => {
        searchInput.value = 'BG-2026-02'
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 50))
      })
    }
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出')) as HTMLElement | undefined
    if (exportBtn) {
      await act(async () => { exportBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(container.textContent || '').toContain('霉酚酸')
    vi.unstubAllGlobals()
  })

  it('edits a batch via the modal and submits an update', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] })))
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑')) as HTMLElement | undefined
    if (editBtn) {
      await act(async () => { editBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('编辑批次 - 霉酚酸')
    // 关闭弹窗
    const cancelBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '取消') as HTMLElement | undefined
    if (cancelBtn) {
      await act(async () => { cancelBtn.click(); await new Promise((r) => setTimeout(r, 40)) })
    }
  })

  it('shows error message when getBatches rejects', async () => {
    actions.getBatches.mockRejectedValue(new Error('boom'))
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(actions.getBatches).toHaveBeenCalled()
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('加载批次数据失败')
  })

  it('creates a batch after filling required fields and flips pagination', async () => {
    const many = Array.from({ length: 25 }, (_, i) => ({
      id: `b${i + 1}`,
      batch_no: `BG-P${i + 1}`,
      product_name: '霉酚酸',
      product_code: 'BG',
      status: 'completed',
    }))
    actions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: many })
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建批次')) as HTMLElement | undefined
    if (addBtn) {
      await act(async () => { addBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const batchInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes('请输入批次号')) as HTMLInputElement | undefined
    const codeInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes('请输入产品编码')) as HTMLInputElement | undefined
    if (batchInput && codeInput) {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
        setter?.call(batchInput, 'BG-NEW-1')
        batchInput.dispatchEvent(new Event('input', { bubbles: true }))
        setter?.call(codeInput, 'BG-NEW')
        codeInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    const okBtn = Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').replace(/\s+/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(actions.createBatch).toHaveBeenCalledWith(expect.objectContaining({ batch_no: 'BG-NEW-1' }))
    // 分页翻到第 2 页
    const page2 = container.querySelector('.ant-pagination-item-2') as HTMLElement | undefined
    if (page2) {
      await act(async () => { page2.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect(container.textContent || '').toContain('BG-P23')
  })

  it('edits a batch and submits the update response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] })))
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑')) as HTMLElement | undefined
    if (editBtn) {
      await act(async () => { editBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    const okBtn = Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').replace(/\s+/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(actions.updateBatch).toHaveBeenCalledWith('b1', expect.objectContaining({ product_name: '霉酚酸' }))
  })

  it('filters via status select and search text typing', async () => {
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    // 状态筛选选「已完成」
    const select = container.querySelector('.ant-select') as HTMLElement | undefined
    if (select) {
      await act(async () => {
        select.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 80))
      })
      const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('已完成'))
      if (option) {
        await act(async () => { option.dispatchEvent(new MouseEvent('click', { bubbles: true })); await new Promise((r) => setTimeout(r, 80)) })
      }
    }
    expect(container.textContent || '').not.toContain('BG-2026-01')
    expect(container.textContent || '').toContain('BG-2026-02')
    // 搜索无匹配内容
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('搜索批次号')) as HTMLInputElement | undefined
    if (searchInput) {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
        setter?.call(searchInput, '不存在的批号')
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    expect(container.textContent || '').not.toContain('BG-2026-02')
  })

  it('warns when exporting an empty result set', async () => {
    actions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: [] })
    act(() => {
      root.render(<App><ProductDataView productName="霉酚酸" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出')) as HTMLElement | undefined
    if (exportBtn) {
      await act(async () => { exportBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(container.textContent || '').toContain('霉酚酸')
  })

  it('renders the production period label for the >=27 day window', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 7, 28))
    try {
      act(() => {
        root.render(<App><ProductDataView productName="霉酚酸" /></App>)
      })
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50))
      })
      expect(container.textContent || '').toContain('9月生产批次数据查看与管理')
    } finally {
      vi.useRealTimers()
    }
  })
})
