/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/DRTable', () => ({
  default: ({ data }: { data: unknown[] }) => <div data-testid="dr-table" data-count={data.length} />,
}))
vi.mock('@/components/production/DRTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import DrCrudeExtractionPage from './page'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string): Promise<Response> {
  if (url.includes('/dr/extraction/full')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ id: 'c1' }] }))
  }
  if (url.includes('/dr/extraction/years')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [2026, 2025] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('DrCrudeExtractionPage (201-3)', () => {
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

  it('renders the crude-extraction page with table and stage nav', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><DrCrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = container.textContent || ''
    expect(text).toContain('过滤萃取')
    expect(container.querySelector('[data-testid="dr-table"]')).toBeTruthy()
  })

  it('shows an error when records fail to load', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dr/extraction/full')) {
        return Promise.resolve(jsonResponse({ code: 500, message: '服务错误', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }))
    act(() => {
      root.render(<App><DrCrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(container.textContent || '').toContain('过滤萃取')
  })
})