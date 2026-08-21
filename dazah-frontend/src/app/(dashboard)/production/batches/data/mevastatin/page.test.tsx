/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({ getBatches: vi.fn() }))
vi.mock('@/actions/production', () => actions)

import {comp} from './page'

const BATCHES = [
  { id: 'b1', batch_no: 'BG-2026-01', product_name: '美伐他汀', product_code: 'BG', status: 'in_progress' },
]

describe('MevastatinPage (data)', () => {
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
  it('renders the product data page', async () => {
    act(() => root.render(<App><MevastatinPage /></App>))
    await act(async () => { await new Promise((r) => setTimeout(r, 60)) })
    expect(actions.getBatches).toHaveBeenCalled()
    expect(container.textContent || '').toContain('美伐他汀')
  })
})
