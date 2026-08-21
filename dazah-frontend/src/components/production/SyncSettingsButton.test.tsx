/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SyncSettingsButton from './SyncSettingsButton'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function plainFetchConfigs(url: string): Promise<Response> {
  if (url.includes('/feishu-configs')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('SyncSettingsButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('opens settings modal and renders config form', async () => {
    vi.stubGlobal('fetch', vi.fn(plainFetchConfigs))

    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    const textBody = (container.textContent || '') + (document.body.textContent || '')
    expect(textBody).toContain('飞书同步设置')
  })
})