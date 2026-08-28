'use server'

import { getServerApiBaseUrl, getBackendFallbackUrls } from '@/lib/server-api'
import { getAuthHeaders } from '@/lib/auth'
import { revalidatePath } from 'next/cache'
import {
  CreateDeviationRequest,
  UpdateDeviationRequest,
  CreateCapaRequest,
  UpdateCapaRequest,
  CreateDepartmentContactRequest,
  UpdateDepartmentContactRequest,
  DeviationAiSession,
  FeishuValidationItem,
  QualityFeishuAppSettingsDetail,
  QualityFeishuEntitySettingItem,
  QualityFeishuSettingsTestResult,
  QualityPullSyncResult,
  AttachmentReview,
  ChangeDetail,
  ChangeActionPlanDetail,
  CreateChangeRequest,
  UpdateChangeRequest,
  CreateDeviationInvestigationPushRecordRequest,
  UpdateDeviationInvestigationPushRecordRequest,
  CreateFeishuDeviationLedgerRecordRequest,
  UpdateFeishuDeviationLedgerRecordRequest,
  DepartmentContactListResponse,
  QualityAiAnalysisLog,
  CreateSupplierQualificationRequest,
  UpdateSupplierQualificationRequest,
  CreateDocumentDepartmentRequest,
  UpdateDocumentDepartmentRequest,
  CreateDocumentEntryRequest,
  UpdateDocumentEntryRequest,
  DocumentCatalogImportResult,
  UploadDocumentEntryAttachmentResult,
  BatchImportDocumentAttachmentsResult,
  DocumentEntryResolveItem,
  DocumentEntryResolveRequest,
  FeishuValidationPullResult,
  InspectionFeishuSyncResponse,
  CreateOosOotRecordRequest,
  CloseOosOotRecordRequest,
  OosOotFeishuSyncOut,
} from '@/types/quality'
import type { components } from '@/types/generated/schema'
import type { LabelVerification } from '@/types/label-verification'

const API_BASE_URL = getServerApiBaseUrl()

type CapaApprovalPayload = components['schemas']['CapaApprovalRequest']
type CapaExecutionTrackPayload = components['schemas']['ExecutionTrack']
type CapaEvaluationPayload = components['schemas']['CapaEvaluationRequest']
type CapaDeptHeadConfirmPayload = components['schemas']['CapaDeptHeadConfirmRequest']
type ChangeActionPlanCreatePayload = components['schemas']['CreateChangeActionPlanRequest']
type ChangeActionPlanUpdatePayload = components['schemas']['UpdateChangeActionPlanRequest']
type ChangeActionPlanFormPayload = Partial<ChangeActionPlanCreatePayload> & Record<string, unknown>
type QualityFeishuAppSettingsUpdatePayload = components['schemas']['UpdateQualityFeishuAppSettingsRequest']
type QualityFeishuEntitySettingUpdatePayload = components['schemas']['UpdateQualityFeishuEntitySettingRequest']
type ApplyDeviationAiSessionPayload = components['schemas']['ApplyDeviationAiSessionRequest']
type ExternalComplaintOut = components['schemas']['ComplaintOut']
type ExternalReturnRecallOut = components['schemas']['ReturnRecallOut']
type ExternalSupplierQualificationCreate =
  components['schemas']['app__modules__quality__schemas__external_quality__CreateSupplierQualificationRequest']

type QueryValue = string | number | boolean | null | undefined
type UntypedFeishuPayload = Record<string, unknown>

interface QualityImportPreviewResult {
  total: number
  valid_count: number
  invalid_count: number
  rows: Array<Record<string, unknown>>
  errors?: string[]
}

interface QualityImportConfirmResult {
  success_count: number
  update_count: number
  skip_count: number
  error_count: number
  errors?: string[]
}

interface ChangeActionPlanSyncResult {
  synced: number
  failed: number
}

interface LabelVerificationListEnvelope {
  data?: LabelVerification[]
  meta?: { total?: number }
}

interface BatchDeleteResult {
  deleted: number
}

function getBackendPath(url: string): string {
  try {
    const parsed = new URL(url)
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return url.startsWith('/') ? url : `/${url}`
  }
}

async function fetchQualityBackend(url: string, options?: RequestInit): Promise<Response> {
  const authHeaders = await getAuthHeaders()
  if (options?.body instanceof FormData) {
    delete authHeaders['Content-Type']
  }
  const path = getBackendPath(url)
  const candidates = Array.from(
    new Set([
      url.startsWith('http') ? url : `${API_BASE_URL}${path}`,
      ...getBackendFallbackUrls().map((baseUrl) => `${baseUrl}${path}`),
    ])
  )

  let lastError: unknown
  for (const candidate of candidates) {
    try {
      return await fetch(candidate, {
        ...options,
        headers: {
          ...authHeaders,
          ...options?.headers,
        },
        cache: 'no-store',
      })
    } catch (error) {
      lastError = error
    }
  }

  const cause = lastError instanceof Error ? lastError.message : 'unknown network error'
  throw new Error(`无法连接后端服务，请检查 API_BASE_URL。最后错误：${cause}`)
}

function unwrapActionResponse<T>(result: unknown): T | null {
  if (
    result &&
    typeof result === 'object' &&
    'data' in result
  ) {
    return (result as { data: T | null }).data
  }
  return result as T
}

function getActionErrorMessage(errorBody: string, response: Response): string {
  const errorMessage = `请求失败: ${response.status} ${response.statusText}`
  try {
    const errorJson = JSON.parse(errorBody)
    if (typeof errorJson.message === 'string' && errorJson.message) {
      return errorJson.message
    }
    if (typeof errorJson.detail === 'string' && errorJson.detail) {
      return errorJson.detail
    }
  } catch {}
  return errorMessage
}

async function actionFetch<T>(url: string, options?: RequestInit): Promise<T | null> {
  const response = await fetchQualityBackend(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    throw new Error(getActionErrorMessage(errorBody, response))
  }
  if (response.status === 204) return null
  const result = await response.json()
  return unwrapActionResponse<T>(result)
}

function requireActionResult<T>(result: T | null, message: string): T {
  if (result === null) throw new Error(message)
  return result
}

// ============ Deviation Actions ============
export async function createDeviation(data: CreateDeviationRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  return result
}

export async function updateDeviation(deviationId: string, data: UpdateDeviationRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
  revalidatePath(`/quality/deviations/${deviationId}`)
  return result
}

export async function deleteDeviation(deviationId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/deviations/${deviationId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/deviations')
}

// ============ CAPA Actions ============
export async function createCapa(data: CreateCapaRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  return result
}

export async function updateCapa(capaId: string, data: UpdateCapaRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function deleteCapa(capaId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/capas')
}

export async function submitCapa(capaId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/submit`, {
    method: 'POST',
  })
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function approveCapa(capaId: string, data: CapaApprovalPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/approve`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function resubmitCapa(capaId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/resubmit`, {
    method: 'POST',
  })
  revalidatePath('/quality/capas')
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function addExecutionTrack(capaId: string, data: CapaExecutionTrackPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/add-execution-track`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function deleteExecutionTrack(capaId: string, index: number) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/delete-execution-track?index=${index}`, {
    method: 'POST',
  })
  revalidatePath(`/quality/capas/${capaId}`)
}

export async function confirmExecution(capaId: string) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/confirm-execution`, {
    method: 'POST',
  })
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function submitEvaluation(capaId: string, data: CapaEvaluationPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/submit-evaluation`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function completeCapaPart(capaId: string, part: 'a' | 'b') {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/complete-part`, {
    method: 'POST',
    body: JSON.stringify({ part }),
  })
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

export async function confirmDeptHead(capaId: string, data: CapaDeptHeadConfirmPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/capas/${capaId}/confirm-dept-head`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath(`/quality/capas/${capaId}`)
  return result
}

// ============ Department Contact Actions ============
export async function createDepartmentContact(data: CreateDepartmentContactRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/department-contacts`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/department-contacts')
  return result
}

export async function updateDepartmentContact(contactId: string, data: UpdateDepartmentContactRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/department-contacts/${contactId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality')
  revalidatePath('/quality/department-contacts')
  return result
}

export async function deleteDepartmentContact(contactId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/department-contacts/${contactId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality')
  revalidatePath('/quality/department-contacts')
}

// ============ Label Verification Server Actions ============
export async function fetchLabelVerificationsServer(params: { page: number; page_size: number }) {
  const searchParams = new URLSearchParams({
    page: params.page.toString(),
    page_size: params.page_size.toString(),
  })
  const result = await actionFetch<LabelVerificationListEnvelope>(
    `${API_BASE_URL}/api/v1/production/label-verifications?${searchParams.toString()}`
  )
  return result
}

function buildQuery(params?: Record<string, QueryValue>) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function actionFetchForm<T>(url: string, formData: FormData): Promise<T | null> {
  const response = await fetchQualityBackend(url, {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    throw new Error(getActionErrorMessage(errorBody, response))
  }
  const result = await response.json()
  return unwrapActionResponse<T>(result)
}

export async function fetchFeishuDepartmentContactsAction(page = 1, page_size = 1000) {
  return requireActionResult(
    await actionFetch<DepartmentContactListResponse>(
      `${API_BASE_URL}/api/v1/quality/department-contacts/feishu?page=${page}&page_size=${page_size}`
    ),
    '未收到部门联系人数据',
  )
}

export async function createFeishuCapa(data: UntypedFeishuPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capas`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/capas')
  return result
}

export async function updateFeishuCapa(recordId: string, data: UntypedFeishuPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capas/${recordId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/capas')
  return result
}

export async function deleteFeishuCapa(recordId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capas/${recordId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/capas')
}

export async function createFeishuCapaPlanTrack(data: UntypedFeishuPayload) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capa-plan-tracks`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/capas/plans')
  return result
}

export async function updateFeishuCapaPlanTrack(recordId: string, data: UntypedFeishuPayload) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/feishu/capa-plan-tracks/${recordId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/quality/capas/plans')
  return result
}

export async function deleteFeishuCapaPlanTrack(recordId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/capa-plan-tracks/${recordId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/capas/plans')
}

export async function createFeishuDeviationLedgerRecord(data: CreateFeishuDeviationLedgerRecordRequest) {
  const result = await actionFetch(`${API_BASE_URL}/api/v1/quality/deviation-ledger-records`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/deviations')
  return result
}

export async function updateFeishuDeviationLedgerRecord(recordId: string, data: UpdateFeishuDeviationLedgerRecordRequest) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/deviation-ledger-records/${recordId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/quality/deviations')
  revalidatePath(`/quality/deviations/${recordId}`)
  return result
}

export async function deleteFeishuDeviationLedgerRecord(recordId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/deviation-ledger-records/${recordId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/deviations')
}

export async function createDeviationInvestigationPushRecord(data: CreateDeviationInvestigationPushRecordRequest) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/deviation-investigation-push-records`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/quality/deviations/investigations')
  return result
}

export async function updateDeviationInvestigationPushRecord(recordId: string, data: UpdateDeviationInvestigationPushRecordRequest) {
  const result = await actionFetch(
    `${API_BASE_URL}/api/v1/quality/deviation-investigation-push-records/${recordId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/quality/deviations/investigations')
  return result
}

export async function deleteDeviationInvestigationPushRecord(recordId: string) {
  await actionFetch(
    `${API_BASE_URL}/api/v1/quality/deviation-investigation-push-records/${recordId}`,
    { method: 'DELETE' }
  )
  revalidatePath('/quality/deviations/investigations')
}

export async function pullQualityRecordsFromFeishu(entity_code?: string): Promise<QualityPullSyncResult> {
  const result = await actionFetch<QualityPullSyncResult>(
    `${API_BASE_URL}/api/v1/quality/feishu-sync/pull${buildQuery({ entity_code })}`,
    { method: 'POST' }
  )
  revalidatePath('/quality')
  if (!result) throw new Error('未收到飞书回拉结果')
  return result
}

export async function ensureDeviationFromReportRecord(recordId: string): Promise<{ deviation_id: string }> {
  const result = await actionFetch<{ deviation_id: string }>(
    `${API_BASE_URL}/api/v1/quality/deviation-report-records/${recordId}/ensure-deviation`,
    { method: 'POST' }
  )
  revalidatePath('/quality/deviations')
  if (!result) throw new Error('未收到关联偏差结果')
  return result
}

export async function updateDeviationAiSession(deviationId: string, supplementText: string): Promise<DeviationAiSession> {
  const result = await actionFetch<DeviationAiSession>(`${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session`, {
    method: 'PUT',
    body: JSON.stringify({ supplement_text: supplementText }),
  })
  if (!result) throw new Error('未收到 AI 会话结果')
  return result
}

export async function regenerateDeviationAiSession(deviationId: string): Promise<DeviationAiSession> {
  const result = await actionFetch<DeviationAiSession>(`${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/regenerate`, {
    method: 'POST',
  })
  if (!result) throw new Error('未收到 AI 会话结果')
  return result
}

export async function applyDeviationAiSession(deviationId: string, data: ApplyDeviationAiSessionPayload): Promise<DeviationAiSession> {
  const result = await actionFetch<DeviationAiSession>(`${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/apply`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  if (!result) throw new Error('未收到 AI 会话结果')
  return result
}

export async function uploadDeviationAiSessionAttachment(deviationId: string, formData: FormData): Promise<DeviationAiSession> {
  const response = await fetchQualityBackend(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/attachments`,
    { method: 'POST', body: formData }
  )
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    throw new Error(getActionErrorMessage(errorBody, response))
  }
  const result = await response.json()
  const data = unwrapActionResponse<DeviationAiSession>(result)
  if (!data) throw new Error('未收到 AI 会话结果')
  return data
}

export async function deleteDeviationAiSessionAttachment(deviationId: string, attachmentId: string): Promise<DeviationAiSession> {
  const result = await actionFetch<DeviationAiSession>(
    `${API_BASE_URL}/api/v1/quality/ai/deviations/${deviationId}/session/attachments/${attachmentId}`,
    { method: 'DELETE' }
  )
  if (!result) throw new Error('未收到 AI 会话结果')
  return result
}

export async function fetchQualityFeishuAppSettingsAction(): Promise<QualityFeishuAppSettingsDetail | null> {
  return actionFetch<QualityFeishuAppSettingsDetail>(`${API_BASE_URL}/api/v1/quality/feishu-settings/app`)
}

export async function updateQualityFeishuAppSettings(data: QualityFeishuAppSettingsUpdatePayload): Promise<QualityFeishuAppSettingsDetail> {
  const result = await actionFetch<QualityFeishuAppSettingsDetail>(`${API_BASE_URL}/api/v1/quality/feishu-settings/app`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  if (!result) throw new Error('未收到飞书应用配置')
  return result
}

export async function testQualityFeishuAppSettings(): Promise<QualityFeishuSettingsTestResult> {
  const result = await actionFetch<QualityFeishuSettingsTestResult>(`${API_BASE_URL}/api/v1/quality/feishu-settings/app/test`, {
    method: 'POST',
  })
  if (!result) throw new Error('未收到飞书测试结果')
  return result
}

export async function updateQualityFeishuEntitySetting(entityCode: string, data: QualityFeishuEntitySettingUpdatePayload): Promise<QualityFeishuEntitySettingItem> {
  const result = await actionFetch<QualityFeishuEntitySettingItem>(`${API_BASE_URL}/api/v1/quality/feishu-settings/entities/${entityCode}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  if (!result) throw new Error('未收到飞书实体配置')
  return result
}

export async function testQualityFeishuEntitySetting(entityCode: string): Promise<QualityFeishuSettingsTestResult> {
  const result = await actionFetch<QualityFeishuSettingsTestResult>(`${API_BASE_URL}/api/v1/quality/feishu-settings/entities/${entityCode}/test`, {
    method: 'POST',
  })
  if (!result) throw new Error('未收到飞书测试结果')
  return result
}

export async function syncInspectionRecordToFeishu(
  resourceCode: string,
  recordId: string,
): Promise<InspectionFeishuSyncResponse> {
  const result = await actionFetch<InspectionFeishuSyncResponse>(
    `${API_BASE_URL}/api/v1/quality/inspection-resources/${resourceCode}/${recordId}/sync-to-feishu`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到飞书推送结果')
  revalidatePath('/quality/inspection')
  return result
}

// ============ OOS/OOT Actions ============
export async function createOosOotRecord(
  data: CreateOosOotRecordRequest,
): Promise<components['schemas']['OosOotRecordOut']> {
  const result = await actionFetch<components['schemas']['OosOotRecordOut']>(
    `${API_BASE_URL}/api/v1/quality/oos-oot/records`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到 OOS/OOT 创建结果')
  revalidatePath('/quality/oos-oot')
  return result
}

export async function startOosOotInvestigation(
  recordId: string,
): Promise<components['schemas']['OosOotRecordOut']> {
  const result = await actionFetch<components['schemas']['OosOotRecordOut']>(
    `${API_BASE_URL}/api/v1/quality/oos-oot/records/${recordId}/start-investigation`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到 OOS/OOT 调查启动结果')
  revalidatePath('/quality/oos-oot')
  return result
}

export async function closeOosOotRecord(
  recordId: string,
  data: CloseOosOotRecordRequest,
): Promise<components['schemas']['OosOotRecordOut']> {
  const result = await actionFetch<components['schemas']['OosOotRecordOut']>(
    `${API_BASE_URL}/api/v1/quality/oos-oot/records/${recordId}/close`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到 OOS/OOT 关闭结果')
  revalidatePath('/quality/oos-oot')
  return result
}

export async function syncOosOotRecordToFeishu(
  recordId: string,
): Promise<OosOotFeishuSyncOut> {
  const result = await actionFetch<OosOotFeishuSyncOut>(
    `${API_BASE_URL}/api/v1/quality/oos-oot/records/${recordId}/sync-to-feishu`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到 OOS/OOT 飞书推送结果')
  revalidatePath('/quality/oos-oot')
  return result
}

export async function createOotLimitProduct(
  data: components['schemas']['CreateOotLimitProductRequest'],
): Promise<components['schemas']['OotLimitProductOut']> {
  const isMigratedLedger = 'document_title' in data
  const result = await actionFetch<components['schemas']['OotLimitProductOut']>(
    `${API_BASE_URL}/api/v1/quality/oos-oot/${isMigratedLedger ? 'oot-limit-products' : 'oot-limits/products'}`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到 OOT 限度产品创建结果')
  revalidatePath('/quality/oos-oot')
  return result
}

export async function createOotLimitItem(
  productIdOrData: string | components['schemas']['CreateOotLimitItemRequest'],
  data?: Record<string, unknown>,
): Promise<components['schemas']['OotLimitItemOut']> {
  const migratedPayload = typeof productIdOrData === 'object' ? productIdOrData : undefined
  const path = migratedPayload
    ? '/api/v1/quality/oos-oot/oot-limit-items'
    : `/api/v1/quality/oos-oot/oot-limits/products/${productIdOrData}/items`
  const result = await actionFetch<components['schemas']['OotLimitItemOut']>(
    `${API_BASE_URL}${path}`,
    { method: 'POST', body: JSON.stringify(migratedPayload ?? data) },
  )
  if (!result) throw new Error('未收到 OOT 限度项目创建结果')
  revalidatePath('/quality/oos-oot')
  return result
}

export async function syncOotLimitProductToFeishu(
  productId: string,
): Promise<OosOotFeishuSyncOut> {
  const result = await actionFetch<OosOotFeishuSyncOut>(
    `${API_BASE_URL}/api/v1/quality/oos-oot/oot-limits/products/${productId}/sync-to-feishu`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到 OOT 限度产品飞书推送结果')
  revalidatePath('/quality/oos-oot')
  return result
}

// ============ External Quality Actions ============
export async function createQualitySupplier(
  data: components['schemas']['CreateSupplierRequest'],
): Promise<components['schemas']['SupplierOut']> {
  const result = await actionFetch<components['schemas']['SupplierOut']>(
    `${API_BASE_URL}/api/v1/quality/suppliers`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到供应商创建结果')
  revalidatePath('/quality/suppliers')
  return result
}

export async function createQualitySupplierQualification(
  supplierId: string,
  data: ExternalSupplierQualificationCreate,
): Promise<components['schemas']['SupplierQualificationOut']> {
  const result = await actionFetch<components['schemas']['SupplierQualificationOut']>(
    `${API_BASE_URL}/api/v1/quality/suppliers/${supplierId}/qualifications`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到供应商资质创建结果')
  revalidatePath('/quality/suppliers')
  return result
}

export async function createQualityComplaint(
  data: components['schemas']['CreateComplaintRequest'],
): Promise<ExternalComplaintOut> {
  const result = await actionFetch<ExternalComplaintOut>(
    `${API_BASE_URL}/api/v1/quality/complaints`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到投诉创建结果')
  revalidatePath('/quality/complaints')
  return result
}

export async function startQualityComplaintInvestigation(
  complaintId: string,
): Promise<ExternalComplaintOut> {
  const result = await actionFetch<ExternalComplaintOut>(
    `${API_BASE_URL}/api/v1/quality/complaints/${complaintId}/start-investigation`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到投诉调查启动结果')
  revalidatePath('/quality/complaints')
  return result
}

export async function respondQualityComplaint(
  complaintId: string,
  data: components['schemas']['RespondComplaintRequest'],
): Promise<ExternalComplaintOut> {
  const result = await actionFetch<ExternalComplaintOut>(
    `${API_BASE_URL}/api/v1/quality/complaints/${complaintId}/respond`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到投诉回复结果')
  revalidatePath('/quality/complaints')
  return result
}

export async function closeQualityComplaint(
  complaintId: string,
): Promise<ExternalComplaintOut> {
  const result = await actionFetch<ExternalComplaintOut>(
    `${API_BASE_URL}/api/v1/quality/complaints/${complaintId}/close`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到投诉关闭结果')
  revalidatePath('/quality/complaints')
  return result
}

export async function createQualityReturnRecall(
  data: components['schemas']['CreateReturnRecallRequest'],
): Promise<ExternalReturnRecallOut> {
  const result = await actionFetch<ExternalReturnRecallOut>(
    `${API_BASE_URL}/api/v1/quality/return-recalls`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到退货/召回创建结果')
  revalidatePath('/quality/return-recalls')
  return result
}

export async function startQualityReturnRecallAssessment(
  recordId: string,
): Promise<ExternalReturnRecallOut> {
  const result = await actionFetch<ExternalReturnRecallOut>(
    `${API_BASE_URL}/api/v1/quality/return-recalls/${recordId}/start-assessment`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到退货/召回评估启动结果')
  revalidatePath('/quality/return-recalls')
  return result
}

export async function startQualityReturnRecallProcessing(
  recordId: string,
  data: components['schemas']['StartReturnRecallProcessingRequest'],
): Promise<ExternalReturnRecallOut> {
  const result = await actionFetch<ExternalReturnRecallOut>(
    `${API_BASE_URL}/api/v1/quality/return-recalls/${recordId}/start-processing`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到退货/召回处置启动结果')
  revalidatePath('/quality/return-recalls')
  return result
}

export async function completeQualityReturnRecall(
  recordId: string,
  data: components['schemas']['CompleteReturnRecallRequest'],
): Promise<ExternalReturnRecallOut> {
  const result = await actionFetch<ExternalReturnRecallOut>(
    `${API_BASE_URL}/api/v1/quality/return-recalls/${recordId}/complete`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到退货/召回完成结果')
  revalidatePath('/quality/return-recalls')
  return result
}

export async function createQualityProductRecord(
  data: Record<string, unknown>,
): Promise<components['schemas']['ProductQualityRecordOut']> {
  const result = await actionFetch<components['schemas']['ProductQualityRecordOut']>(
    `${API_BASE_URL}/api/v1/quality/product-quality`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到产品质量记录创建结果')
  revalidatePath('/quality/product-quality')
  return result
}

export async function createQualityProductStandardItem(
  recordId: string,
  data: components['schemas']['CreateProductQualityStandardItemRequest'],
): Promise<components['schemas']['ProductQualityStandardItemOut']> {
  const result = await actionFetch<components['schemas']['ProductQualityStandardItemOut']>(
    `${API_BASE_URL}/api/v1/quality/product-quality/${recordId}/standard-items`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到产品质量标准明细创建结果')
  revalidatePath('/quality/product-quality')
  return result
}

export async function completeQualityProductRecord(
  recordId: string,
  data: components['schemas']['CompleteProductQualityRecordRequest'],
): Promise<components['schemas']['ProductQualityRecordOut']> {
  const result = await actionFetch<components['schemas']['ProductQualityRecordOut']>(
    `${API_BASE_URL}/api/v1/quality/product-quality/${recordId}/complete`,
    { method: 'POST', body: JSON.stringify(data) },
  )
  if (!result) throw new Error('未收到产品质量记录完成结果')
  revalidatePath('/quality/product-quality')
  return result
}

export async function approveQualityProductRecord(
  recordId: string,
): Promise<components['schemas']['ProductQualityRecordOut']> {
  const result = await actionFetch<components['schemas']['ProductQualityRecordOut']>(
    `${API_BASE_URL}/api/v1/quality/product-quality/${recordId}/approve`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到产品质量记录批准结果')
  revalidatePath('/quality/product-quality')
  return result
}

export async function syncExternalQualityRecordToFeishu(
  resourcePath: string,
  recordId: string,
): Promise<components['schemas']['ExternalQualityFeishuSyncOut']> {
  const result = await actionFetch<components['schemas']['ExternalQualityFeishuSyncOut']>(
    `${API_BASE_URL}/api/v1/quality/${resourcePath}/${recordId}/sync-to-feishu`,
    { method: 'POST' },
  )
  if (!result) throw new Error('未收到外部质量飞书推送结果')
  return result
}

export async function createFeishuValidationAction(data: Partial<FeishuValidationItem>): Promise<FeishuValidationItem | null> {
  const result = await actionFetch<FeishuValidationItem>(`${API_BASE_URL}/api/v1/quality/feishu/validations`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/validation')
  return result
}

export async function updateFeishuValidationAction(recordId: string, data: Partial<FeishuValidationItem>, validationType?: string): Promise<FeishuValidationItem | null> {
  const result = await actionFetch<FeishuValidationItem>(
    `${API_BASE_URL}/api/v1/quality/feishu/validations/${recordId}${buildQuery({ validation_type: validationType })}`,
    {
    method: 'PUT',
    body: JSON.stringify(data),
    }
  )
  revalidatePath('/quality/validation')
  return result
}

export async function deleteFeishuValidationAction(recordId: string, validationType?: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/feishu/validations/${recordId}${buildQuery({ validation_type: validationType })}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/validation')
}

export async function deleteValidation(validationId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/validations/${validationId}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/validation')
}

export async function previewChangeImport(formData: FormData) {
  return requireActionResult(
    await actionFetchForm<QualityImportPreviewResult>(
      `${API_BASE_URL}/api/v1/quality/changes/import/preview`,
      formData,
    ),
    '未收到变更导入预览结果',
  )
}

export async function confirmChangeImport(
  formData: FormData,
  options: { skipDuplicates: boolean; updateExisting: boolean },
) {
  const result = await actionFetchForm<QualityImportConfirmResult>(
    `${API_BASE_URL}/api/v1/quality/changes/import/confirm${buildQuery({
      skip_duplicates: options.skipDuplicates,
      update_existing: options.updateExisting,
    })}`,
    formData,
  )
  revalidatePath('/quality/change')
  return requireActionResult(result, '未收到变更导入结果')
}

export async function previewCapaImport(formData: FormData) {
  return requireActionResult(
    await actionFetchForm<QualityImportPreviewResult>(
      `${API_BASE_URL}/api/v1/quality/capas/import/preview`,
      formData,
    ),
    '未收到CAPA导入预览结果',
  )
}

export async function confirmCapaImport(
  formData: FormData,
  options: { skipDuplicates: boolean; updateExisting: boolean },
) {
  const result = await actionFetchForm<QualityImportConfirmResult>(
    `${API_BASE_URL}/api/v1/quality/capas/import/confirm${buildQuery({
      skip_duplicates: options.skipDuplicates,
      update_existing: options.updateExisting,
    })}`,
    formData,
  )
  revalidatePath('/quality/capas')
  return requireActionResult(result, '未收到CAPA导入结果')
}

export async function previewDeviationImport(formData: FormData) {
  return requireActionResult(
    await actionFetchForm<QualityImportPreviewResult>(
      `${API_BASE_URL}/api/v1/quality/deviations/import/preview`,
      formData,
    ),
    '未收到偏差导入预览结果',
  )
}

export async function confirmDeviationImport(
  formData: FormData,
  options: { skipDuplicates: boolean; updateExisting: boolean },
) {
  const result = await actionFetchForm<QualityImportConfirmResult>(
    `${API_BASE_URL}/api/v1/quality/deviations/import/confirm${buildQuery({
      skip_duplicates: options.skipDuplicates,
      update_existing: options.updateExisting,
    })}`,
    formData,
  )
  revalidatePath('/quality/deviations')
  return requireActionResult(result, '未收到偏差导入结果')
}

export async function createAttachmentReview(data: {
  deviation_id?: string | null
  capa_id?: string | null
  attachment_url: string
  content: string
}): Promise<AttachmentReview> {
  const result = await actionFetch<AttachmentReview>(
    `${API_BASE_URL}/api/v1/quality/attachment-reviews`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    },
  )
  if (!result) throw new Error('未收到审阅意见')
  return result
}

export async function deleteAttachmentReview(reviewId: string) {
  await actionFetch(`${API_BASE_URL}/api/v1/quality/attachment-reviews/${reviewId}`, {
    method: 'DELETE',
  })
}

export async function pullFeishuValidations(validationType?: string): Promise<QualityPullSyncResult> {
  const result = await actionFetch<QualityPullSyncResult>(
    `${API_BASE_URL}/api/v1/quality/feishu-sync/validations/pull${buildQuery({ validation_type: validationType })}`,
    { method: 'POST' },
  )
  revalidatePath('/quality/validation')
  if (!result) throw new Error('未收到验证回拉结果')
  return result
}

export async function syncChangesFromFeishu(): Promise<QualityPullSyncResult> {
  const result = await actionFetch<QualityPullSyncResult>(
    `${API_BASE_URL}/api/v1/quality/changes/sync-from-feishu`,
    { method: 'POST' },
  )
  revalidatePath('/quality/change')
  if (!result) throw new Error('未收到变更同步结果')
  return result
}

export async function syncChangeActionPlansFromFeishu() {
  const result = await actionFetch<ChangeActionPlanSyncResult>(
    `${API_BASE_URL}/api/v1/quality/change-action-plans/sync-from-feishu`,
    { method: 'POST' },
  )
  revalidatePath('/quality/change-action-plans')
  return requireActionResult(result, '未收到变更行动计划同步结果')
}

export async function syncChangeActionPlanToFeishu(planId: string) {
  const result = await actionFetch<ChangeActionPlanDetail>(
    `${API_BASE_URL}/api/v1/quality/change-action-plans/${planId}/sync-to-feishu`,
    { method: 'POST' },
  )
  revalidatePath('/quality/change-action-plans')
  return result
}

export async function createChange(data: CreateChangeRequest) {
  const result = await actionFetch<ChangeDetail>(`${API_BASE_URL}/api/v1/quality/changes`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/change')
  return requireActionResult(result, '未收到变更创建结果')
}

export async function updateChange(id: string, data: UpdateChangeRequest) {
  const result = await actionFetch<ChangeDetail>(`${API_BASE_URL}/api/v1/quality/changes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/change')
  revalidatePath(`/quality/change/${id}`)
  return result
}

export async function deleteChange(id: string) {
  const result = await actionFetch<unknown>(`${API_BASE_URL}/api/v1/quality/changes/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/change')
  return result
}

export async function batchDeleteChanges(ids: string[]) {
  const result = await actionFetch<BatchDeleteResult>(`${API_BASE_URL}/api/v1/quality/changes/batch-delete`, {
    method: 'POST',
    body: JSON.stringify({ ids }),
  })
  revalidatePath('/quality/change')
  return requireActionResult(result, '未收到批量删除结果')
}

export async function createChangeActionPlan(data: ChangeActionPlanFormPayload) {
  const result = await actionFetch<ChangeActionPlanDetail>(`${API_BASE_URL}/api/v1/quality/change-action-plans`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/change-action-plans')
  return result
}

export async function updateChangeActionPlan(id: string, data: ChangeActionPlanFormPayload | ChangeActionPlanUpdatePayload) {
  const result = await actionFetch<ChangeActionPlanDetail>(`${API_BASE_URL}/api/v1/quality/change-action-plans/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/quality/change-action-plans')
  return result
}

export async function deleteChangeActionPlan(id: string) {
  const result = await actionFetch<unknown>(`${API_BASE_URL}/api/v1/quality/change-action-plans/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/quality/change-action-plans')
  return result
}

export async function analyzeDeviationAi(id: string) {
  return actionFetch<QualityAiAnalysisLog>(`${API_BASE_URL}/api/v1/quality/ai/deviations/${id}/analyze`, {
    method: 'POST',
  })
}

export async function suggestDeviationCapaAi(id: string) {
  return actionFetch<QualityAiAnalysisLog>(`${API_BASE_URL}/api/v1/quality/ai/deviations/${id}/suggest-capa`, {
    method: 'POST',
  })
}

export async function analyzeCapaAi(id: string) {
  return actionFetch<QualityAiAnalysisLog>(`${API_BASE_URL}/api/v1/quality/ai/capas/${id}/analyze`, {
    method: 'POST',
  })
}

export async function analyzeChangeAi(id: string) {
  return actionFetch<QualityAiAnalysisLog>(`${API_BASE_URL}/api/v1/quality/ai/changes/${id}/analyze`, {
    method: 'POST',
  })
}

export async function applyQualityAiLog(id: string, fieldKeys: string[]) {
  return actionFetch<QualityAiAnalysisLog>(`${API_BASE_URL}/api/v1/quality/ai/logs/${id}/apply`, {
    method: 'POST',
    body: JSON.stringify({ field_keys: fieldKeys }),
  })
}

// ============ Migrated quality module Server Actions ============
const OOS_OOT_PATHS = [
  '/quality',
  '/quality/oos-oot',
  '/quality/oos-oot/report-records',
  '/quality/oos-oot/investigation-push',
  '/quality/oos-oot/oos-ledger',
  '/quality/oos-oot/oot-ledger',
  '/quality/oos-oot/oot-limits',
  '/quality/oos-oot/product-departments',
]
const COMPLAINT_RETURN_PATHS = [
  '/quality',
  '/quality/complaints',
  '/quality/complaints/ledger',
  '/quality/return-recalls',
  '/quality/return-recalls/return-application',
  '/quality/return-recalls/return-ledger',
]

function revalidateQualityPaths(paths: string[]) {
  paths.forEach((path) => revalidatePath(path))
}

async function mutateMigratedQuality<T>(
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  data: Record<string, unknown> | undefined,
  revalidatePaths: string[]
): Promise<T | null> {
  const result = await actionFetch<T>(`${API_BASE_URL}${path}`, {
    method,
    ...(data ? { body: JSON.stringify(data) } : {}),
  })
  revalidateQualityPaths(revalidatePaths)
  return result
}

export async function resolveDocumentEntryContent(names: string[]): Promise<DocumentEntryResolveItem[]> {
  const result = await actionFetch<components['schemas']['DocumentEntryResolveResult']>(
    `${API_BASE_URL}/api/v1/quality/document-entries/resolve-content`,
    { method: 'POST', body: JSON.stringify({ names } satisfies DocumentEntryResolveRequest) }
  )
  return result?.results ?? []
}

export async function pullOosOotReportRecords() {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/report-records/pull', 'POST', undefined, OOS_OOT_PATHS)
}
export async function createOosOotReportRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/report-records', 'POST', data, OOS_OOT_PATHS)
}
export async function updateOosOotReportRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/report-records/${recordId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteOosOotReportRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/report-records/${recordId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}
export async function pullOosOotInvestigationPushRecords() {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/investigation-push-records/pull', 'POST', undefined, OOS_OOT_PATHS)
}
export async function createOosOotInvestigationPushRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/investigation-push-records', 'POST', data, OOS_OOT_PATHS)
}
export async function updateOosOotInvestigationPushRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/investigation-push-records/${recordId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteOosOotInvestigationPushRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/investigation-push-records/${recordId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}

export async function pullOosLedgerRecords() {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/oos-ledger/pull', 'POST', undefined, OOS_OOT_PATHS)
}
export async function createOosLedgerRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/oos-ledger', 'POST', data, OOS_OOT_PATHS)
}
export async function updateOosLedgerRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oos-ledger/${recordId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteOosLedgerRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oos-ledger/${recordId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}
export async function pullOotLedgerRecords() {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/oot-ledger/pull', 'POST', undefined, OOS_OOT_PATHS)
}
export async function createOotLedgerRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/oot-ledger', 'POST', data, OOS_OOT_PATHS)
}
export async function updateOotLedgerRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oot-ledger/${recordId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteOotLedgerRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oot-ledger/${recordId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}
export async function updateOotLimitProduct(productId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oot-limit-products/${productId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteOotLimitProduct(productId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oot-limit-products/${productId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}
export async function updateOotLimitItem(itemId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oot-limit-items/${itemId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteOotLimitItem(itemId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/oot-limit-items/${itemId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}
export async function pullProductDepartmentRecords() {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/product-departments/pull', 'POST', undefined, OOS_OOT_PATHS)
}
export async function createProductDepartmentRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/oos-oot/product-departments', 'POST', data, OOS_OOT_PATHS)
}
export async function updateProductDepartmentRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/product-departments/${recordId}`, 'PUT', data, OOS_OOT_PATHS)
}
export async function deleteProductDepartmentRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/oos-oot/product-departments/${recordId}`, 'DELETE', undefined, OOS_OOT_PATHS)
}

export async function batchDeleteFeishuValidationsAction(recordIds: string[], validationType?: string) {
  let deleted = 0
  for (const recordId of recordIds) {
    try {
      await deleteFeishuValidationAction(recordId, validationType)
      deleted += 1
    } catch {
      // Continue so a single stale Feishu record does not block the batch.
    }
  }
  return { success: true, message: `已删除 ${deleted} 条记录` }
}
export async function pullFeishuValidationsAction(validationType?: string): Promise<FeishuValidationPullResult | null> {
  const result = await pullFeishuValidations(validationType)
  return result as FeishuValidationPullResult | null
}

export async function createComplaintLedgerRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/complaint-ledger', 'POST', data, COMPLAINT_RETURN_PATHS)
}
export async function updateComplaintLedgerRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/complaint-ledger/${recordId}`, 'PUT', data, COMPLAINT_RETURN_PATHS)
}
export async function deleteComplaintLedgerRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/complaint-ledger/${recordId}`, 'DELETE', undefined, COMPLAINT_RETURN_PATHS)
}
export async function pullComplaintLedgerRecords() {
  return mutateMigratedQuality<{ synced: number; failed: number }>('/api/v1/quality/complaint-ledger/pull', 'POST', undefined, COMPLAINT_RETURN_PATHS)
}
export async function createReturnApplicationRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/return-application', 'POST', data, COMPLAINT_RETURN_PATHS)
}
export async function updateReturnApplicationRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/return-application/${recordId}`, 'PUT', data, COMPLAINT_RETURN_PATHS)
}
export async function deleteReturnApplicationRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/return-application/${recordId}`, 'DELETE', undefined, COMPLAINT_RETURN_PATHS)
}
export async function pullReturnApplicationRecords() {
  return mutateMigratedQuality<{ synced: number; failed: number }>('/api/v1/quality/return-application/pull', 'POST', undefined, COMPLAINT_RETURN_PATHS)
}
export async function createReturnLedgerRecord(data: Record<string, unknown>) {
  return mutateMigratedQuality('/api/v1/quality/return-ledger', 'POST', data, COMPLAINT_RETURN_PATHS)
}
export async function updateReturnLedgerRecord(recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/return-ledger/${recordId}`, 'PUT', data, COMPLAINT_RETURN_PATHS)
}
export async function deleteReturnLedgerRecord(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/return-ledger/${recordId}`, 'DELETE', undefined, COMPLAINT_RETURN_PATHS)
}
export async function pullReturnLedgerRecords() {
  return mutateMigratedQuality<{ synced: number; failed: number }>('/api/v1/quality/return-ledger/pull', 'POST', undefined, COMPLAINT_RETURN_PATHS)
}

export async function createProductQualityStandardAction(productCode: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/product-quality-standards/${productCode}`, 'POST', data, ['/quality', '/quality/product-quality'])
}
export async function updateProductQualityStandardAction(productCode: string, recordId: string, data: Record<string, unknown>) {
  return mutateMigratedQuality(`/api/v1/quality/product-quality-standards/${productCode}/${recordId}`, 'PUT', data, ['/quality', '/quality/product-quality'])
}
export async function deleteProductQualityStandardAction(productCode: string, recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/product-quality-standards/${productCode}/${recordId}`, 'DELETE', undefined, ['/quality', '/quality/product-quality'])
}
export async function pullProductQualityStandardsAction(productCode: string) {
  return mutateMigratedQuality<{ synced: number; failed: number }>(`/api/v1/quality/product-quality-standards/${productCode}/pull`, 'POST', undefined, ['/quality', '/quality/product-quality'])
}

const SUPPLIER_PATHS = ['/quality/suppliers', '/quality/suppliers/qualification']
export async function createSupplierQualification(data: CreateSupplierQualificationRequest) {
  return mutateMigratedQuality('/api/v1/quality/supplier-qualification', 'POST', data as Record<string, unknown>, SUPPLIER_PATHS)
}
export async function updateSupplierQualification(recordId: string, data: UpdateSupplierQualificationRequest) {
  return mutateMigratedQuality(`/api/v1/quality/supplier-qualification/${recordId}`, 'PUT', data as Record<string, unknown>, SUPPLIER_PATHS)
}
export async function deleteSupplierQualification(recordId: string) {
  return mutateMigratedQuality(`/api/v1/quality/supplier-qualification/${recordId}`, 'DELETE', undefined, SUPPLIER_PATHS)
}
export async function pullSupplierQualifications() {
  return mutateMigratedQuality<{ synced: number; failed: number }>('/api/v1/quality/supplier-qualification/pull', 'POST', undefined, SUPPLIER_PATHS)
}

const DOCUMENT_PATHS = ['/quality/documents']
export async function createDocumentDepartment(data: CreateDocumentDepartmentRequest) {
  return mutateMigratedQuality<{ id: string }>('/api/v1/quality/document-departments', 'POST', data as Record<string, unknown>, DOCUMENT_PATHS)
}
export async function updateDocumentDepartment(id: string, data: UpdateDocumentDepartmentRequest) {
  return mutateMigratedQuality<{ id: string }>(`/api/v1/quality/document-departments/${id}`, 'PUT', data as Record<string, unknown>, DOCUMENT_PATHS)
}
export async function deleteDocumentDepartment(id: string) {
  return mutateMigratedQuality(`/api/v1/quality/document-departments/${id}`, 'DELETE', undefined, DOCUMENT_PATHS)
}
export async function createDocumentEntry(data: CreateDocumentEntryRequest) {
  return mutateMigratedQuality<{ id: string }>('/api/v1/quality/document-entries', 'POST', data as Record<string, unknown>, DOCUMENT_PATHS)
}
export async function updateDocumentEntry(id: string, data: UpdateDocumentEntryRequest) {
  return mutateMigratedQuality<{ id: string }>(`/api/v1/quality/document-entries/${id}`, 'PUT', data as Record<string, unknown>, DOCUMENT_PATHS)
}
export async function deleteDocumentEntry(id: string) {
  return mutateMigratedQuality(`/api/v1/quality/document-entries/${id}`, 'DELETE', undefined, DOCUMENT_PATHS)
}
export async function importDocumentCatalogExcel(formData: FormData): Promise<DocumentCatalogImportResult | null> {
  const result = await actionFetchForm<DocumentCatalogImportResult>(`${API_BASE_URL}/api/v1/quality/document-catalog/import`, formData)
  revalidateQualityPaths(DOCUMENT_PATHS)
  return result
}
export async function batchImportDocumentAttachments(formData: FormData): Promise<BatchImportDocumentAttachmentsResult | null> {
  const result = await actionFetchForm<BatchImportDocumentAttachmentsResult>(`${API_BASE_URL}/api/v1/quality/document-catalog/attachments/import`, formData)
  revalidateQualityPaths(DOCUMENT_PATHS)
  return result
}
export async function uploadDocumentEntryAttachment(entryId: string, formData: FormData): Promise<UploadDocumentEntryAttachmentResult | null> {
  const result = await actionFetchForm<UploadDocumentEntryAttachmentResult>(`${API_BASE_URL}/api/v1/quality/document-entries/${entryId}/attachments`, formData)
  revalidateQualityPaths(DOCUMENT_PATHS)
  return result
}
export async function autoBindDocumentEntryAttachment(formData: FormData): Promise<UploadDocumentEntryAttachmentResult | null> {
  const result = await actionFetchForm<UploadDocumentEntryAttachmentResult>(`${API_BASE_URL}/api/v1/quality/document-entries/attachments/auto-bind`, formData)
  revalidateQualityPaths(DOCUMENT_PATHS)
  return result
}
export async function deleteDocumentEntryAttachment(entryId: string, storageKey: string) {
  const encodedKey = storageKey.split('/').map(encodeURIComponent).join('/')
  return mutateMigratedQuality(`/api/v1/quality/document-entries/${entryId}/attachments/${encodedKey}`, 'DELETE', undefined, DOCUMENT_PATHS)
}
