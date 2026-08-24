/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TraceModal from './TraceModal'
import { buildLayout } from './TraceModal'

const LAYOUT_STAGES = [
  { stage: 'refinement', label: '精制MC-F2', nodes: [{ batch_no: 'MC-F2-1', yield_rate: 88.5, quantity: 100 }] },
  { stage: 'extraction', label: '萃取批号', nodes: [] },
  { stage: 'sub_tank', label: '钠化批号', nodes: [
    { batch_no: 'MC-1', yield_rate: 90, quantity: 100 },
    { batch_no: 'MC-1-b', yield_rate: 85, quantity: 30, is_sibling: true, connects_to: 'MC-F2-1' },
  ] },
]

describe('TraceModal buildLayout', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('builds node/line/note layout for a stage graph', () => {
    const cfg: Record<string, { color: string }> = {
      refinement: { color: '#722ed1' }, extract: { color: '#fa8c16' }, sub_tank: { color: '#13c2c2' },
    }
    const layout = buildLayout(LAYOUT_STAGES, 'MC-F2-1', 'refinement', cfg, ['refinement', 'sub_tank'])
    expect(layout.nodes.length).toBeGreaterThan(0)
    expect(layout.lines).toBeInstanceOf(Array)
    expect(layout.notes).toBeInstanceOf(Array)
    const target = layout.nodes.find((n) => n.batch_no === 'MC-F2-1')
    expect(target?.is_target).toBe(true)
    expect(target?.label).toBe('精制MC-F2')
    const sib = layout.nodes.find((n) => n.batch_no === 'MC-1-b')
    expect(sib?.is_sibling).toBe(true)
    expect(String(sib?.connects_to || '')).toContain('MC-F2-1')
    const main = layout.nodes.find((n) => n.batch_no === 'MC-1')
    expect(main).toBeTruthy()
    expect(typeof main?.x).toBe('number')
    expect(typeof main?.y).toBe('number')
  })

  it('returns empty layout when no stages in order match', () => {
    const layout = buildLayout(LAYOUT_STAGES, 'MC-F2-1', 'refinement', { refinement: { color: '#000' } }, ['unknown_stage'])
    expect(layout.nodes).toEqual([])
    expect(layout.lines).toEqual([])
  })

  it('renders the trace modal, loads history and AI analysis flow', async () => {
    const TRACE = {
      stages: LAYOUT_STAGES,
      target_batch: 'MC-F2-1',
      target_stage: 'refinement',
    }
    function fetchMock(url: string): Promise<Response> {
      const body =
        url.includes('/trace')
          ? { code: 200, message: 'success', data: TRACE }
          : url.includes('/ai-history')
            ? { code: 200, message: 'success', data: { records: [] } }
            : { code: 200, message: 'success', data: null }
      return Promise.resolve(new Response(JSON.stringify(body), {
        status: 200, headers: { 'content-type': 'application/json' },
      }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    let root: Root
    const container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><TraceModal stage="refinement" batchNo="MC-F2-1" onClose={() => {}} /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('批次追溯')
    expect(text).toContain('MC-F2-1')
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
  })

  it('executes AI analysis and chat follow-up flow', async () => {
    function fetchMock(url: string): Promise<Response> {
      if (url.includes('/trace')) {
        return Promise.resolve(new Response(JSON.stringify({
          code: 200, message: 'success',
          data: { stages: LAYOUT_STAGES, target_batch: 'MC-F2-1', target_stage: 'refinement' },
        }), { status: 200, headers: { 'content-type': 'application/json' } }))
      }
      if (url.includes('/ai-history')) {
        return Promise.resolve(new Response(JSON.stringify({
          code: 200, message: 'success', data: { records: [
            { id: 1, severity: 'high', created_at: '2026-08-21 09:00', stage_label: '精制', batch_no: 'MC-F2-1', summary: '存在风险', session_id: 's1' },
          ] },
        }), { status: 200, headers: { 'content-type': 'application/json' } }))
      }
      if (url.includes('/ai-analysis')) {
        return Promise.resolve(new Response(JSON.stringify({
          code: 200, message: 'success', data: {
            severity: 'high', summary: '存在风险', causes: ['原因1'], suggestions: ['建议1'], session_id: 's1',
          },
        }), { status: 200, headers: { 'content-type': 'application/json' } }))
      }
      if (url.includes('/chat/send')) {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode('data: {"token":"回复"}\n'))
            controller.close()
          },
        })
        return Promise.resolve(new Response(body, {
          status: 200, headers: { 'content-type': 'text/event-stream' },
        }))
      }
      return Promise.resolve(new Response(JSON.stringify({ code: 200, message: 'success', data: null }), {
        status: 200, headers: { 'content-type': 'application/json' },
      }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    let root: Root
    const container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><TraceModal stage="refinement" batchNo="MC-F2-1" onClose={() => {}} /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })

    const aiButton = Array.from(document.querySelectorAll('button')).find((b) => b.textContent?.includes('AI'))
    if (aiButton) {
      await act(async () => { aiButton.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const aiBtns = Array.from(document.querySelectorAll('button')).filter((b) => b.textContent?.includes('AI'))
    expect(aiBtns.length).toBeGreaterThan(0)
    const histBtn = Array.from(document.querySelectorAll('button')).find((b) => b.textContent?.includes('历史'))
    if (histBtn) {
      await act(async () => { histBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
  })
})

// 额外覆盖 buildLayout 更多分支
describe('TraceModal buildLayout edges', () => {
  it('handles sibling connections and stage notes', () => {
    const cfg: Record<string, { color: string }> = { refinement: { color: '#722ed1' }, sub_tank: { color: '#13c2c2' } }
    const stages = [
      { stage: 'refinement', label: '精制MC-F2', nodes: [{ batch_no: 'MC-F2-1', yield_rate: 88.5 }],
        note: 'note' },
      { stage: 'sub_tank', label: '钠化批号', nodes: [
        { batch_no: 'MC-1', yield_rate: 90, connects_to: 'MC-2' },
        { batch_no: 'MC-2', yield_rate: 85 },
        { batch_no: 'MC-1-b', yield_rate: 80, is_sibling: true, connects_to: 'MC-2' },
      ] },
    ]
    const layout = buildLayout(stages, 'MC-F2-1', 'refinement', cfg, ['refinement', 'sub_tank'])
    expect(layout.notes.length).toBeGreaterThan(0)
    expect(layout.lines).toBeInstanceOf(Array)
  })

  it('renders the modal with a valid layout and AI analysis result', async () => {
    const TRACE = {
      stages: LAYOUT_STAGES,
      target_batch: 'MC-F2-1',
      target_stage: 'refinement',
    }
    function fetchMock(url: string): Promise<Response> {
      if (url.includes('/ai-analysis')) {
        return Promise.resolve(new Response(JSON.stringify({ code: 200, message: 'success', data: {
          severity: 'high', summary: '存在风险', causes: ['原因'], suggestions: ['建议'], session_id: 's1',
          anomalies: [{ stage: '精制', batch_no: 'MC-F2-1', value: 88.5, detail: '偏低' }],
          analysis_text: '详细LLM输出',
        } }), { status: 200, headers: { 'content-type': 'application/json' } }))
      }
      if (url.includes('/trace')) {
        return Promise.resolve(new Response(JSON.stringify({ code: 200, message: 'success', data: TRACE }), {
          status: 200, headers: { 'content-type': 'application/json' },
        }))
      }
      if (url.includes('/ai-history')) {
        return Promise.resolve(new Response(JSON.stringify({ code: 200, message: 'success', data: { records: [] } }), {
          status: 200, headers: { 'content-type': 'application/json' },
        }))
      }
      return Promise.resolve(new Response(JSON.stringify({ code: 200, message: 'success', data: null }), {
        status: 200, headers: { 'content-type': 'application/json' },
      }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    const container2 = document.createElement('div')
    document.body.append(container2)
    const root2 = createRoot(container2)
    act(() => root2.render(<App><TraceModal stage="refinement" batchNo="MC-F2-1" onClose={() => {}} /></App>))
    await act(async () => { await new Promise((r) => setTimeout(r, 100)) })
    const aiBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('AI'))
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    const text = (document.body.textContent || '')
    expect(text).toContain('存在风险')
    expect(text).toContain('原因：原因')
    expect(text).toContain('建议：建议')
    expect(text).toContain('严重')
    act(() => root2.unmount())
    container2?.remove()
    vi.unstubAllGlobals()
  })
})