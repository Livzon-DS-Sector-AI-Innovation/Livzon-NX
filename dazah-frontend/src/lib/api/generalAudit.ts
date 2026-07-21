import type { components } from '@/types/generated/schema'

export type GeneralAuditLogItem = components['schemas']['GeneralAuditLogItem']
export type GeneralAuditLogDetail = components['schemas']['GeneralAuditLogDetail']
export type GeneralAuditLogPage = components['schemas']['GeneralAuditLogPage']
export type GeneralAuditCategory = GeneralAuditLogItem['category']

interface ApiEnvelope<T> {
  data?: T
  message?: string
  detail?: string
}

async function fetchAudit<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/audit${path}`, {
    credentials: 'include',
    cache: 'no-store',
  })
  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `请求失败 (${response.status})`)
  }
  return (payload?.data ?? payload) as T
}

export async function fetchGeneralAuditLogs(params: {
  category: GeneralAuditCategory
  page: number
  pageSize: number
  keyword?: string
  startedAt?: string
  endedAt?: string
}): Promise<GeneralAuditLogPage> {
  const search = new URLSearchParams({
    category: params.category,
    page: String(params.page),
    page_size: String(params.pageSize),
  })
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.startedAt) search.set('started_at', params.startedAt)
  if (params.endedAt) search.set('ended_at', params.endedAt)
  return fetchAudit<GeneralAuditLogPage>(`/logs?${search}`)
}

export async function fetchGeneralAuditLog(logId: string): Promise<GeneralAuditLogDetail> {
  return fetchAudit<GeneralAuditLogDetail>(`/logs/${logId}`)
}
