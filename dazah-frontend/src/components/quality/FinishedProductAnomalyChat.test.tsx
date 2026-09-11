/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FinishedProductAnomalyChat } from './FinishedProductAnomalyChat'

let root: Root
let container: HTMLDivElement

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  // antd Drawer/Message 通过 portal 挂在 body，卸载后清掉残留避免跨用例串扰
  document
    .body.querySelectorAll('.ant-drawer, .ant-drawer-mask, .ant-message, .ant-scrolling-effect')
    .forEach((node) => node.remove())
  document.body.style.removeProperty('overflow')
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderChat(year: number | null = 2026) {
  act(() => {
    root.render(
      <App>
        <FinishedProductAnomalyChat open year={year} onClose={vi.fn()} />
      </App>,
    )
  })
  // 等 Drawer portal 挂载完成
  return act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
}

function sseChunks(events: unknown[]): Uint8Array[] {
  return events.map(
    (event) => new TextEncoder().encode(`data: ${JSON.stringify(event)}\n`),
  )
}

function mockSseFetch(events: unknown[]) {
  const chunks = sseChunks(events)
  let index = 0
  const reader = {
    read: async () =>
      index < chunks.length
        ? { done: false, value: chunks[index++] }
        : { done: true, value: undefined },
  }
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    body: { getReader: () => reader },
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function flushStream() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

const flushRenders = () => new Promise((resolve) => setTimeout(resolve, 20))

function reactPropsOf(el: Element): Record<string, any> | undefined {
  const propsKey = Object.keys(el).find((key) => key.startsWith('__reactProps$'))
  return propsKey ? (el as unknown as Record<string, any>)[propsKey] : undefined
}

/** rc-textarea autoSize 会附带隐藏测量 textarea，挑真正挂了 onChange 的节点 */
function findComposerTextarea(): HTMLTextAreaElement {
  const textareas = Array.from(
    document.body.querySelectorAll('textarea'),
  ) as HTMLTextAreaElement[]
  const target = textareas.find((el) => typeof reactPropsOf(el)?.onChange === 'function')
  if (!target) {
    throw new Error(`composer textarea not found (${textareas.length} textareas)`)
  }
  return target
}

function reactChange(el: HTMLTextAreaElement, value: string) {
  el.value = value
  reactPropsOf(el)!.onChange({
    target: el,
    currentTarget: el,
    type: 'input',
    preventDefault: () => undefined,
    stopPropagation: () => undefined,
  })
}

function findSendButton(): HTMLButtonElement | undefined {
  // antd 中文按钮会自动插入空格（发 送），按去空白文本匹配
  return Array.from(document.body.querySelectorAll('button')).find(
    (button) => button.textContent?.replace(/\s+/g, '') === '发送',
  )
}

async function typeAndSend(text: string) {
  const textarea = findComposerTextarea()
  act(() => {
    reactChange(textarea, text)
  })
  await act(flushRenders)
  const sendButton = findSendButton()
  act(() => {
    sendButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  await act(flushRenders)
}

describe('FinishedProductAnomalyChat', () => {
  it('renders welcome message and composer', async () => {
    await renderChat()
    expect(document.body.textContent).toContain('成品异常 AI 助手')
    expect(document.body.textContent).toContain('资深现场 QA')
    expect(document.body.querySelector('textarea')).not.toBeNull()
  })

  it('streams status, thinking and answer content from SSE events', async () => {
    const fetchMock = mockSseFetch([
      { status: '正在查询异常记录…' },
      { reasoning_content: '先筛选 2026 年杂质异常。' },
      { content: '霉酚酸' },
      { content: '最多。' },
      { done: true },
    ])

    await renderChat(2026)
    await typeAndSend('哪个产品杂质异常最多？')
    await flushStream()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.year).toBe(2026)
    expect(body.messages.at(-1)).toEqual({
      role: 'user',
      content: '哪个产品杂质异常最多？',
    })
    expect(document.body.textContent).toContain('霉酚酸最多。')
    // 流结束后状态/思考面板收起
    expect(document.body.textContent).not.toContain('正在查询异常记录…')
    const textarea = findComposerTextarea()
    expect(textarea.disabled).toBe(false)
    expect(textarea.value).toBe('')
  })

  it('shows thinking panel while status event is streaming', async () => {
    const chunks = sseChunks([
      { status: '正在查询异常记录…' },
      { reasoning_content: '思考中……' },
      { content: '答案' },
      { done: true },
    ])
    // 受控泵：每个 read() 等测试显式放行，便于在流式中段的可见性断言
    const resolvers: Array<() => void> = []
    let cursor = 0
    const reader = {
      read: () =>
        new Promise((resolve) => {
          resolvers.push(() =>
            resolve(
              cursor < chunks.length
                ? { done: false, value: chunks[cursor++] }
                : { done: true, value: undefined },
            ),
          )
        }),
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }))

    async function pump() {
      await act(async () => {
        resolvers.shift()?.()
        await new Promise((resolve) => setTimeout(resolve, 20))
      })
    }

    await renderChat(null)
    await typeAndSend('分析下')

    // 首个事件消费：状态行可见，输入禁用
    await pump()
    expect(document.body.textContent).toContain('正在查询异常记录…')
    const textarea = findComposerTextarea()
    expect(textarea.disabled).toBe(true)

    // reasoning 事件：思考面板出现且内容可见
    await pump()
    expect(document.body.textContent).toContain('思考过程')
    expect(document.body.textContent).toContain('思考中……')

    // content + done：答案入泡、流结束恢复输入
    await pump()
    await pump()
    await pump()
    expect(document.body.textContent).toContain('答案')
    expect(document.body.textContent).not.toContain('思考过程')
    expect(textarea.disabled).toBe(false)
  })

  it('falls back to retry hint when stream yields no content', async () => {
    mockSseFetch([{ status: '分析中' }, { done: true }])
    await renderChat()
    await typeAndSend('随便问')
    await flushStream()
    expect(document.body.textContent).toContain('（AI 未返回内容')
  })

  it('surfaces backend business message on failed request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ message: 'AI 服务未配置' }),
      }),
    )
    await renderChat()
    await typeAndSend('在吗')
    await flushStream()
    expect(document.body.textContent).toContain('调用失败：AI 服务未配置')
  })

  it('uses http status detail when error body is not json', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('not json')
      },
    }))
    await renderChat()
    await typeAndSend('在吗')
    await flushStream()
    expect(document.body.textContent).toContain('调用失败：请求失败: 500')
  })

  it('ignores send when input is blank', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await renderChat()
    const sendButton = findSendButton()
    act(() => {
      sendButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
