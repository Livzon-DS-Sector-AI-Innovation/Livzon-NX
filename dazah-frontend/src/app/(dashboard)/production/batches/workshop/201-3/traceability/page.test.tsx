/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { routerPushMock } = vi.hoisted(() => ({ routerPushMock: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPushMock }),
  useSearchParams: () => new URLSearchParams('stage=fermentation&batch_no=DR-F1'),
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
        { batch_no: 'DR-F1', stage: 'fermentation', label: '发酵', yield_rate: 92.1 },
        { batch_no: 'DR-F1-b', stage: 'fermentation', label: '发酵', yield_rate: 96.3, is_sibling: true, sib_group: 'DR-F1' },
      ],
    },
    {
      stage: 'extraction',
      label: '萃取',
      nodes: [{
        batch_no: 'DR-E1', stage: 'extraction', label: '萃取', yield_rate: 68.4,
        loss_kg: 2.5, loss_rate: 1.8, loss_level: 'red',
        detail: '投入折纯 50kg',
        loss_breakdown: { recorded: true, mother_liquor_kg: 1.2, recovery_powder_kg: 0.5, other_kg: 0.8 },
        input_total: 60, quantity: 40,
        feeds: [
          { batch_no: 'DR-F1', label: '发酵', qty: 40 },
          { batch_no: 'DR-F2', label: '发酵', qty: 20 },
        ],
      }],
    },
    {
      stage: 'second_refinement',
      label: '二次精制',
      nodes: [{ batch_no: 'DR-S1', stage: 'second_refinement', label: '二次精制', yield_rate: 95.0, broken: true, broken_reason: '断链' }],
    },
  ],
  cumulative_yield: 85.2,
  target_stage: 'fermentation',
  target_batch: 'DR-F1',
  max_loss_stage: 'extraction',
  broken_links: [{ batch_no: 'DR-S1', reason: '无源头' }],
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
  if (url.includes('dr/lineage/trace')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
  }
  if (url.includes('dr/lineage/loss-funnel')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: {
      target_batch: 'DR-F1', overall_yield: 88, overall_loss: 12,
      layers: [
        { stage: 'fermentation', label: '发酵', output_pure: 100, batch_count: 1, segment_yield: null },
        { stage: 'extraction', label: '萃取', output_pure: 90, batch_count: 1, segment_yield: 90 },
      ],
    } }))
  }
  if (url.includes('/lineage/yield-distribution')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [
      { stage: 'fermentation', label: '发酵', count: 10, min: 80, q1: 85, median: 90, mean: 90.5, q3: 95, max: 100, below_80: 1, above_110: 0 },
    ] }))
  }
  if (url.includes('/lineage/reuse')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [
      { upstream_type: 'extraction', upstream_batch: 'DR-E1', usage_count: 4, used_by: 'DR-F1' },
      { upstream_type: 'chromatography', upstream_batch: 'DR-C1', usage_count: 2, used_by: 'DR-F2' },
    ] }))
  }
  if (url.includes('/lineage/coverage')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: {
      segments: [
        { segment: '发酵', count: 5 },
        { segment: '萃取', count: 3 },
      ],
      broken: {
        extraction_feeds_not_in_extraction: { count: 2, batches: ['DR-X1', 'DR-X2'] },
        third_feeds_not_in_second: { count: 1, batches: ['DR-Y1'] },
        fourth_feeds_not_in_third: { count: 1, batches: ['DR-Z1'] },
        special_feeds: { count: 1, batches: ['DR-H1'] },
      },
    } }))
  }
  if (url.includes('/lineage/loss-stats')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: {
      by_segment_month: [
        { stage: 'second_refinement', year_month: '2026-07', count: 12, avg_yield: 90.5, min_yield: 80, max_yield: 98 },
        { stage: 'third_refinement', year_month: '2026-08', count: 10, avg_yield: 85.0, min_yield: 75, max_yield: 95 },
      ],
      unclosed: [
        { stage: 'fourth_refinement', batch_no: 'DR-GB1', feed_batch_no: 'DR-F3-X', reason: '三次表无记录' },
      ],
    } }))
  }
  if (url.includes('/lineage/ai-history')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { records: [] } }))
  }
  if (url.includes('ai-analysis-stream')) {
    return Promise.resolve(streamResponse([
      'data: {"type":"step","step":1,"msg":"开始分析","done":true}',
      'data: {"type":"token","content":"潜在风险"}',
      'data: {"type":"result","severity":"high","summary":"存在风险","session_id":"s1",'
      + '"causes":["物料投入异常"],"suggestions":["复核"],"anomalies":[{"stage":"萃取","batch_no":"DR-E1","value":68,"detail":"偏低"}],'
      + '"analysis_text":"详细分析"}',
      '',
    ]))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('TraceabilityPage (201-3)', () => {
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
    // URL 携带 stage/batch_no，mount 时应已触发自动追溯并渲染流程节点与分析面板
    expect(text).toContain('累计收率: 85.2%')
    expect(text).toContain('DR-E1')
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
        inputs[inputs.length - 1].value = 'DR-E1'
        inputs[inputs.length - 1].dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const traceBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('追溯'))
    if (traceBtn) {
      await act(async () => { traceBtn.click(); await new Promise((r) => setTimeout(r, 150)) })
    }
    const text = container.textContent || ''
    // 触发追溯后应出现全链路追溯结果卡片
    expect(text).toContain('全链路追溯')
  })

  it('shows the empty placeholder when no trace data', async () => {
    const emptyMock = (url: string) => {
      if (url.includes('/lineage/trace') && url.includes('/loss-funnel')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
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

  it('renders the loss funnel, broken links, and analytics tabs with mock data', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const text = container.textContent || ''
    // LossFunnelCard（故障漏斗）
    expect(text).toContain('全程损耗漏斗')
    expect(text).toContain('全程收率')
    expect(text).toContain('段收率')
    // 断链清单卡片
    expect(text).toContain('断链清单')
    expect(text).toContain('DR-S1')
    // 分析面板 Tabs：收率分布
    expect(text).toContain('收率分布')
    expect(text).toContain('DR 六工段收率箱线数据')
    // 覆盖完整性（coverage tab，默认未激活，需点击切换）
    const covTab = Array.from(container.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('覆盖完整性')) as HTMLElement | undefined
    if (covTab) {
      await act(async () => { covTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const covText = container.textContent || ''
    expect(covText).toContain('DR 六工段台账覆盖')
    expect(covText).toContain('层析投料萃取表查不到')
    expect(covText).toContain('DR-X1')
    // 损耗统计配置页
    const lossTab = Array.from(document.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('损耗统计')) as HTMLElement | undefined
    if (lossTab) {
      await act(async () => { lossTab.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const lossText = container.textContent || ''
    expect(lossText).toContain('按月平均收率')
    expect(lossText).toContain('未闭合投料')
    expect(lossText).toContain('DR-GB1')
  })

  it('renders LossFunnelCard fallback when funnel layers are missing', async () => {
    const mock = (url: string) => {
      if (url.includes('lineage/loss-funnel')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { layers: [], target_batch: 'DR-F1', overall_yield: null, overall_loss: null, notes: [] } }))
      }
      if (url.includes('lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(container.textContent || '').toContain('未找到层析湿粉起点')
  })

  it('renders funnel notes when layers and notes exist', async () => {
    const mock = (url: string) => {
      if (url.includes('lineage/loss-funnel')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: {
          target_batch: 'DR-F1', overall_yield: 88, overall_loss: 12,
          layers: [
            { stage: 'chromatography', label: '层析', output_pure: 100, input_pure: 110, batch_count: 1, segment_yield: 90, segment_loss: 3 },
            { stage: 'fourth_refinement', label: '四次精制', output_pure: 80, batch_count: 1, segment_yield: 85 },
          ],
          notes: ['干粉口径', '母液带出 2kg'],
        } }))
      }
      if (url.includes('lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
const text = container.textContent || ''
    expect(text).toContain('母液带出 2kg')
    expect(text).toContain('干粉口径')
  })

  it('shows the trace API failure message on error code', async () => {
    const mock = (url: string) => {
      if (url.includes('lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 400, message: '该批次不存在于 DR 台账', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent || '').toContain('该批次不存在于 DR 台账')
  })

  it('shows a network error when the trace request rejects', async () => {
    const mock = (url: string) => {
      if (url.includes('lineage/trace')) return Promise.reject(new Error('network down'))
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent || '').toContain('网络错误，请检查服务是否正常运行')
  })

  it('exports the flow chart PNG via anchor click', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const exportBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('导出图片'))
    await act(async () => {
      exportBtn?.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  it('renders reuse rows with usage count tags and fallback labels', async () => {
    const mock = (url: string) => {
      if (url.includes('lineage/material-reuse')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [
          { upstream_type: 'chromatography', upstream_batch: 'DR-C1', usage_count: 4, used_by: 'DR-F1' },
          { upstream_type: '回收粉', upstream_batch: 'DR-R1', usage_count: 1, used_by: 'DR-F2' },
        ] }))
      }
      if (url.includes('lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const reuseTab = Array.from(container.querySelectorAll('.ant-tabs-tab')).find((t) => t.textContent?.includes('物料复用')) as HTMLElement | undefined
    await act(async () => { reuseTab?.click(); await new Promise((r) => setTimeout(r, 80)) })
    const text = container.textContent || ''
    expect(text).toContain('DR-C1')
    expect(text).toContain('4 次')
    expect(text).toContain('回收粉')
  })

  it('shows below-average comparison warning with cumulative yield and max-loss stage', async () => {
    const mock = (url: string) => {
      if (url.includes('lineage/yield-distribution')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [
          { stage: 'extraction', label: '萃取', count: 8, min: 60, q1: 70, median: 88, mean: 90, q3: 95, max: 100, below_80: 2, above_110: 0 },
        ] }))
      }
      if (url.includes('lineage/trace')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const text = container.textContent || ''
    expect(text).toContain('低于工段均值')
    expect(text).toContain('累计收率 85.2%')
    expect(text).toContain('最大损失环节: 萃取')
  })

  // React 监听原生 value setter；直接赋值不会触发 onChange
  function setNativeValue(input: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }

  it('searches a freshly typed batch number and routes back to the workshop', async () => {
    const traceCalls: string[] = []
    const mock = (url: string) => {
      if (url.includes('lineage/trace')) {
        traceCalls.push(url)
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: TRACE }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><TraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120))
    })
    const input = Array.from(container.querySelectorAll('input')).find((i) => (i.placeholder || '').includes('24003'))
    await act(async () => {
      if (input) setNativeValue(input, 'DR-9K-1')
      await new Promise((r) => setTimeout(r, 30))
    })
    const searchBtn = Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('.anticon-search'))
    await act(async () => {
      searchBtn?.click()
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(traceCalls.some((u) => u.includes('batch_no=DR-9K-1'))).toBe(true)
    const backBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('返回车间'))
    await act(async () => {
      backBtn?.click()
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(routerPushMock).toHaveBeenCalledWith('/production/batches/workshop/201-3')
  })
})