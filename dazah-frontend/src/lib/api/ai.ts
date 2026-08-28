import {
  ExamGenerateResponse,
  ExamExportData,
  OralExamFile,
  OralExamGenerateRequest,
  OralExamGenerateResponse,
  WrittenExamGenerateResponse,
} from '@/types/hr'
import type { components } from '@/types/generated/schema'


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

type WrittenExamJobStatusResponse = components['schemas']['WrittenExamJobStatusResponse']

export async function generateOralExamQuestions(
  files: OralExamFile[],
  questionCount?: number | null
): Promise<OralExamGenerateResponse> {
  const payload: OralExamGenerateRequest = { files, question_count: questionCount ?? null }
  const res = await fetch('/api/v1/hr/ai/exam/generate-oral', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data
}

export async function submitWrittenExamGenerate(data: Record<string, unknown>): Promise<string> {
  const res = await fetch('/api/v1/hr/ai/exam/generate-written', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data.job_id as string
}

async function fetchWrittenExamStatus(jobId: string, signal?: AbortSignal): Promise<WrittenExamJobStatusResponse> {
  const res = await fetch(`/api/v1/hr/ai/exam/generate-written/${encodeURIComponent(jobId)}`, { signal })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data
}

export async function pollWrittenExamGenerate(
  jobId: string,
  onProgress?: (progress: string) => void,
  options?: { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal }
): Promise<WrittenExamGenerateResponse> {
  const startedAt = Date.now()
  const timeoutMs = options?.timeoutMs ?? 600_000
  while (Date.now() - startedAt <= timeoutMs) {
    if (options?.signal?.aborted) throw new Error('出题任务已取消')
    const status = await fetchWrittenExamStatus(jobId, options?.signal)
    if (status.state === 'completed' && status.result) return status.result as WrittenExamGenerateResponse
    if (status.state === 'failed') throw new Error(status.error || status.progress || 'AI 出题失败')
    onProgress?.(status.progress || '')
    await new Promise((resolve) => setTimeout(resolve, options?.intervalMs ?? 2000))
  }
  throw new Error('AI 出题超时，请稍后重试或减少题目数量')
}

export async function extractExamDocumentText(file: File): Promise<{ text: string; filename: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch('/api/v1/hr/ai/exam/extract-text', { method: 'POST', body: formData })
  if (!res.ok) throw new Error(`文档解析失败: ${res.status}`)
  const json = await res.json()
  return json.data
}

export async function exportWrittenExam(data: Record<string, unknown>): Promise<Blob> {
  const res = await fetch('/api/v1/hr/ai/exam/export-written', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.blob()
}
