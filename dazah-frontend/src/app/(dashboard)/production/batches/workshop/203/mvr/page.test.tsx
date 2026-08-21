/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

import MvrPage from './page'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const ITEMS = {
  items: [{ id: 1, 日期: '2026-08-01', 批号: 'FA-MVR-1', '蒸发量(m3)': 10, 备注: '正常运行' }], total: 1,
}

describe('MvrPage', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders MVR ledger table', async () => {
    const fetchMock = (url: string) => {
      if (url.includes('/fa/mvr/list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: ITEMS }))
      }
      if (url.includes('/fa/monthly-averages')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { data: [], columns: [] } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><MvrPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('MVR 浓缩')
    expect(text).toContain('正常运行')
  })
})