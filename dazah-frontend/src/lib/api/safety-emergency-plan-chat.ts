/** 应急预案 AI 工作台：浏览器端 SSE 对话客户端。

经 `/api/v1/...` 代理流式透传（`src/app/api/[...path]/route.ts` 对
text/event-stream 直接转发 body）；显式携带 `X-Dazah-Page-Key`，
保证本地开发（无 nginx 注入页面头）时非管理员也能通过页面权限校验。
 */

export const EMERGENCY_MGMT_PAGE_KEY = 'safety:emergency-accident:emergency-mgmt'

export interface PlanChatWarning {
  code: string
  severity: 'high' | 'medium' | 'low'
  section: string
  quote: string
  message: string
  replacement: string | null
}

export interface PlanChatHandlers {
  onStatus?: (text: string) => void
  onReply?: (text: string) => void
  onRevision?: (revisionNo: number, sections: string[]) => void
  onWarnings?: (warnings: PlanChatWarning[]) => void
  onContent?: (content: unknown) => void
  onMessage?: (text: string) => void
  onDone?: () => void
}

interface SseFrame {
  status?: string
  reply?: string
  revision?: number
  sections?: string[]
  warnings?: PlanChatWarning[]
  content?: unknown
  done?: boolean
}

/** 解析 SSE 文本流，按 `data: {...}` 帧分发给 handlers。 */
export function parsePlanChatFrame(
  raw: string,
  handlers: PlanChatHandlers
): boolean {
  const frame = JSON.parse(raw.slice(5).trim()) as SseFrame
  let done = false
  if (frame.status) handlers.onStatus?.(frame.status)
  if (frame.reply !== undefined) handlers.onReply?.(frame.reply)
  if (frame.revision !== undefined) {
    handlers.onRevision?.(frame.revision, frame.sections ?? [])
  }
  if (frame.warnings) handlers.onWarnings?.(frame.warnings)
  if (frame.content !== undefined) handlers.onContent?.(frame.content)
  if (frame.done) {
    handlers.onDone?.()
    done = true
  }
  return done
}

/** 发起应急预案 AI 对话（流式）。返回结束后端给出的最终说明（或错误文案）。 */
export async function streamEmergencyPlanChat(
  planId: string,
  message: string,
  section: string | null,
  handlers: PlanChatHandlers,
  signal?: AbortSignal
): Promise<string> {
  const response = await fetch(
    `/api/v1/safety/emergency-plans/${planId}/ai/chat`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Dazah-Page-Key': EMERGENCY_MGMT_PAGE_KEY,
      },
      body: JSON.stringify({ message, section }),
      signal,
    }
  )
  if (!response.ok || !response.body) {
    let detail = `请求失败 (${response.status})`
    try {
      const payload = (await response.json()) as { message?: string }
      if (payload.message) detail = payload.message
    } catch {
      // 非 JSON 错误体时保留状态码文案
    }
    throw new Error(detail)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalText = ''
  let finished = false
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let index: number
    for (;;) {
      index = buffer.indexOf('\n')
      if (index < 0) break
      const line = buffer.slice(0, index).trim()
      buffer = buffer.slice(index + 1)
      if (!line.startsWith('data: ')) continue
      const isDone = parsePlanChatFrame(line, {
        ...handlers,
        onMessage: (text) => {
          finalText = text
          handlers.onMessage?.(text)
        },
        onReply: (text) => {
          finalText = text
          handlers.onReply?.(text)
        },
      })
      if (isDone) finished = true
    }
  }
  if (!finished && finalText) handlers.onDone?.()
  return finalText
}
