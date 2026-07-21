import type { components } from '@/types/generated/schema'

export type AgentAuditSessionItem =
  components['schemas']['AgentAuditSessionItem']
export type AgentAuditSessionPage =
  components['schemas']['AgentAuditSessionPage']
export type AgentAuditSessionDetail =
  components['schemas']['AgentAuditSessionDetail']
export type AgentAuditOperationItem =
  components['schemas']['AgentAuditOperationItem']

interface ApiEnvelope<T> {
  data?: T
  message?: string
  detail?: string
}

async function fetchAudit<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/agent/audit${path}`, {
    credentials: 'include',
    cache: 'no-store',
  })
  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `请求失败 (${response.status})`)
  }
  return (payload?.data ?? payload) as T
}

export async function fetchAgentAuditSessions(params: {
  page: number
  pageSize: number
  keyword?: string
  channel?: string
  startedAt?: string
  endedAt?: string
}): Promise<AgentAuditSessionPage> {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.channel) search.set('channel', params.channel)
  if (params.startedAt) search.set('started_at', params.startedAt)
  if (params.endedAt) search.set('ended_at', params.endedAt)
  return fetchAudit<AgentAuditSessionPage>(`/sessions?${search}`)
}

export async function fetchAgentAuditSession(
  sessionId: string
): Promise<AgentAuditSessionDetail> {
  return fetchAudit<AgentAuditSessionDetail>(`/sessions/${sessionId}`)
}
