/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import BatchEventsButton from './BatchEventsButton'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const EVENTS = [
  { id: 1, event_time: '2026-08-01T10:00:00', workshop: '103车间', event_type: '染菌', description: '大肠杆菌', impact_scope: '本罐', action_taken: '消毒', restore_time: '2026-08-01T12:00:00', impact_duration: '2h' },
]

describe('BatchEventsButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders null when status is not in_progress', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><BatchEventsButton batchId="b1" batchLabel="批次" status="completed" /></App>)
    })
    expect(container.textContent || '').not.toContain('异常')
  })

  it('opens modal and shows event details for in_progress', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: EVENTS }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><BatchEventsButton batchId="b1" batchLabel="批次" status="in_progress" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('异常'))
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('运行期间异常事件')
    expect(text).toContain('大肠杆菌')
  })
})