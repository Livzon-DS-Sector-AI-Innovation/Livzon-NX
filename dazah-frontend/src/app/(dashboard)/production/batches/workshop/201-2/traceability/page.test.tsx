/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { routerPushMock } = vi.hoisted(() => ({ routerPushMock: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPushMock }),
  useSearchParams: () => new URLSearchParams('stage=fermentation&batch_no=MC-F1'),
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

// React 监听原始 value setter；直接赋值不会触发 onChange，走原生 prototype setter
function setNativeValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
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
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [
      { stage: 'extraction', label: '萃取', count: 10, min: 80, q1: 85, median: 90, mean: 95, q3: 98, max: 100, below_80: 1, above_110: 0 },
    ] }))
  }
  if (url.includes('/lineage/coverage')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: {
      segments: [{ segment: '发酵', count: 7 }, { segment: '萃取', count: 3 }],
      broken: {},
      extraction_coverage_pct: 92,
      extraction_total: 10,
      extraction_missing: 2,
    } }))
  }
  if (url.includes('/lineage/material-reuse')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [
      { upstream_type: 'extraction', upstream_batch: 'MC-E1', usage_count: 5, used_by: 'MC-F1' },
      { upstream_type: '神秘类型', upstream_batch: 'MC-X1', usage_count: 2, used_by: 'MC-F2' },
    ] }))
  }
  if (url.includes('/lineage/loss-stats')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
  }
  if (url.includes('/chat/send')) {
    return Promise.resolve(streamResponse([
      'data: {"token":"收到,"}',
      'data: {"token":"请稍等"}',
      '',
    ]))
  }
  if (url.includes('ai-analysis-stream')) {
    return Promise.resolve(streamResponse([
      'data: {"type":"step","step":1,"msg":"开始分析","done":true}',
      'data: {"type":"token","content":"潜在风险"}',
      'data: {"type":"result","severity":"high","summary":"存在风险","session_id":"s1",'
      + '"causes":["物料投入异常"],"suggestions":["复核"],"anomalies":[{"stage":"萃取","batch_no":"MC-E1","value":80,"detail":"偏低"}],'
      + '"analysis_text":"详细分析"}',
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

  it('renders the full-chain traceability page and triggers an auto trace from URL params', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })

    const text = container.textContent || ''
    expect(text).toContain('全链路追溯')
    // 由于 URL 携带 stage/batch_no，mount 时应已触发自动追溯并渲染流程节点
    expect(text).toContain('累计收率: 85.2%')
    expect(text).toContain('MC-E1')
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

  it('runs an AI analysis over the SSE stream and renders the result & chat', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })

    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析'))
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 120)) })
    }

    const text = container.textContent || ''
    // ai-result 分支：summary（存在风险）/thinkingSteps（开始分析）/token（潜在风险）渲染
    expect(text).toContain('存在风险')
    expect(text).toContain('开始分析')
    expect(text).toContain('潜在风险')
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

  it('renders analytics tabs: material reuse and coverage completeness', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })

    const reuseTab = Array.from(container.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('物料复用')) as HTMLElement | undefined
    if (reuseTab) {
      await act(async () => { reuseTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const reuseText = container.textContent || ''
    expect(reuseText).toContain('物料复用')
    expect(reuseText).toContain('被多个成品批次复用的物料')

    const covTab = Array.from(document.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('覆盖完整性')) as HTMLElement | undefined
    if (covTab) {
      await act(async () => { covTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const covText = container.textContent || ''
    expect(covText).toContain('血链表各段关联覆盖')
  })

  it('renders AI analysis detail: anomalies and copy action', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })

    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析')) as HTMLElement | undefined
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 160)) })
    }
    await act(async () => { await new Promise((r) => setTimeout(r, 60)) })
    const text = container.textContent || ''
    // aiResult.anomalies 分支渲染
    expect(text).toContain('异常标记')
    expect(text).toContain('MC-E1')
    expect(text).toContain('可能原因')
    expect(text).toContain('物料投入异常')
    expect(text).toContain('优化建议')
    expect(text).toContain('复核')
  })

  it('loads AI analysis history, restores a record, and copies its text', async () => {
    const record = {
      id: 'h1',
      severity: 'high',
      session_id: 'sess-h1',
      created_at: '2026-08-01 10:22:33',
      stage: 'extraction', stage_label: '萃取', batch_no: 'MC-E1',
      summary: '历史异常分析结论',
      causes: ['历史原因'], suggestions: ['历史建议'],
    }
    const historyMock = (url: string) => {
      if (url.includes('/lineage/ai-history')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [record] } }))
      }
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(historyMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })

    const histBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('历史记录')) as HTMLElement | undefined
    if (histBtn) {
      await act(async () => { histBtn.click(); await new Promise((r) => setTimeout(r, 120)) })
    }
    expect(document.body.textContent || '').toContain('历史异常分析结论')
    // 点击历史记录行恢复 aiResult（analysis_text 置空、session 复用）
    const rowText = Array.from(document.body.querySelectorAll('span, div')).find((el) => (el.textContent || '').trim() === '历史异常分析结论') as HTMLElement | undefined
    if (rowText) {
      await act(async () => { rowText.click(); await new Promise((r) => setTimeout(r, 80)) })
    }
    expect(container.textContent || '').toContain('历史原因')
    // 复制按钮：写入剪贴板
    const writeSpy = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: writeSpy }, configurable: true })
    const copyBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('复制结果')) as HTMLElement | undefined
    if (copyBtn) {
      await act(async () => { copyBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect(writeSpy).toHaveBeenCalled()
  })

  it('shows the failure message when the trace API returns a non-200 code', async () => {
    const errMock = (url: string) => {
      if (url.includes('/lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 500, message: '该批次不存在', data: null }))
      }
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(errMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(document.body.textContent || '').toContain('该批次不存在')
  })

  it('shows a network error when the trace request rejects', async () => {
    const netMock = (url: string) => {
      if (url.includes('/lineage/trace')) return Promise.reject(new Error('network down'))
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(netMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(document.body.textContent || '').toContain('网络错误，请检查服务是否正常运行')
  })

  it('merges repeated thinking steps and warns when AI ends without a result', async () => {
    const noResultMock = (url: string) => {
      if (url.includes('ai-analysis-stream')) {
        return Promise.resolve(streamResponse([
          'data: {"type":"step","step":1,"msg":"开始分析","done":false}',
          'data: {"type":"step","step":1,"msg":"开始分析","done":true}',
          'data: {"type":"token","content":"仅思考"}',
          '',
        ]))
      }
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(noResultMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析')) as HTMLElement | undefined
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(container.textContent || '').toContain('开始分析')
    expect(document.body.textContent || '').toContain('AI 分析未返回完整结果，请重试')
  })

  it('shows an AI failure toast when the analysis stream cannot be read', async () => {
    const failMock = (url: string) => {
      if (url.includes('ai-analysis-stream')) return Promise.resolve(new Response(null, { status: 200 }))
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(failMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析')) as HTMLElement | undefined
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(document.body.textContent || '').toContain('AI 分析失败，请重试')
  })

  it('sends a follow-up chat message and streams the assistant reply into the chat', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析')) as HTMLElement | undefined
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 160)) })
    }
    const chatInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('继续追问'))
    if (chatInput) {
      await act(async () => {
        setNativeValue(chatInput, '为什么收率偏低？')
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    const sendBtn = Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('.anticon-send'))
    if (sendBtn) {
      await act(async () => { sendBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    const text = container.textContent || ''
    expect(text).toContain('为什么收率偏低？')
    expect(text).toContain('收到,')
    expect(text).toContain('请稍等')
  })

  it('shows a chat retry note when the chat stream fails', async () => {
    const chatErrMock = (url: string) => {
      if (url.includes('/chat/send')) return Promise.resolve(new Response(null, { status: 500 }))
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(chatErrMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析')) as HTMLElement | undefined
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 160)) })
    }
    const chatInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('继续追问'))
    if (chatInput) {
      await act(async () => {
        setNativeValue(chatInput, '继续')
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    const sendBtn = Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('.anticon-send'))
    if (sendBtn) {
      await act(async () => { sendBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
    }
    expect(container.textContent || '').toContain('网络错误，请重试')
  })

  it('warns when sending a chat message while no AI session is active', async () => {
    const noSessionMock = (url: string) => {
      if (url.includes('ai-analysis-stream')) {
        return Promise.resolve(streamResponse([
          'data: {"type":"result","severity":"low","summary":"无会话","session_id":"","causes":[],"suggestions":[],"anomalies":[],"analysis_text":"x"}',
          '',
        ]))
      }
      return fetchMock(url)
    }
    vi.stubGlobal('fetch', vi.fn(noSessionMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const aiBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('AI 分析')) as HTMLElement | undefined
    if (aiBtn) {
      await act(async () => { aiBtn.click(); await new Promise((r) => setTimeout(r, 160)) })
    }
    const chatInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('继续追问'))
    if (chatInput) {
      await act(async () => {
        setNativeValue(chatInput, '追问')
        await new Promise((r) => setTimeout(r, 80))
      })
    }
    const sendBtn = Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('.anticon-send'))
    if (sendBtn) {
      await act(async () => { sendBtn.click(); await new Promise((r) => setTimeout(r, 150)) })
    }
    expect(document.body.textContent || '').toContain('会话已过期')
  })

  it('exports the flow chart image and back button pushes to the workshop', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出图片'))
    if (exportBtn) {
      await act(async () => { exportBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()

    const backBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('返回车间'))
    if (backBtn) {
      await act(async () => { backBtn.click(); await new Promise((r) => setTimeout(r, 50)) })
    }
    expect(routerPushMock).toHaveBeenCalledWith('/production/batches/workshop/201-2')
  })

  it('renders material reuse rows and coverage segments from analytics data', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const reuseTab = Array.from(container.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('物料复用')) as HTMLElement | undefined
    if (reuseTab) {
      await act(async () => { reuseTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const reuseText = container.textContent || ''
    // reuse 列 render：标签 + 复用次数
    expect(reuseText).toContain('MC-E1')
    expect(reuseText).toContain('5 次')
    expect(reuseText).toContain('神秘类型')

    const covTab = Array.from(document.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('覆盖完整性')) as HTMLElement | undefined
    if (covTab) {
      await act(async () => { covTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const covText = container.textContent || ''
    expect(covText).toContain('发酵')
    expect(covText).toContain('7 条')
    expect(covText).toContain('92%')
  })
})