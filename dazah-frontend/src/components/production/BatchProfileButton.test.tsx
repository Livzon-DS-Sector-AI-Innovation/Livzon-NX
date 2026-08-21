/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import BatchProfileButton from './BatchProfileButton'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const PROFILE = {
  seed_culture: { product_name: '霉酚酸', prepare_date: '2026-08-01', tank_yield: 100 },
  fermentation: [
    { fermenter: '1#', product_name: '霉酚酸', entry_date: '2026-08-01', discharge_date: null, status: 'in_progress', tank_yield: 100 },
  ],
  events: [{ id: 1, event_time: '2026-08-01T10:00', event_type: '异常', description: '波动', impact_duration: '1h' }],
  refinery: { broth_receive: [{ id: 1 }], pretreatment: [] },
}

describe('BatchProfileButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('opens modal and renders batch profile sections', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: PROFILE }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><BatchProfileButton batchNo="B-001" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('全貌'))
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('批次全貌')
    expect(text).toContain('菌种制备')
    expect(text).toContain('发酵记录')
  })

  it('shows not-found message when no profile data', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><BatchProfileButton batchNo="B-001" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('全貌'))
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('未找到')
  })
})