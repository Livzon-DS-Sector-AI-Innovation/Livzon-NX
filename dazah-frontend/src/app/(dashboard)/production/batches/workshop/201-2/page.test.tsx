/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/SyncSettingsButton', () => ({
  default: () => <button>同步设置</button>,
}))
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

import Workshop2012Page from './page'

const SUMMARY = {
  stages: { sub_tank: { count: 3 } },
  status_distribution: [
    { status: 'in_progress', color: '#1890ff', count: 2 },
    { status: 'completed', color: '#52c41a', count: 1 },
  ],
  monthly_trend: [
    { month: 1, output_kg: 100 },
    { month: 2, output_kg: 120 },
  ],
  rrt_pass_rates: [
    { label: 'RRT=0.53', field: 'rrt_053', limit: 0.05, total: 5, passed: 5, rate: 100 },
  ],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('Workshop2012Page', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders the dashboard summary with batch status distribution', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: SUMMARY })))
    )

    act(() => {
      root.render(<Workshop2012Page />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('二车间')
    expect(text).toContain('批次状态')
    expect(text).toContain('in_progress')
    expect(text).toContain('completed')
  })
})
