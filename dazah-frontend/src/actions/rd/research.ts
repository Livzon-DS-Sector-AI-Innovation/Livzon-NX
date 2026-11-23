'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import { requireActionResponse, serverActionResult } from '@/lib/server-action-result'
import { uncertainWriteMessage } from '@/lib/user-error'
import { ResearchProjectCreate, ResearchProjectUpdate } from '@/types/rd'

const API_BASE_URL = getServerApiBaseUrl()

async function actionFetch<T>(url: string, options?: RequestInit): Promise<T | null> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    let errorMessage = `请求失败: ${response.status} ${response.statusText}`
    try {
      const errorJson = JSON.parse(errorBody)
      if (errorJson.message) errorMessage = errorJson.message
    } catch {}
    throw new Error(errorMessage)
  }
  if (response.status === 204) return null
  const result = await response.json()
  return result.data
}

export async function createResearchProject(data: ResearchProjectCreate) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/research/projects`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/rd')
  return result
}

export async function updateResearchProject(projectId: string, data: ResearchProjectUpdate) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/research/projects/${projectId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/rd')
  return result
}

export async function deleteResearchProject(projectId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/research/projects/${projectId}`, {
    method: 'DELETE',
  })
  revalidatePath('/rd')
}

// ===== Pilot Workflow Server Actions =====

export async function createPilotWorkflow(data: {
  product_name: string
  scale_up_ratio: number
  equipment_type: string
  equipment_volume: number
  project_id?: string
  input_context?: Record<string, unknown>
}) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/research/pilot/workflow`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/rd/pilot-workflow')
  return result
}

export async function startPilotWorkflow(workflowId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/research/pilot/workflow/${workflowId}/start`, {
    method: 'POST',
  })
  revalidatePath(`/rd/pilot-workflow/${workflowId}`)
  revalidatePath('/rd/pilot-workflow')
  return result
}

export async function approvePilotWorkflowStep(workflowId: string) {
  return pilotWorkflowWrite('approve', '中试步骤确认', workflowId)
}

function pilotWorkflowWrite(operation: 'approve' | 'upload', label: string, workflowId: string, formData?: FormData) {
  return serverActionResult(`research.pilotWorkflow.${operation}`, async (): Promise<unknown> => {
    const id = encodeURIComponent(workflowId)
    const headers = { ...await getAuthHeaders() }
    if (formData) delete headers['Content-Type']
    const response = await fetch(`${API_BASE_URL}/api/v1/research/pilot/workflow/${id}/${operation}`, {
      method: 'POST',
      headers,
      body: formData,
    })
    await requireActionResponse(response)
    const payload = await response.json()
    revalidatePath(`/rd/pilot-workflow/${id}`)
    if (operation === 'approve') revalidatePath('/rd/pilot-workflow')
    return payload.data
  }, uncertainWriteMessage(label))
}

export async function uploadPilotWorkflowDocument(workflowId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)

  return pilotWorkflowWrite('upload', '中试文档上传', workflowId, formData)
}

export async function deletePilotWorkflow(workflowId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/research/pilot/workflow/${workflowId}`, {
    method: 'DELETE',
  })
  revalidatePath('/rd/pilot-workflow')
}

// ─── Server-side fetch functions (for Server Components) ───

export async function fetchResearchProjects(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.keyword) searchParams.set('keyword', params.keyword)
  if (params.status) searchParams.set('status', params.status)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE_URL}/api/v1/research/projects?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取研发项目列表失败')
  return res.json()
}

export async function fetchRoutes(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.project_id) searchParams.set('project_id', params.project_id)
  if (params.status) searchParams.set('status', params.status)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE_URL}/api/v1/research/routes?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取工艺路线列表失败')
  return res.json()
}

export async function fetchPilotWorkflows(params: any = {}): Promise<any> {
  const searchParams = new URLSearchParams()
  if (params.status) searchParams.set('status', params.status)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  searchParams.set('page', String(params.page || 1))
  searchParams.set('page_size', String(params.page_size || 20))

  const res = await fetch(`${API_BASE_URL}/api/v1/research/pilot/workflow?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  const json = await res.json()
  return {
    items: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchPilotWorkflow(workflowId: string): Promise<any> {
  const res = await fetch(`${API_BASE_URL}/api/v1/research/pilot/workflow/${workflowId}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取中试工作流详情失败')
  const json = await res.json()
  return json.data
}
