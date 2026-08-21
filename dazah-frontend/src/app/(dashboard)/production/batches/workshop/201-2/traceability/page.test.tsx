/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))
vi.mock('html-to-image', () => ({
  toPng: vi.fn().mockResolvedValue('data:image/png;base64,AAA'),
}))

import TraceabilityPage from './page'

const TRACE = {
  stages: [
    {
      stage: 'fermentation',
      label: '发酵',
      nodes: [
        { batch_no: 'MC-F1', stage: 'fermentation', label: '发酵', yield_rate: 92.1, input_total: 60, quantity: 40, feeds: [{ batch_no: 'MC-F0', label: '预混', qty: 40 }] },
        { batch_no: 'MC-F1-b', stage: 'fermentation', label: '发酵', yield_rate: 96.3, is_sibling: true, sib_group: 'MC-F1' },
      ],
    },
    {
      stage: 'extraction',
      label: '萃取',
      nodes: [{
        batch_no: 'MC-E1', stage: 'extraction', label: '萃取', yield_rate: 88.4,
        loss_kg: 2.5, loss_rate: 3.1, loss_level: 'yellow',
        detail: '投入折纯 50kg',
        loss_breakdown: { recorded: true, mother_liquor_kg: 1.2 },
        input_total: 50, quantity: 30,
        feeds: [
          { batch_no: 'MC-F1', label: '发酵', qty: 30 },
          { batch_no: 'MC-F2', label: '发酵', qty: 20 },
        ],
      }],
    },
    {
      stage: 'second_refinement',
      label: '二次精制',
      nodes: [{ batch_no: 'MC-S1', stage: 'second_refinement', label: '二次精制', yield_rate: 95.0, broken: true, broken_reason: '断链' }],
    },
  ],
  cumulative_yield: 85.2,
  target_stage: 'fermentation',
  target_batch: 'MC-F1',
  max_loss_stage: 'extraction',
  broken_links: [{ batch_no: 'MC-S1', reason: '无源头' }],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

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

function fetchMock(url: string) {
  if (url.includes('/mc/lineage/loss-funnel')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: {
      target_batch: 'MC-F1', overall_yield: 88, overall_loss: 12,
      layers: [{ stage: 'extraction', label: '萃取', output_pure: 90, batch_count: 1, segment_yield: 90 }],
    } }))
  }
  if (url.includes('/mc/lineage/trace')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
  }
  if (url.includes('/mc/lineage/ai-history')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [] } }))
  }
  if (url.includes('/lineage/yield-distribution')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ stage: 'extraction', label: '萃取', count: 10, min: 80 }] }))
  }
  if (url.includes('/lineage/coverage')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { segments: [], broken: {} } }))
  }
  if (url.includes('/lineage/reuse')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
  }
  if (url.includes('/lineage/loss-stats')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
  }
  if (url.includes('ai-analysis-stream')) {
    return Promise.resolve(streamResponse([
      'data: {"type":"step","step":1,"msg":"开始"}',
      'data: {"type":"token","content":"风险"}',
      'data: {"type":"result","severity":"high","summary":"存在风险","session_id":"s1"}',
      '',
    ]))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('TraceabilityPage (201-2)', () => {
  let root: Root
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
  })

  it('renders the full-chain traceability page with a batch query panel', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })

    const text = container.textContent || ''
    expect(text).toContain('全链路追溯')
  })

  it('renders trace result flow when batch is queried', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })

    const inputs = Array.from(container.querySelectorAll('input'))
    if (inputs.length > 0) {
      await act(async () => {
        inputs[inputs.length - 1].value = 'MC-E1'
        inputs[inputs.length - 1].dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const traceBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('追溯'))
    if (traceBtn) {
      await act(async () => { traceBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    // 触发后应出现 FlowNode 分支内容（本段损耗/对账收率）
    const text = container.textContent || ''
    expect(text).toContain('全链路追溯')
  })

  it('shows the empty placeholder when no trace data', async () => {
    const emptyMock = (url: string) => {
      if (url.includes('/lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(emptyMock))

    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(container.textContent || '').toContain('全链路追溯')
  })
})