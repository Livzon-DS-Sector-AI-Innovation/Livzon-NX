/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import FATraceModal from './FATraceModal'

function streamResponse(lines: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of lines.map((l) => `${l}\n`)) {
        controller.enqueue(new TextEncoder().encode(c))
      }
      controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  })
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const LAYOUT_STAGES = [
  { stage: 'fermentation', label: '发酵', nodes: [{ batch_no: 'FA-1', yield_rate: 90 }] },
  { stage: 'acidification', label: '酸化', nodes: [
    { batch_no: 'FA-2', yield_rate: 85 },
    { batch_no: 'FA-2-b', yield_rate: 80, is_sibling: true, connects_to: 'FA-3' },
  ] },
  { stage: 'decolor1', label: '脱色1', nodes: [{ batch_no: 'FA-3', yield_rate: 88 }] },
]

describe('FATraceModal', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders FA trace modal and loads lineage layout', async () => {
    const TRACE = { stages: LAYOUT_STAGES, target_batch: 'FA-3', target_stage: 'decolor1' }
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/ai-history')) {
          return Promise.resolve(jsonResponse({ code: 200, data: { records: [] } }))
        }
        if (url.includes('/trace')) {
          return Promise.resolve(jsonResponse({ code: 200, data: TRACE }))
        }
        if (url.includes('ai-analysis-stream')) {
          return Promise.resolve(
            streamResponse([
              'data: {"type":"step","step":1,"msg":"开始"}',
              'data: {"type":"token","content":"风险"}',
              'data: {"type":"result","severity":"high","summary":"存在风险","session_id":"s1"}',
              '',
            ])
          )
        }
        return Promise.resolve(jsonResponse({ code: 200, data: null }))
      })
    )
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <FATraceModal stage="decolor1" batchNo="FA-3" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('FA 批次追溯')
    expect(text).toContain('FA-3')
  })
})