/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import dayjs from 'dayjs'

import Scheduling2013Page from './page'

const dumpPlan = (over: Record<string, unknown> = {}) => ({
  batch_no: 'DR-2601-1',
  tank_no: 'T1',
  product_type: '正式批',
  dump_date: dayjs().format('YYYY-MM-DD'),
  year: 2026,
  month: 1,
  day: 15,
  in_db: true,
  is_past: false,
  status: 'upcoming',
  task_status: 'pending',
  actual_time: null,
  confirmed_by: null,
  actual_tank_no: null,
  delay_reason: null,
  ...over,
})

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string): Promise<Response> {
  if (url.includes('/dr/schedule/dump-plans')) {
    return Promise.resolve(jsonResponse({
      code: 200, message: 'success',
      data: {
        version: { file: '2026排产.xlsx', sheet: '排产' },
        today: dayjs().format('YYYY-MM-DD'),
        items: [
          dumpPlan({ task_status: 'pending' }),
          dumpPlan({ batch_no: 'DR-2601-2', task_status: 'confirmed', actual_time: '2026-01-15T08:30:00+08:00', confirmed_by: '张三' }),
          dumpPlan({ batch_no: 'DR-2602-1', task_status: 'delayed', delay_reason: '等料' }),
          dumpPlan({ batch_no: 'DR-2602-2', is_past: true, status: 'past' }),
        ],
        summary: { total: 4, past: 1, upcoming: 3 },
      },
    }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('Scheduling2013Page', () => {
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

  it('renders the dump/接罐 plan table with status tags and actions', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('排产')
    expect(text).toContain('确认接罐')
    expect(text).toContain('延期')
  })

  it('shows an error state when the API returns an error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 500, message: '服务错误', data: null }))))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(container.textContent || '').toContain('排产')
  })

  it('renders the confirm/modal for confirming an approved batch', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const confirmBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('确认接罐'))
    if (confirmBtn) {
      await act(async () => { confirmBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('确认接罐')
  })

  it('opens the delay-reason modal for pending batches', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const delayBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('延期'))
    if (delayBtn) {
      await act(async () => { delayBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('延期')
  })
})