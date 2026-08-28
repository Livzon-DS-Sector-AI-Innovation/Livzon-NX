/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getBatches: vi.fn(),
  getMaterialBalance: vi.fn(),
  calculateMaterialBalance: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

import BalancePage from './page'

const BATCHES = [
  { id: 'b-1', batch_no: 'FA-2026-01', product_name: '苯丙氨酸', product_code: 'FA', status: 'in_progress' },
]

const BALANCE = {
  batch_id: 'b-1',
  input_qty: 100,
  output_qty: 95,
  balance_rate: 95,
  min_balance_rate: 95,
}

describe('BalancePage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getBatches.mockResolvedValue({ code: 200, message: 'success', data: BATCHES })
    actions.getMaterialBalance.mockResolvedValue({ code: 200, message: 'success', data: BALANCE })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the material balance page', async () => {
    act(() => {
      root.render(<App><BalancePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = container.textContent || ''
    expect(actions.getBatches).toHaveBeenCalled()
    expect(text).toContain('物料')
  })

  it('shows an error when batches fail to load', async () => {
    actions.getBatches.mockResolvedValue({ code: 500, message: '服务错误', data: [] })
    act(() => {
      root.render(<App><BalancePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.getBatches).toHaveBeenCalled()
  })
})