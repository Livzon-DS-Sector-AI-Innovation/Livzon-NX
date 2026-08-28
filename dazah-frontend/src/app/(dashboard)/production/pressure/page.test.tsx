/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getPressureDashboard: vi.fn(),
  getMergedPressureRecords: vi.fn(),
}))

vi.mock('@/actions/pressure', () => actions)
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import PressurePage from './page'

const DASHBOARD = {
  total_points: 8,
  total_records_today: 120,
  alarm_count: 2,
  last_import_time: '2026-08-21 08:00',
}

describe('PressurePage', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    actions.getPressureDashboard.mockResolvedValue({ code: 200, message: 'success', data: DASHBOARD })
    actions.getMergedPressureRecords.mockResolvedValue({ code: 200, message: 'success', data: [] })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the pressure dashboard page', async () => {
    act(() => {
      root.render(<App><PressurePage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.getPressureDashboard).toHaveBeenCalled()
    expect(container.textContent || '').toContain('压差')
  })
})