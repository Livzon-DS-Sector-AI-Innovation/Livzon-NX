/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getShiftHandovers: vi.fn(),
  createShiftHandover: vi.fn(),
  updateShiftHandover: vi.fn(),
  deleteShiftHandover: vi.fn(),
  confirmShiftHandover: vi.fn(),
  getDistinctPositions: vi.fn(),
}))

vi.mock('@/actions/shift-handover', () => actions)

import ShiftHandoverPage from './page'

const RECORDS = [
  {
    id: 'sh-1',
    shift_date: '2026-03-01',
    position: '发酵主操',
    workshop: '101车间',
    handover_from: '张三',
    handover_to: '李四',
    schedule_mode: '4-3',
    summary: '正常交班',
    status: 'pending',
  },
]

describe('ShiftHandoverPage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getShiftHandovers.mockResolvedValue({ code: 200, message: 'success', data: RECORDS })
    actions.getDistinctPositions.mockResolvedValue({ code: 200, message: 'success', data: ['发酵主操'] })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders handover records with position filter', async () => {
    act(() => {
      root.render(<ShiftHandoverPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('交接')
    expect(text).toContain('张三')
    expect(text).toContain('李四')
    expect(text).toContain('发酵主操')
    expect(actions.getShiftHandovers).toHaveBeenCalled()
    expect(actions.getDistinctPositions).toHaveBeenCalled()
  })
})
