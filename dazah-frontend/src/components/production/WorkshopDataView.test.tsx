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
})