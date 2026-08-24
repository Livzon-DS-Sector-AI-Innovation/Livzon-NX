/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DRSheetsSyncButton from './DRSheetsSyncButton'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const SYNC_RESULTS = {
  crude: { created_fl: 2, created_rb: 1, created_st: 3 },
  extraction: { updated_records: 5, updated_inputs: 2 },
  refinement: { error: '连接失败' },
}

describe('DRSheetsSyncButton', () => {
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
      root.render(<App><DRSheetsSyncButton /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('从飞书同步')
  })

  it('calls sync endpoint and shows result tags', async () => {
    const fetchMock = (url: string) => {
      if (url.includes('/dr/sync/trigger')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success',
          data: { results: SYNC_RESULTS, total_created: 6, total_updated: 7 } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><DRSheetsSyncButton /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('从飞书同步'))
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    // 打开弹窗并查找「开始同步」按钮（注意文本可能含空白）
    const syncBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '').includes('开始同步'))
    if (syncBtn) {
      await act(async () => { syncBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('数据源：')
    expect(text).toContain('新建 6')
    expect(text).toContain('更新 7')
    expect(text).toContain('失败: 连接失败')
  })
})