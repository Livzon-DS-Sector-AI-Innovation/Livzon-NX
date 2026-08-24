import { ExamGenerateResponse, ExamExportData } from '@/types/hr'


export interface ChatAttachment {
  type: 'image'
  mime_type: string
  data: string
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  reasoning_content?: string
  attachments?: ChatAttachment[]
}

export interface HrPageContext {
  page: string
  filters?: Record<string, string | null | undefined>
  selected_ids?: string[]
  data_summary?: Record<string, string | number | null | undefined>
}

export async function streamChat(
  messages: ChatMessage[],
  pageContext: HrPageContext | null,
  onChunk: (type: 'reasoning' | 'content', text: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
) {
  try {
    const res = await fetch(`/api/v1/ai/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages,
        page_context: pageContext,
      }),
    })

    if (!res.ok) {
      const text = await res.text()
      throw new Error(`请求失败: ${res.status} ${text}`)
    }

    const reader = res.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    if (!reader) {
      throw new Error('无法读取响应流')
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.reasoning_content) {
              onChunk('reasoning', data.reasoning_content)
            }
            if (data.content) {
              onChunk('content', data.content)
            }
            if (data.done) onDone()
          } catch {
            // ignore malformed lines
          }
        }
      }
    }

    onDone()
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)))
  }
}

export async function generateExamQuestions(data: unknown): Promise<any> {
  const res = await fetch('/api/v1/ai/exam/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data
}

export async function exportExam(data: unknown): Promise<any> {
  const res = await fetch(`/api/v1/ai/exam/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data
}
