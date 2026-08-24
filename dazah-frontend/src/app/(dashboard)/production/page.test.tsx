/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getBatches: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import ProductionHomePage from './page'

const BATCHES = [
  { id: 'b1', batch_no: 'FA-2026-01', product_name: '苯丙氨酸', product_code: 'FA', status: 'in_progress' },
  { id: 'b2', batch_no: 'MC-2026-02', product_name: '霉酚酸', product_code: 'MC', status: 'completed' },
]

describe('ProductionHomePage', () => {
  let root: ReturnType<typeof createRoot>
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

  it('renders the production home page with stats & recent batches', async () => {
    act(() => {
      root.render(<App><ProductionHomePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = container.textContent || ''
    expect(actions.getBatches).toHaveBeenCalled()
    expect(text).toContain('生产')
  })

  it('shows an error when batches fail to load', async () => {
    actions.getBatches.mockResolvedValue({ code: 500, message: '服务错误', data: [] })
    act(() => {
      root.render(<App><ProductionHomePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.getBatches).toHaveBeenCalled()
  })
})