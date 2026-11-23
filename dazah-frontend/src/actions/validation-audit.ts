'use server'

import { getAuthHeaders } from '@/lib/auth'
import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { requireActionResponse, serverActionResult, type BusinessErrorMessages } from '@/lib/server-action-result'
import { uncertainWriteMessage } from '@/lib/user-error'
import type { components } from '@/types/generated/schema'
import type {
  ValidationAuditFileListItem,
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

function auditRead<T>(operation: string, path: string, allowMissing = false) {
  return serverActionResult(`registration.validationAudit.${operation}`, async (): Promise<T | null> => {
    const response = await fetch(`${BASE}${path}`, { headers: await getAuthHeaders() })
    if (allowMissing && response.status === 404) return null
    await requireActionResponse(response)
    return response.json()
  }, '暂时无法读取验证审核数据，请刷新后重试')
}

// ── Server-side data fetching ───────────────────────────────

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
  return auditRead<ValidationAuditTaskListResponse>('list', `/tasks?${searchParams}`)
}

export async function fetchTaskByIdServer(id: string) {
  return auditRead<ValidationAuditTaskResponse>('get', `/tasks/${encodeURIComponent(id)}`, true)
}

export async function fetchFilesServer(taskId: string) {
  return auditRead<ValidationAuditDataResponse<ValidationAuditFileListItem[]>>('files', `/tasks/${encodeURIComponent(taskId)}/files`)
}

export async function fetchIssuesServer(taskId: string, issueType?: string) {
  const params = new URLSearchParams()
  if (issueType) params.set('issue_type', issueType)
  return auditRead<ValidationAuditDataResponse<ValidationAuditIssue[]>>('issues', `/tasks/${encodeURIComponent(taskId)}/issues?${params}`)
}

export async function fetchReportServer(taskId: string) {
  return auditRead<ValidationAuditDataResponse<ValidationAuditReport>>('report', `/tasks/${encodeURIComponent(taskId)}/report`, true)
}

// ── Write operations ──────────────────────────────────────

type AuditErrorCode = components['schemas']['ValidationAuditErrorCode']
type AuditUploadItem = components['schemas']['ValidationAuditUploadSuccess'] | components['schemas']['ValidationAuditUploadFailure']

const uploadErrors = {
  400: { VALIDATION_AUDIT_FILE_LIMIT: '本次上传的文件过多，请分批上传' },
} satisfies Partial<Record<number, Partial<Record<AuditErrorCode, string>>>>

const parseErrors = {
  409: { VALIDATION_AUDIT_NO_FILES: '请先上传审核文件，再执行解析' },
  422: { VALIDATION_AUDIT_FILE_UNREADABLE: '无法读取审核文件，请检查文件是否损坏或受密码保护，必要时联系管理员' },
} satisfies Partial<Record<number, Partial<Record<AuditErrorCode, string>>>>

const auditErrors = {
  409: {
    VALIDATION_AUDIT_NO_FILES: '请上传并解析审核文件，再执行审核',
    VALIDATION_AUDIT_NO_PARSED_FILES: '请先解析审核文件，再执行审核',
    VALIDATION_AUDIT_CROSS_FILES_REQUIRED: '联合审核需要方案和报告，请补齐并解析两类文件',
  },
} satisfies Partial<Record<number, Partial<Record<AuditErrorCode, string>>>>

function auditMutation<T = unknown>(
  operation: string,
  label: string,
  path: string,
  options: RequestInit,
  refreshPaths: string[],
  businessMessages?: BusinessErrorMessages,
) {
  return serverActionResult(`registration.validationAudit.${operation}`, async (): Promise<T> => {
    const headers = { ...await getAuthHeaders() }
    if (options.body instanceof FormData) delete headers['Content-Type']
    const response = await fetch(`${BASE}${path}`, { ...options, headers })
    await requireActionResponse(response, businessMessages)
    const payload = await response.json()
    for (const refreshPath of refreshPaths) revalidatePath(refreshPath)
    return payload.data
  }, uncertainWriteMessage(label))
}

const listPath = '/registration/validation-audit'

export async function createValidationAuditTask(data: ValidationAuditTaskCreate) {
  return auditMutation<ValidationAuditTask>('create', '审核任务创建', '/tasks', {
    method: 'POST', body: JSON.stringify(data),
  }, [listPath])
}

export async function deleteValidationAuditTask(taskId: string) {
  return auditMutation('delete', '审核任务删除', `/tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
  }, [listPath])
}

export async function uploadValidationAuditFiles(taskId: string, formData: FormData) {
  const id = encodeURIComponent(taskId)
  return auditMutation<AuditUploadItem[]>('upload', '审核文件上传', `/tasks/${id}/files`, {
    method: 'POST', body: formData,
  }, [`${listPath}/${id}`], uploadErrors)
}

export async function parseValidationAuditFiles(taskId: string) {
  const id = encodeURIComponent(taskId)
  return auditMutation('parse', '审核文件解析', `/tasks/${id}/parse`, {
    method: 'POST',
  }, [`${listPath}/${id}`], parseErrors)
}

export async function runValidationAudit(taskId: string) {
  const id = encodeURIComponent(taskId)
  return auditMutation('run', '验证审核执行', `/tasks/${id}/audit`, {
    method: 'POST',
  }, [`${listPath}/${id}`, listPath], auditErrors)
}
