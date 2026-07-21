import {
  PilotWorkflow,
  PilotWorkflowFilters,
  PilotWorkflowListResponse,
} from '@/types/pilot-workflow'

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const data = await response.json()
  return data.data
}

export async function fetchPilotWorkflows(
  filters: PilotWorkflowFilters = {}
): Promise<PilotWorkflowListResponse> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.page_size) params.set('page_size', String(filters.page_size))

  const qs = params.toString()
  const url = `/api/v1/research/pilot/workflow${qs ? `?${qs}` : ''}`
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const json = await response.json()
  return {
    items: json.data,
    total: json.meta?.total ?? 0,
    page: json.meta?.page ?? 1,
    page_size: json.meta?.page_size ?? 20,
  }
}

export async function fetchPilotWorkflow(
  workflowId: string
): Promise<PilotWorkflow> {
  const url = `/api/v1/research/pilot/workflow/${workflowId}`
  return apiFetch<PilotWorkflow>(url)
}
