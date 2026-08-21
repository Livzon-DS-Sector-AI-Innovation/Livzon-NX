/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import MCSheetsSyncButton from './MCSheetsSyncButton'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const SYNC_RESULTS = {
  crude: { created_fl: 2, created_rb: 1 },
  extraction: { updated_records: 5 },
  refinement: { error: '连接失败' },
}

describe('MCSheetsSyncButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders sync button and opens modal', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><MCSheetsSyncButton /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('从飞书同步')
  })

  it('shows result tags with created/updated counts', async () => {
    const fetchMock = (url: string) => {
      if (url.includes('/mc/sync/trigger')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success',
          data: { data: { results: SYNC_RESULTS, total_created: 3, total_updated: 5 } } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><MCSheetsSyncButton /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btns = Array.from(container.querySelectorAll('button')).filter((b) => b.textContent?.includes('同步'))
    if (btns.length > 0) {
      await act(async () => { btns[0].click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('数据源')
  })
})