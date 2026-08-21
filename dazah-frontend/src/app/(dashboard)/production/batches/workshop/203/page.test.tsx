/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

import Workshop203Page from './page'

const SUMMARY = {
  stages: { acidification: { count: 2 } },
  status_distribution: [{ status: 'in_progress', color: '#1890ff', count: 1 }],
  monthly_trend: [{ month: 7, output_kg: 100 }],
  rrt_pass_rates: [],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string) {
  if (url.includes('/fa/dashboard/summary')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: SUMMARY }))
  }
  if (url.includes('/fa/dashboard/yield-chain')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { stages: [], summary: null } }))
  }
  if (url.includes('/fa/dashboard/golden-batches')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { batches: [], scores: {} } }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('Workshop203Page', () => {
  let root: ReturnType<typeof createRoot>
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

  it('renders the 203 workshop dashboard', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<Workshop203Page />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })

    const text = container.textContent || ''
    expect(text).toContain('203')
    expect(text).toContain('苯丙氨酸')
  })
})
