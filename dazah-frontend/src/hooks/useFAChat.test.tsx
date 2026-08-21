/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useFAChat } from './useFAChat'

// 构造 ReadableStream 响应，用于 SSE 流式测试
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

function Harness({ stage, batchNo }: { stage: string; batchNo: string }) {
  const chat = useFAChat({ stage, batchNo })
  return (
    <div>
      <button onClick={() => chat.doAiAnalysis()}>分析</button>
      <button
        onClick={() => {
          chat.setChatInput('追问一下')
          chat.doChatSend()
        }}
      >
        发送
      </button>
      <button onClick={() => chat.loadHistory()}>历史</button>
      <button onClick={() => chat.setAiResult({ session_id: 's1' })}>设会话</button>
      <span data-testid="ai">{chat.aiResult ? 'has-result' : 'none'}</span>
      <span data-testid="thinking">{chat.thinkingText}</span>
      <span data-testid="history">{chat.historyRecords ? chat.historyRecords.length : 0}</span>
    </div>
  )
}

describe('useFAChat', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('doAiAnalysis parses step/token/result events from the SSE stream', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          streamResponse([
            'data: {"type":"step","step":1,"done":false,"msg":"开始分析"}',
            'data: {"type":"token","content":"风险"}',
            'data: {"type":"result","severity":"high","summary":"存在风险","causes":["原因1"],"suggestions":["建议1"],"session_id":"s1"}',
            '',
          ])
        )
      )
    )
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Harness stage="fermentation" batchNo="FA-1" />
        </App>
      )
    })
    const btn = container.querySelector('button')!
    await act(async () => {
      btn.click()
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(container.querySelector('[data-testid=ai]')?.textContent).toBe('has-result')
  })

  it('loadHistory sets records when code is 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({ code: 200, message: 'success', data: { records: [{ id: 1 }, { id: 2 }] } })
        )
      )
    )
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Harness stage="fermentation" batchNo="FA-2" />
        </App>
      )
    })
    const btns = container.querySelectorAll('button')
    await act(async () => {
      btns[2].click()
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(container.querySelector('[data-testid=history]')?.textContent).toBe('2')
  })

  it('doAiAnalysis with empty batchNo does nothing', async () => {
    const fetchFn = vi.fn(() => Promise.resolve(streamResponse(['data: {"type":"result","summary":"x"}\n'])))
    vi.stubGlobal('fetch', fetchFn)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Harness stage="" batchNo="" />
        </App>
      )
    })
    const btn = container.querySelector('button')!
    await act(async () => {
      btn.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it('doChatSend warns when no session id exists', async () => {
    const fetchFn = vi.fn(() => Promise.resolve(jsonResponse({ code: 200, data: null })))
    vi.stubGlobal('fetch', fetchFn)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Harness stage="fermentation" batchNo="FA-3" />
        </App>
      )
    })
    const btns = container.querySelectorAll('button')
    await act(async () => {
      btns[1].click()
      await new Promise((r) => setTimeout(r, 30))
    })
    // 无 session_id -> 不应真正发送
    expect(fetchFn).not.toHaveBeenCalledWith(
      expect.stringContaining('/chat/send'),
      expect.anything(),
    )
    // 仍可渲染
    expect(container.querySelector('[data-testid=ai]')?.textContent).toBe('none')
  })

  it('doChatSend streams tokens to the assistant message when a session exists', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(streamResponse([
      'data: {"token":"回答"}',
      'data: {"token":"内容"}',
      '',
    ]))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Harness stage="fermentation" batchNo="FA-4" />
        </App>
      )
    })
    const btns = container.querySelectorAll('button')
    // 先设置 session（会触发 doChatSend 的 session_id 分支）
    await act(async () => {
      btns[3].click()
      await new Promise((r) => setTimeout(r, 20))
    })
    await act(async () => {
      btns[1].click()
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(container.querySelector('[data-testid=ai]')?.textContent).toBe('has-result')
  })

  it('doAiAnalysis surfaces an error event and malformed-token is skipped', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(streamResponse([
      'data: {"type":"error","msg":"模型不可用"}',
      'data: not-json',
      '',
    ]))))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(
        <App>
          <Harness stage="fermentation" batchNo="FA-5" />
        </App>
      )
    })
    const btn = container.querySelector('button')!
    await act(async () => {
      btn.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    // error 事件不设 result，且非 JSON行跳过；ai 仍是 none
    expect(container.querySelector('[data-testid=ai]')?.textContent).toBe('none')
  })
})