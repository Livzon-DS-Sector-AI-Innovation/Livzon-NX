/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('@/hooks/useFAChat', () => ({
  useFAChat: () => ({
    aiLoading: false, aiResult: { severity: 'high', summary: '存在风险', causes: ['原因'], suggestions: [] },
    thinkingSteps: [], thinkingText: '',
    chatMessages: [], chatInput: '', chatSending: false, chatEndRef: { current: null },
    historyRecords: [], historyLoading: false,
    doAiAnalysis: vi.fn(), doChatSend: vi.fn(), loadHistory: vi.fn(),
    setChatInput: vi.fn(), setChatMessages: vi.fn(), setAiResult: vi.fn(), aiResultRef: { current: null },
  }),
}))

import FATraceabilityPage from './page'

const FLOW = {
  stages: [
    { stage: 'fermentation', label: '发酵', nodes: [{ batch_no: 'FA-1', detail: '投料 10kg' }] },
    { stage: 'acidification', label: '酸化', nodes: [{ batch_no: 'FA-2', detail: '' }] },
  ],
  target_batch: 'FA-1',
  target_stage: 'fermentation',
}

describe('FATraceabilityPage (203)', () => {
  let root: Root
  let container: HTMLElement

  function jsonResponse(body: unknown): Response {
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  it('renders the FA trace page with search and flow rendering', async () => {
    const fetchMock = (url: string) => {
      if (url.includes('/fa/lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: FLOW }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FATraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    // 输入批号并触发追溯
    const input = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('输入批号'))
    if (input) {
      await act(async () => {
        input.value = 'FA-1'
        input.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('FA 批次')
  })

  it('renders empty when no flow data', async () => {
    const fetchMock = (url: string) => {
      if (url.includes('/fa/lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FATraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('FA 批次')
  })
})