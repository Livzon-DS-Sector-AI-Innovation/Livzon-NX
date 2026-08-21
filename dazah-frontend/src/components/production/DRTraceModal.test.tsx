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
})