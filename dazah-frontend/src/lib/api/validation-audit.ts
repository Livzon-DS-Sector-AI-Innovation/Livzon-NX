// Validation Audit — client-side API calls (relative paths, proxied by Next.js)

import type {
  ValidationAuditTaskListResponse,
  ValidationAuditTaskResponse,
  ValidationAuditTaskListParams,
} from '@/types/validation-audit'

const BASE = '/api/v1/registration/validation-audit'

export async function fetchValidationAuditTasks(
  params?: ValidationAuditTaskListParams
): Promise<ValidationAuditTaskListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.source_company) searchParams.set('source_company', params.source_company)
  if (params?.status) searchParams.set('status', params.status)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await fetch(`${BASE}/tasks?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取审核任务列表失败')
  return res.json()
}

export async function fetchValidationAuditTaskById(
  id: string
): Promise<ValidationAuditTaskResponse> {
  const res = await fetch(`${BASE}/tasks/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取审核任务详情失败')
  return res.json()
}

export async function fetchValidationAuditFiles(taskId: string) {
  const res = await fetch(`${BASE}/tasks/${taskId}/files`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取文件列表失败')
  return res.json()
}

export async function fetchValidationAuditIssues(
  taskId: string,
  issueType?: string
) {
  const params = new URLSearchParams()
  if (issueType) params.set('issue_type', issueType)
  const res = await fetch(`${BASE}/tasks/${taskId}/issues?${params.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取问题列表失败')
  return res.json()
}

export async function fetchValidationAuditReport(taskId: string) {
  const res = await fetch(`${BASE}/tasks/${taskId}/report`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取审核报告失败')
  return res.json()
}
