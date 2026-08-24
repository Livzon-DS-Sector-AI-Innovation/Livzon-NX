/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { routerPushMock } = vi.hoisted(() => ({ routerPushMock: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPushMock }),
  useSearchParams: () => new URLSearchParams(),
}))
const { faChatState, faChatActions } = vi.hoisted(() => {
  const faChatState = {
    aiResult: { severity: 'high', summary: '存在风险', causes: ['原因'], suggestions: ['建议'], anomalies: [{ severity: 'high', batch_no: 'FA-2', detail: '异常详情' }], analysis_text: '详细分析' },
    thinkingSteps: [] as Array<{ step: string; msg: string; done?: boolean }>,
    thinkingText: '',
    chatMessages: [] as Array<{ role: string; content: string }>,
    chatInput: '',
    chatSending: false,
    historyRecords: [] as Array<Record<string, unknown>>,
    historyLoading: false,
  }
  const faChatActions = {
    doAiAnalysis: vi.fn(),
    doChatSend: vi.fn(),
    loadHistory: vi.fn(),
    setChatInput: vi.fn(),
    setChatMessages: vi.fn(),
    setAiResult: vi.fn(),
  }
  return { faChatState, faChatActions }
})

vi.mock('@/hooks/useFAChat', () => ({
  useFAChat: () => ({
    aiLoading: false, aiResult: faChatState.aiResult,
    thinkingSteps: faChatState.thinkingSteps, thinkingText: faChatState.thinkingText,
    chatMessages: faChatState.chatMessages, chatInput: faChatState.chatInput, chatSending: faChatState.chatSending, chatEndRef: { current: null },
    historyRecords: faChatState.historyRecords, historyLoading: faChatState.historyLoading,
    doAiAnalysis: faChatActions.doAiAnalysis, doChatSend: faChatActions.doChatSend, loadHistory: faChatActions.loadHistory,
    setChatInput: faChatActions.setChatInput, setChatMessages: faChatActions.setChatMessages, setAiResult: faChatActions.setAiResult, aiResultRef: { current: null },
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

  // React 监听原生 value setter；直接赋值不会触发 onChange
  function setNativeValue(input: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }

  function resetChatState() {
    faChatState.aiResult = { severity: 'high', summary: '存在风险', causes: ['原因'], suggestions: ['建议'], anomalies: [{ severity: 'high', batch_no: 'FA-2', detail: '异常详情' }], analysis_text: '详细分析' }
    faChatState.thinkingSteps = []
    faChatState.thinkingText = ''
    faChatState.chatMessages = []
    faChatState.chatInput = ''
    faChatState.chatSending = false
    faChatState.historyRecords = []
    faChatState.historyLoading = false
  }

  function faFetchMock(url: string): Promise<Response> {
    if (url.includes('/fa/lineage/trace')) {
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: FLOW }))
    }
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
  }

  async function renderAndSearch() {
    vi.stubGlobal('fetch', vi.fn(faFetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FATraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const input = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('输入批号'))
    await act(async () => {
      if (input) setNativeValue(input, 'FA-EX25315')
      await new Promise((r) => setTimeout(r, 30))
    })
    const traceBtnSwap = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('追溯'))
    await act(async () => {
      traceBtnSwap?.click()
      await new Promise((r) => setTimeout(r, 150))
    })
  }

  it('searches a batch, renders the flow/AI card, and restores a history analysis from the popover', async () => {
    resetChatState()
    faChatState.historyRecords = [
      { id: 'h1', severity: 'medium', session_id: 's-h1', created_at: '2026-08-01 10:00:00', summary: '历史分析摘要' },
    ]
    await renderAndSearch()
    const text = container.textContent || ''
    // flow nodes
    expect(text).toContain('FA-1')
    expect(text).toContain('目标批次: FA-1')
    expect(text).toContain('FA-2')
    // AI result card renders severity/summary/anomalies/原因/建议
    expect(text).toContain('存在风险')
    expect(text).toContain('异常详情')
    expect(text).toContain('原因')
    expect(text).toContain('建议')
    // open history popover and restore a record
    const histBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('分析历史'))
    await act(async () => {
      histBtn?.click()
      await new Promise((r) => setTimeout(r, 120))
    })
    expect(document.body.textContent || '').toContain('历史分析摘要')
    const rowEl = Array.from(document.body.querySelectorAll('*')).find((el) => (el.textContent || '') === '历史分析摘要' && el.children.length === 0) as HTMLElement | undefined
    await act(async () => {
      rowEl?.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(faChatActions.setAiResult).toHaveBeenCalled()
  })

  it('renders thinking steps with raw output and copies the analysis text', async () => {
    resetChatState()
    faChatState.thinkingSteps = [{ step: '1', done: true, msg: '完成推理' }]
    faChatState.thinkingText = 'LLM原始输出'
    await renderAndSearch()
    const text = container.textContent || ''
    expect(text).toContain('完成推理')
    expect(text).toContain('LLM原始输出')
    const writeSpy = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: writeSpy }, configurable: true })
    const copyBtn = Array.from(container.querySelectorAll('button')).find((b) => /^复\s*制$/.test((b.textContent || '').trim())) as HTMLElement | undefined
    expect(copyBtn).toBeDefined()
    await act(async () => {
      copyBtn?.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(writeSpy).toHaveBeenCalledWith('详细分析')
  })

  it('renders chat messages and sends a follow-up question through the chat input', async () => {
    resetChatState()
    faChatState.chatMessages = [{ role: 'user', content: '为什么偏低？' }, { role: 'assistant', content: '请稍候' }]
    await renderAndSearch()
    expect(container.textContent || '').toContain('为什么偏低？')
    const chatInput = Array.from(container.querySelectorAll('input')).find((i) => i.placeholder?.includes('继续追问'))
    await act(async () => {
      if (chatInput) setNativeValue(chatInput, '再来一次')
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(faChatActions.setChatInput).toHaveBeenCalledWith('再来一次')
    const sendBtn = Array.from(container.querySelectorAll('button')).find((b) => b.querySelector('.anticon-send'))
    await act(async () => {
      sendBtn?.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(faChatActions.doChatSend).toHaveBeenCalled()
  })

  it('warns when searching without a batch number and routes back to the workshop', async () => {
    resetChatState()
    vi.stubGlobal('fetch', vi.fn(faFetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><FATraceabilityPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const traceBtnSwap = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('追溯'))
    await act(async () => {
      traceBtnSwap?.click()
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(document.body.textContent || '').toContain('请输入批号')
    const backBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('返回车间'))
    await act(async () => {
      backBtn?.click()
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(routerPushMock).toHaveBeenCalledWith('/production/batches/workshop/203?tab=workshop')
  })
})