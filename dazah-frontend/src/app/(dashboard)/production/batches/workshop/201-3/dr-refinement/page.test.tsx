/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/DRRefinementTable', () => ({
  default: ({ data }: { data: unknown[] }) => <div data-testid="dr-refinement-table" data-count={data.length} />,
}))
vi.mock('@/components/production/DRTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import DrRefinementPage from './page'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string): Promise<Response> {
  if (url.includes('/dr/records?')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { items: [{ id: 'd1' }], total: 1 } }))
  }
  if (url.includes('/dr/records/years')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [2026, 2025] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('DrRefinementPage (201-3)', () => {
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
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders the DR refinement page with table and stage nav', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><DrRefinementPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = container.textContent || ''
    expect(text).toContain('一次精制')
    expect(container.querySelector('[data-testid="dr-refinement-table"]')).toBeTruthy()
  })

  it('shows an error when records fail to load', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dr/records?')) {
        return Promise.resolve(jsonResponse({ code: 500, message: '服务错误', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }))
    act(() => {
      root.render(<App><DrRefinementPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(container.textContent || '').toContain('一次精制')
  })
})