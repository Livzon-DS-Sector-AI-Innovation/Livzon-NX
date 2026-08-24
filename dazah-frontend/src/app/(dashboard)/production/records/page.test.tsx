/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getBatches: vi.fn(),
  getProductionRecords: vi.fn(),
  createProductionRecord: vi.fn(),
  updateProductionRecord: vi.fn(),
  deleteProductionRecord: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import RecordsPage from './page'

const BATCHES = [
  { id: 'b-1', batch_no: 'B-2026-01', product_name: '霉酚酸' },
]

const RECORDS = [
  {
    id: 'rec-1',
    batch_id: 'b-1',
    operation_type: '投料',
    operation_name: '投入粗品',
    operator: '张三',
  },
]

describe('RecordsPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: BATCHES })
    actions.getProductionRecords.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the production records page', async () => {
    act(() => {
      root.render(<App><RecordsPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = container.textContent || ''
    expect(actions.getBatches).toHaveBeenCalled()
    expect(text).toContain('生产记录')
  })

  it('shows an error message when loading batches fails', async () => {
    actions.getBatches.mockResolvedValue({ code: 500, message: '服务错误', data: [] })
    act(() => {
      root.render(<App><RecordsPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.getBatches).toHaveBeenCalled()
  })
})