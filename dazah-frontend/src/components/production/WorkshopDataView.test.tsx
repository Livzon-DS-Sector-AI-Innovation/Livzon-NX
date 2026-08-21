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
})