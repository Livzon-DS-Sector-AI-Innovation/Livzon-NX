import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  EMERGENCY_MGMT_PAGE_KEY,
  parsePlanChatFrame,
  streamEmergencyPlanChat,
} from './safety-emergency-plan-chat'

function sseResponse(frames: string[], status = 200): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame))
      }
      controller.close()
    },
  })
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('parsePlanChatFrame', () => {
  it('按键分发 status/reply/revision/warnings/content/done', () => {
    const handlers = {
      onStatus: vi.fn(),
      onReply: vi.fn(),
      onRevision: vi.fn(),
      onWarnings: vi.fn(),
      onContent: vi.fn(),
      onDone: vi.fn(),
    }
    expect(parsePlanChatFrame('data: {"status":"已连接"}', handlers)).toBe(false)
    expect(handlers.onStatus).toHaveBeenCalledWith('已连接')
    parsePlanChatFrame('data: {"reply":"已修改"}', handlers)
    expect(handlers.onReply).toHaveBeenCalledWith('已修改')
    parsePlanChatFrame('data: {"revision":5,"sections":["scenario"]}', handlers)
    expect(handlers.onRevision).toHaveBeenCalledWith(5, ['scenario'])
    parsePlanChatFrame('data: {"warnings":[{"code":"x"}]}', handlers)
    expect(handlers.onWarnings).toHaveBeenCalledWith([{ code: 'x' }])
    parsePlanChatFrame('data: {"content":{"revision_no":5}}', handlers)
    expect(handlers.onContent).toHaveBeenCalledWith({ revision_no: 5 })
    expect(parsePlanChatFrame('data: {"done":true}', handlers)).toBe(true)
    expect(handlers.onDone).toHaveBeenCalled()
  })
})

describe('streamEmergencyPlanChat', () => {
  it('携带页面权限头并按帧回调（跨 chunk 拼接）', async () => {
    const fetchMock = vi.fn(async () =>
      sseResponse([
        'data: {"status":"已连接"}\n\n',
        'data: {"reply":"已把情景',
        '改为夜班"}\n\ndata: {"revision":2,"sections":["scenario"]}\n\n',
        'data: {"done":true}\n\n',
      ])
    )
    vi.stubGlobal('fetch', fetchMock)
    const onReply = vi.fn()
    const onRevision = vi.fn()
    const onDone = vi.fn()
    const result = await streamEmergencyPlanChat(
      'plan-1',
      '改成夜班',
      'scenario',
      { onReply, onRevision, onDone }
    )
    expect(result).toBe('已把情景改为夜班')
    expect(onReply).toHaveBeenCalledWith('已把情景改为夜班')
    expect(onRevision).toHaveBeenCalledWith(2, ['scenario'])
    expect(onDone).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/safety/emergency-plans/plan-1/ai/chat')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['X-Dazah-Page-Key']).toBe(
      EMERGENCY_MGMT_PAGE_KEY
    )
    expect(JSON.parse(init.body as string)).toEqual({
      message: '改成夜班',
      section: 'scenario',
    })
  })

  it('非 2xx 时抛出后端文案', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ message: '当前接口尚未完成页面权限登记' }), {
          status: 403,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    )
    await expect(
      streamEmergencyPlanChat('plan-1', 'x', null, {})
    ).rejects.toThrow('当前接口尚未完成页面权限登记')
  })

  it('非 JSON 错误体保留状态码', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('bad gateway', { status: 502 }))
    )
    await expect(streamEmergencyPlanChat('plan-1', 'x', null, {})).rejects.toThrow(
      '请求失败 (502)'
    )
  })
})
