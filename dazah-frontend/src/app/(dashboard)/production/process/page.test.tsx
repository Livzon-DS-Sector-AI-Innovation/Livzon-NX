/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getProcessSpecs: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import ProcessPage from './page'

const SPECS = [
  {
    id: 'ps-1',
    spec_no: 'PS-2026-01',
    product_code: 'FA',
    product_name: '苯丙氨酸',
    status: 'released',
  },
]

describe('ProcessPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getProcessSpecs.mockResolvedValue({
      code: 200, message: 'success', data: SPECS, meta: { total: 1 },
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
    // 重置 zustand store 状态
  })

  it('renders the process specification page', async () => {
    act(() => {
      root.render(<App><ProcessPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = container.textContent || ''
    expect(actions.getProcessSpecs).toHaveBeenCalled()
    expect(text).toContain('工艺')
  })
})