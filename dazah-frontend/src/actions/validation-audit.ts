'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import type {
  ValidationAuditFile,
  ValidationAuditIssue,
  ValidationAuditReport,
  ValidationAuditTask,
  ValidationAuditTaskCreate,
  ValidationAuditTaskListResponse,
  ValidationAuditTaskResponse,
} from '@/types/validation-audit'

interface ValidationAuditDataResponse<T> {
  code: number
  message: string
  data: T
}

const API_BASE_URL = getServerApiBaseUrl()
const BASE = `${API_BASE_URL}/api/v1/registration/validation-audit`

async function actionFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
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
  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text)
}

// ── Server-side data fetching (for Server Components) ─────

export async function fetchTasksServer(params?: {
  product_name?: string
  source_company?: string
  status?: string
  page?: number
  page_size?: number
}) {
  const searchParams = new URLSearchParams()
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.source_company) searchParams.set('source_company', params.source_company)
  if (params?.status) searchParams.set('status', params.status)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  try {
    return await actionFetch<ValidationAuditTaskListResponse>(
      `${BASE}/tasks?${searchParams.toString()}`,
    )
  } catch {
    return null
  }
}

export async function fetchTaskByIdServer(id: string) {
  try {
    return await actionFetch<ValidationAuditTaskResponse>(`${BASE}/tasks/${id}`)
  } catch {
    return null
  }
}

export async function fetchFilesServer(taskId: string) {
  try {
    return await actionFetch<ValidationAuditDataResponse<ValidationAuditFile[]>>(
      `${BASE}/tasks/${taskId}/files`,
    )
  } catch {
    return null
  }
}

export async function fetchIssuesServer(taskId: string, issueType?: string) {
  const params = new URLSearchParams()
  if (issueType) params.set('issue_type', issueType)
  try {
    return await actionFetch<ValidationAuditDataResponse<ValidationAuditIssue[]>>(
      `${BASE}/tasks/${taskId}/issues?${params.toString()}`,
    )
  } catch {
    return null
  }
}

export async function fetchReportServer(taskId: string) {
  try {
    return await actionFetch<ValidationAuditDataResponse<ValidationAuditReport | null>>(
      `${BASE}/tasks/${taskId}/report`,
    )
  } catch {
    return null
  }
}

// ── Write operations ──────────────────────────────────────

export async function createValidationAuditTask(
  data: ValidationAuditTaskCreate
): Promise<{ success: boolean; message: string; data?: ValidationAuditTask }> {
  try {
    const response = await fetch(`${BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    const json = await response.json()
    if (!response.ok) {
      return { success: false, message: json.message || '创建失败' }
    }
    revalidatePath('/registration/validation-audit')
    return { success: true, message: json.message || '创建成功', data: json.data }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '创建任务失败',
    }
  }
}

export async function deleteValidationAuditTask(
  taskId: string
): Promise<{ success: boolean; message: string }> {
  try {
    const response = await fetch(`${BASE}/tasks/${taskId}`, {
      method: 'DELETE',
    })
    const json = await response.json()
    if (!response.ok) {
      return { success: false, message: json.message || '删除失败' }
    }
    revalidatePath('/registration/validation-audit')
    return { success: true, message: json.message || '删除成功' }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '删除任务失败',
    }
  }
}

export async function uploadValidationAuditFiles(
  taskId: string,
  formData: FormData
): Promise<{ success: boolean; message: string; data?: unknown }> {
  try {
    const response = await fetch(`${BASE}/tasks/${taskId}/files`, {
      method: 'POST',
      body: formData,
    })
    const json = await response.json()
    if (!response.ok) {
      return { success: false, message: json.message || '上传失败' }
    }
    revalidatePath(`/registration/validation-audit/${taskId}`)
    return { success: true, message: json.message || '上传成功', data: json.data }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '上传文件失败',
    }
  }
}

export async function parseValidationAuditFiles(
  taskId: string
): Promise<{ success: boolean; message: string; data?: unknown }> {
  try {
    const response = await fetch(`${BASE}/tasks/${taskId}/parse`, {
      method: 'POST',
    })
    const json = await response.json()
    if (!response.ok) {
      return { success: false, message: json.message || '解析失败' }
    }
    revalidatePath(`/registration/validation-audit/${taskId}`)
    return { success: true, message: json.message || '解析完成', data: json.data }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '文件解析失败',
    }
  }
}

export async function runValidationAudit(
  taskId: string
): Promise<{ success: boolean; message: string; data?: unknown }> {
  try {
    const response = await fetch(`${BASE}/tasks/${taskId}/audit`, {
      method: 'POST',
    })
    if (!response.ok) {
      const json = await response.json().catch(() => ({}))
      return { success: false, message: json.message || '审核失败' }
    }
    const json = await response.json()
    revalidatePath(`/registration/validation-audit/${taskId}`)
    revalidatePath('/registration/validation-audit')
    return { success: true, message: json.message || '审核完成', data: json.data }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '审核执行失败',
    }
  }
}
