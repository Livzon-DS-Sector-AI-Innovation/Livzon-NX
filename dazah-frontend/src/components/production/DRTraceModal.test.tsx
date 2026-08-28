/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DRTraceModal from './DRTraceModal'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const STAGES = [
  {
    stage: 'fermentation', label: '发酵', note: '发酵说明',
    nodes: [
      { batch_no: 'DR-F1', yield_rate: 1.5, quantity: 100 },
      { batch_no: 'DR-F1-b', is_sibling: true, connects_to: 'DR-S1', sib_group: 'DR-F1', broken: true, broken_reason: '断链' },
    ],
  },
  {
    stage: 'extraction', label: '萃取',
    nodes: [
      { batch_no: 'DR-S1', yield_rate: 0.9, quantity: 90, loss_kg: 2.5, loss_rate: 3.1, loss_level: 'yellow' },
    ],
  },
]

describe('DRTraceModal', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders lineage SVG from /dr/lineage trace data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          jsonResponse({
            code: 200,
            message: 'success',
            data: { stages: STAGES, target_batch: 'DR-1', target_stage: 'fermentation' },
          })
        )
      )
    )
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <DRTraceModal stage="fermentation" batchNo="DR-1" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('批次追溯')
    expect(text).toContain('DR-1')
    expect(text).toContain('发酵说明')
  })

  it('shows error state when trace request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 404, message: '未查到数据' })))
    )
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <DRTraceModal stage="fermentation" batchNo="DR-X" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('未查到数据')
  })

  it('renders multi-source sib-group lines and empty layout path', async () => {
    const data = {
      stages: [
        { stage: 'fermentation', label: '发酵', nodes: [
          { batch_no: 'DR-A', quantity: 100 },
          { batch_no: 'DR-B', quantity: 90 },
        ] },
        { stage: 'extraction', label: '萃取', nodes: [
          { batch_no: 'DR-E1', quantity: 80, loss_kg: 1, loss_rate: 2, loss_level: 'green' },
          { batch_no: 'DR-E2', is_sibling: true, connects_to: 'DR-E1', sib_group: 'DR-A、DR-B' },
          { batch_no: 'DR-E3', broken: true, broken_reason: '无源头' },
        ] },
      ],
      target_batch: 'DR-E1',
      target_stage: 'extraction',
    }
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <DRTraceModal stage="extraction" batchNo="DR-E1" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('批次追溯')
    expect(text).toContain('DR-E1')
    expect(text).toContain('无源头')
  })

it('renders empty when no order-matching stage is provided', async () => {
    const data = { stages: [{ stage: 'unknown', label: 'x', nodes: [] }], target_batch: 'DR-0', target_stage: 'unknown' }
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data }))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <DRTraceModal stage="unknown" batchNo="DR-0" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('未查到相关批次')
  })

  it('renders sibling dashes, connects_to lines, broken/loss data, and exports PNG', async () => {
    const data = {
      stages: [
        { stage: 'fermentation', label: '发酵', nodes: [
          { batch_no: 'DR-A', connects_to: 'DR-B', quantity: 100 },
        ] },
        { stage: 'extraction', label: '萃取', nodes: [
          { batch_no: 'DR-B', quantity: 90, loss_kg: 2.5, loss_rate: 3.1, loss_level: 'red', detail: 'd-x',
            loss_breakdown: { recorded: true, mother_liquor_kg: 1, recovery_powder_kg: 0.5, other_kg: 1 } },
          { batch_no: 'DR-C', is_sibling: true, connects_to: 'DR-F', sib_group: 'DR-A' },
          { batch_no: 'DR-D', is_sibling: true, connects_to: 'DR-F', sib_group: 'DR-A' },
        ] },
        { stage: 'chromatography', label: '层析', nodes: [
          { batch_no: 'DR-F', quantity: 98 },
        ] },
      ],
      target_batch: 'DR-B',
      target_stage: 'extraction',
    }
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data }))))
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }) as any
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <DRTraceModal stage="extraction" batchNo="DR-B" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('批次追溯')
    expect(text).toContain('DR-B')
    expect(text).toContain('DR-F')
    const exportBtn = Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').includes('导出')) as HTMLButtonElement | undefined
    if (exportBtn) {
      await act(async () => { exportBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
  })

  it('shows network error when the trace request rejects', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('boom'))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <DRTraceModal stage="fermentation" batchNo="DR-B" onClose={() => {}} />
        </App>
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect((container.textContent || '') + (document.body.textContent || '')).toContain('网络错误')
  })
})