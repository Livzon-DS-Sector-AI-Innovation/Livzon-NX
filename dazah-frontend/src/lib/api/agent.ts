"use client"

import type { components } from "@/types/generated/schema"

export type AgentRole = "system" | "user" | "assistant" | "tool"

export interface AgentMessage {
  id?: string
  role: AgentRole
  content: string
  created_at?: string
  metadata?: Record<string, unknown>
}

export type AgentAttachmentInput = components["schemas"]["AgentAttachmentIn"]

export interface AgentConfirmation {
  id: string
  operation: string
  summary: string
  risk_level: "low" | "medium" | "high" | string
  status: string
  expires_at: string
  request_payload?: Record<string, unknown>
  result_payload?: Record<string, unknown> | null
  executed_at?: string | null
  updated_at?: string | null
}

export type AgentSessionItem = components["schemas"]["AgentSessionItem"]
export type AgentSessionPage = components["schemas"]["AgentSessionPage"]
export type AgentSessionDetail = components["schemas"]["AgentSessionDetail"]

export interface LivzonTaskTrigger {
  id: string
  automation_id: string
  trigger_type: string
  status: string
  schedule: Record<string, unknown>
  event_type?: string | null
  event_filter?: Record<string, unknown>
  timezone: string
  next_fire_at?: string | null
  last_fired_at?: string | null
}

export interface LivzonTaskItem {
  id: string
  owner_user_id: string
  name: string
  description?: string | null
  scope_type: string
  status: string
  active_version?: number | null
  triggers: LivzonTaskTrigger[]
  last_run_status?: string | null
  last_run_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  legacy_source_workflow_id?: string | null
}

export interface LivzonTaskPage {
  items: LivzonTaskItem[]
  page: number
  page_size: number
  total: number
}

export interface LivzonTaskVersion {
  id: string
  automation_id: string
  version: number
  definition: Record<string, unknown>
  change_summary?: string | null
  created_at?: string | null
}

export interface AgentChatData {
  session_id: string
  message: AgentMessage
  pending_confirmations: AgentConfirmation[]
  tool_trace: Record<string, unknown>[]
}

export interface AgentConfirmationExecuteData {
  confirmation: AgentConfirmation
  result: {
    ok: boolean
    operation: string
    data?: unknown
    meta?: Record<string, unknown>
  }
}

interface ApiEnvelope<T> {
  success?: boolean
  code?: number
  message?: string
  data?: T
}

async function readEnvelope<T>(response: Response): Promise<T> {
  const text = await response.text()
  let payload: ApiEnvelope<T> | null = null
  if (text) {
    try {
      payload = JSON.parse(text) as ApiEnvelope<T>
    } catch {
      if (!response.ok) {
        throw new Error(text || `请求失败 (${response.status})`)
      }
      throw new Error("服务返回了无法解析的数据")
    }
  }
  if (!payload) {
    if (!response.ok) {
      throw new Error(`请求失败 (${response.status})`)
    }
    return undefined as T
  }
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || `请求失败 (${response.status})`)
  }
  if (payload.data === undefined) {
    return payload as T
  }
  return payload.data
}

export async function sendAgentMessage(input: {
  session_id?: string | null
  message: string
  context?: Record<string, unknown>
  attachments?: AgentAttachmentInput[]
}): Promise<AgentChatData> {
  const response = await fetch("/api/v1/agent/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(input),
  })
  return readEnvelope<AgentChatData>(response)
}

export async function streamAgentMessage(
  input: {
    session_id?: string | null
    message: string
    context?: Record<string, unknown>
    attachments?: AgentAttachmentInput[]
  },
  handlers: {
    onStart?: (data: { session_id?: string }) => void
    onDelta?: (text: string) => void
    onDone?: (data: AgentChatData) => void
    onPing?: () => void
  },
  options: {
    signal?: AbortSignal
  } = {},
): Promise<void> {
  const response = await fetch("/api/v1/agent/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(input),
    signal: options.signal,
  })
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "")
    throw new Error(text || `请求失败 (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  function handleFrame(frame: string) {
    let event = "message"
    const dataLines: string[] = []
    for (const line of frame.split(/\r?\n/)) {
      if (!line || line.startsWith(":")) {
        continue
      }
      if (line.startsWith("event:")) {
        event = line.slice(6).trim()
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).replace(/^ /, ""))
      }
    }
    if (event === "ping") {
      handlers.onPing?.()
      return
    }
    if (dataLines.length === 0) return
    const rawData = dataLines.join("\n")
    let data: Record<string, unknown>
    try {
      const parsed = JSON.parse(rawData) as unknown
      data = typeof parsed === "object" && parsed !== null
        ? parsed as Record<string, unknown>
        : { data: parsed }
    } catch {
      data = { message: rawData, text: rawData }
    }

    if (event === "start") {
      handlers.onStart?.({ session_id: typeof data.session_id === "string" ? data.session_id : undefined })
    } else if (event === "delta") {
      handlers.onDelta?.(typeof data.text === "string" ? data.text : "")
    } else if (event === "done") {
      handlers.onDone?.(data as unknown as AgentChatData)
    } else if (event === "error") {
      throw new Error(typeof data.message === "string" ? data.message : "中枢助手请求失败")
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() ?? ""
      for (const frame of frames) {
        if (frame.trim()) handleFrame(frame)
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) handleFrame(buffer)
  } finally {
    reader.releaseLock()
  }
}

export async function executeAgentConfirmation(
  confirmationId: string,
): Promise<AgentConfirmationExecuteData> {
  const response = await fetch(`/api/v1/agent/confirmations/${confirmationId}/execute`, {
    method: "POST",
    credentials: "include",
  })
  return readEnvelope<AgentConfirmationExecuteData>(response)
}

export async function cancelAgentConfirmation(
  confirmationId: string,
): Promise<AgentConfirmation> {
  const response = await fetch(`/api/v1/agent/confirmations/${confirmationId}/cancel`, {
    method: "POST",
    credentials: "include",
  })
  return readEnvelope<AgentConfirmation>(response)
}

export async function fetchAgentSessions(
  page = 1,
  pageSize = 20,
): Promise<AgentSessionPage> {
  const response = await fetch(
    `/api/v1/agent/sessions?page=${page}&page_size=${pageSize}`,
    { credentials: "include", cache: "no-store" },
  )
  return readEnvelope<AgentSessionPage>(response)
}

export async function fetchAgentSession(
  sessionId: string,
): Promise<AgentSessionDetail> {
  const response = await fetch(`/api/v1/agent/sessions/${sessionId}`, {
    credentials: "include",
    cache: "no-store",
  })
  return readEnvelope<AgentSessionDetail>(response)
}

export async function archiveAgentSession(
  sessionId: string,
): Promise<AgentSessionItem> {
  const response = await fetch(`/api/v1/agent/sessions/${sessionId}/archive`, {
    method: "POST",
    credentials: "include",
  })
  return readEnvelope<AgentSessionItem>(response)
}

export async function fetchLivzonTasks(): Promise<LivzonTaskPage> {
  const response = await fetch("/api/v1/agent/automations?scope=mine&page=1&page_size=100", {
    credentials: "include",
  })
  return readEnvelope<LivzonTaskPage>(response)
}

export async function fetchLivzonTaskVersions(
  automationId: string,
): Promise<LivzonTaskVersion[]> {
  const response = await fetch(`/api/v1/agent/automations/${automationId}/versions`, {
    credentials: "include",
  })
  return readEnvelope<LivzonTaskVersion[]>(response)
}
