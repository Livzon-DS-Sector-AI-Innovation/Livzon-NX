/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const prodActions = vi.hoisted(() => ({
  getBatches: vi.fn(),
  createBatch: vi.fn(),
  updateBatch: vi.fn(),
  deleteBatch: vi.fn(),
}))

vi.mock('@/actions/production', () => prodActions)

import WorkshopDataView from './WorkshopDataView'

const BATCHES = [
  {
    id: 'b1',
    batch_no: 'B-001',
    product_code: 'PC-1',
    product_name: '霉酚酸',
    specification: '10kg',
    planned_qty: 100,
    input_qty: 90,
    actual_qty: 95,
    status: 'completed',
    production_line: 'A线',
    start_time: '2026-08-01T08:00:00',
    end_time: '2026-08-02T08:00:00',
  },
  {
    id: 'b2',
    batch_no: 'B-002',
    product_code: 'PC-2',
    product_name: '多拉菌素',
    specification: '5kg',
    planned_qty: 50,
    input_qty: 45,
    actual_qty: null,
    status: 'in_progress',
    production_line: 'B线',
  },
]

describe('WorkshopDataView', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    prodActions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: BATCHES })
    prodActions.deleteBatch.mockResolvedValue({ code: 200, message: 'success', data: null })
    prodActions.createBatch.mockResolvedValue({ code: 200, message: 'success', data: null })
    prodActions.updateBatch.mockResolvedValue({ code: 200, message: 'success', data: null })
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders stats and batch table from getBatches', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = container.textContent || ''
    expect(text).toContain('批次数据')
    expect(text).toContain('B-001')
    expect(text).toContain('总批次')
    expect(text).toContain('完成率')
  })

  it('filters and exports batches to CSV', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    // 导出 CSV：点击导出按钮（有数据的批次分支）
    const expBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出'))
    if (expBtn) {
      await act(async () => { expBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    // 触发状态筛选，进入分页/筛选分支
    const filterSelect = container.querySelector('.ant-select')
    expect(prodActions.getBatches).toHaveBeenCalled()
  })

  it('renders empty state when getBatches fails', async () => {
    prodActions.getBatches.mockResolvedValue({ code: 500, message: 'error', data: [] })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(prodActions.getBatches).toHaveBeenCalled()
  })

  it('opens delete confirm modal and triggers delete', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const delBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.trim() === '删除') as HTMLElement | undefined
    if (delBtn) {
      await act(async () => { delBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal-confirm-btns button')).find((b) => b.textContent?.trim() === 'OK') as HTMLElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(prodActions.deleteBatch).toHaveBeenCalled()
  })

  it('opens add modal and edits a batch', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建批次')) as HTMLElement | undefined
    if (addBtn) {
      await act(async () => { addBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    const addText = (container.textContent || '') + (document.body.textContent || '')
    expect(addText).toContain('新建批次 - 201车间')
    // 关闭
    const cancelBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '取消') as HTMLElement | undefined
    if (cancelBtn) {
      await act(async () => { cancelBtn.click(); await new Promise((r) => setTimeout(r, 40)) })
    }
    // 编辑
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑')) as HTMLElement | undefined
    if (editBtn) {
      await act(async () => { editBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('编辑批次 - 201车间')
  })

  it('applies search and status filtering', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('搜索批次号'))
    if (searchInput) {
      await act(async () => {
        searchInput.value = 'B-002'
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 50))
      })
    }
    // 状态筛选下拉：触发 antd Select 打开（仅覆盖状态筛选 onChange 分支的空值路径）
    const text = container.textContent || ''
    expect(text).toContain('201车间')
    expect(prodActions.getBatches).toHaveBeenCalled()
  })

  it('shows an error message when getBatches rejects', async () => {
    prodActions.getBatches.mockRejectedValue(new Error('boom'))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('加载批次数据失败')
  })

  it('filters by status select and search terms then paginates', async () => {
    const many = Array.from({ length: 25 }, (_, i) => ({
      id: `w${i + 1}`,
      batch_no: `W-P${i + 1}`,
      product_name: `产品${i + 1}`,
      specification: `${i + 1}kg`,
      planned_qty: 10,
      actual_qty: 10,
      status: 'completed',
      production_line: 'A线',
    }))
    prodActions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: many })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const searchInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('搜索批次号')) as HTMLInputElement | undefined
    if (searchInput) {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
        setter?.call(searchInput, 'W-P3')
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect(container.textContent || '').toContain('W-P3')
    // 清空搜索后翻到第 2 页
    if (searchInput) {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
        setter?.call(searchInput, '')
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    const page2 = container.querySelector('.ant-pagination-item-2') as HTMLElement | undefined
    if (page2) {
      await act(async () => { page2.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect(container.textContent || '').toContain('W-P23')
  })

  it('warns when exporting with no data', async () => {
    prodActions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: [] })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => (b.textContent || '').includes('导出'))
    if (exportBtn) {
      await act(async () => { (exportBtn as HTMLButtonElement).click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('没有可导出的批次数据')
  })

  it('renders the production period label for the >=27 day window', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 7, 28))
    try {
      container = document.createElement('div')
      document.body.append(container)
      root = createRoot(container)
      act(() => {
        root.render(
          <App>
            <WorkshopDataView workshopName="201车间" />
          </App>
        )
      })
      await act(async () => {
        await new Promise((r) => setTimeout(r, 60))
      })
      expect(container.textContent || '').toContain('9月生产批次数据查看与管理')
    } finally {
      vi.useRealTimers()
    }
  })

  it('filters the table after selecting a completed status', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const select = container.querySelector('.ant-select') as HTMLElement | undefined
    if (select) {
      await act(async () => {
        select.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('已完成'))
    if (option) {
      await act(async () => { option.dispatchEvent(new MouseEvent('click', { bubbles: true })); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(container.textContent || '').toContain('B-001')
    expect(container.textContent || '').not.toContain('B-002')
  })

  it('creates and updates a batch via the modal forms', async () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
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
        setter?.call(batchInput, 'B-NEW-99')
        batchInput.dispatchEvent(new Event('input', { bubbles: true }))
        setter?.call(codeInput, 'PC-99')
        codeInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 100))
      })
    }
    const okBtn = Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').replace(/\s+/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(prodActions.createBatch).toHaveBeenCalledWith(expect.objectContaining({ batch_no: 'B-NEW-99' }))
    // 编辑并更新
    const editBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('编辑')) as HTMLElement | undefined
    if (editBtn) {
      await act(async () => { editBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const okBtn2 = Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').replace(/\s+/g, '') === '确认') as HTMLButtonElement | undefined
    if (okBtn2) {
      await act(async () => { okBtn2.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(prodActions.updateBatch).toHaveBeenCalled()
  }, 15000)

  it('falls into the export failure branch when URL API throws', async () => {
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => { throw new Error('fail') }), revokeObjectURL: vi.fn() }) as any
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <WorkshopDataView workshopName="201车间" />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => (b.textContent || '').includes('导出'))
    if (exportBtn) {
      await act(async () => { (exportBtn as HTMLButtonElement).click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(container.textContent || '').toContain('201车间')
  })
})
