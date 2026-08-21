/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))


import PlateRecoveryPage from './page'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const ROWS = {
  items: [{ id: 1, 日期: '2026-08-01', 批号: 'FA-1', 备注: '正常' }], total: 1,
}

describe('PlateRecoveryPage', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders the plate-recovery ledger with row data and avg panel', async () => {
    const fetchMock = (url: string) => {
      if (url.includes('/fa/') && url.includes('/list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: ROWS }))
      }
      if (url.includes('/fa/monthly-averages')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { data: [{ 月份: '2026-08' }], columns: ['月份'] } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><PlateRecoveryPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('共 1 条')
    expect(text).toContain('共 1 条')
  })
})
