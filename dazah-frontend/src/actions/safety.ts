'use server'

import { serverApiUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
// 注意：以下 revalidatePath 调用指向的页面路径部分仍在开发中，待对应页面创建后将自动生效
import { getAuthHeaders, getServerToken } from '@/lib/auth'
import { SAFETY_FEISHU_SETTINGS_PAGE_KEY } from '@/lib/safety-page-tables'
import type {
  Accident,
  AccidentFormData,
  AccidentQueryParams,
  ConfirmCheckRequest,
  Contractor,
  ContractorFormData,
  ContractorQueryParams,
  ContractorWorkRecord,
  ContractorWorkRecordFormData,
  HazardReport,
  HazardReportFormData,
  HazardReportQueryParams,
  HazardStats,
  OperationRegulation,
  OperationRegulationFormData,
  OperationRegulationQueryParams,
  RegulationBatchUploadResponse,
  RegulationDocumentPreview,
  RegulationLatestReviewEntry,
  RegulationReview,
  RegulationRevision,
  RegulationRevisionFormData,
  RegulationRevisionQueryParams,
  SafetyCheck,
  SafetyCheckFormData,
  SafetyCheckQueryParams,
  SafetyKnowledgeArticle,
  SafetyKnowledgeArticleFormData,
  SafetyKnowledgeArticleQueryParams,
  SafetyTraining,
  SafetyTrainingFormData,
  SafetyTrainingQueryParams,
  SpecialOperationPermit,
  SpecialOperationPermitFormData,
  SpecialOperationPermitQueryParams,
  SpecialOperationPersonnel,
  SpecialOperationPersonnelFormData,
  SpecialOperationPersonnelQueryParams,
  SpecialOperationReport,
  SpecialOperationReportFormData,
  SpecialOperationReportQueryParams,
  SpecialOperationLedgerQueryParams,
  SpecialOperationLedgerStats,
  DailyRiskReport,
  DailyRiskReportFormData,
  DailyRiskReportQueryParams,
  HazardRiskOption,
  RectificationReplyRequest,
  VerifyLevelRequest,
  TrainingRecord,
  TrainingRecordFormData,
  ApiResponse,
  ScheduledTask,
  ScheduledTaskLog,
  ScheduledTaskFormData,
  ScheduledTaskQueryParams,
  CardPreviewRequest,
  CardPreviewResponse,
  DataSourceOption,
  FeishuChat,
  OhHazardMonitor,
  OhHazardMonitorFormData,
  OhHazardMonitorQueryParams,
  OhHealthExam,
  OhHealthExamFormData,
  OhHealthExamQueryParams,
  OhDetectionReport,
  OhDetectionImportResult,
  OhDetectionParsePreview,
  OhDetectionResult,
  OhDetectionResultQueryParams,
} from '@/types/safety'
import type { components } from '@/types/generated/schema'

type SafetyFeishuAppSettingsDetail = components['schemas']['SafetyFeishuAppSettingsDetail']
type SafetyFeishuSettingsTestResult = components['schemas']['SafetyFeishuSettingsTestResult']
type UpdateSafetyFeishuAppSettingsRequest = components['schemas']['UpdateSafetyFeishuAppSettingsRequest']
type PageTableRecordsResponse = components['schemas']['PageTableRecordsResponse']
type PageTableStatsResponse = components['schemas']['PageTableStatsResponse']
type PageTableTabListResponse = components['schemas']['PageTableTabListResponse']
type PageTableFieldValuesResponse =
  components['schemas']['PageTableFieldValuesResponse']
type PageTableRecord = components['schemas']['PageTableRecord']
type PageTableAttachmentUploadResponse = components['schemas']['PageTableAttachmentUploadResponse']
type PageFeishuConfigItem = components['schemas']['PageFeishuConfigItem']
type PageFeishuConfigListResponse = components['schemas']['PageFeishuConfigListResponse']
type PageFeishuConfigTestResult = components['schemas']['PageFeishuConfigTestResult']
type ResolvedPageFeishuUrl = components['schemas']['ResolvedPageFeishuUrl']
type UpdatePageFeishuConfigRequest = components['schemas']['UpdatePageFeishuConfigRequest']

const API_BASE = serverApiUrl('')

// ============ Helper Functions ============

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  let response: Response
  try {
    const authHeaders = await getAuthHeaders()
    const { headers: optHeaders, ...restOptions } = options || {}
    response = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        ...authHeaders,
        ...optHeaders,
      },
      ...restOptions,
    })
  } catch {
    return {
      code: -1,
      message: `网络请求失败，无法连接到后端服务 (${API_BASE}${endpoint})`,
    } as ApiResponse<T>
  }

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorBody = await response.text()
      try {
        const errorJson = JSON.parse(errorBody)
        if (errorJson.message) {
          errorMessage = errorJson.message
        } else if (errorJson.detail) {
          errorMessage = errorJson.detail
        }
      } catch {
        errorMessage = errorBody.substring(0, 200)
      }
    } catch {
      // 无法读取响应体
    }
    return { code: response.status, message: errorMessage } as ApiResponse<T>
  }

  try {
    return await response.json()
  } catch {
    const text = await response.text().catch(() => '无法读取响应')
    return {
      code: -1,
      message: `响应解析失败: ${text.substring(0, 200)}`,
    } as ApiResponse<T>
  }
}

// ============ SafetyCheck Actions ============

export async function getChecks(params: SafetyCheckQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.check_type) searchParams.set('check_type', params.check_type)
  if (params.department) searchParams.set('department', params.department)

  const queryString = searchParams.toString()
  const endpoint = `/safety/checks${queryString ? `?${queryString}` : ''}`
  return fetchApi<SafetyCheck[]>(endpoint)
}

export async function getCheck(id: string) {
  return fetchApi<SafetyCheck>(`/safety/checks/${id}`)
}

export async function createCheck(data: SafetyCheckFormData) {
  const response = await fetchApi<SafetyCheck>('/safety/checks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/check')
  return response
}

export async function updateCheck(id: string, data: Partial<SafetyCheckFormData>) {
  const response = await fetchApi<SafetyCheck>(`/safety/checks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/check')
  return response
}

export async function submitCheck(id: string) {
  const response = await fetchApi<SafetyCheck>(`/safety/checks/${id}/submit`, {
    method: 'POST',
  })
  revalidatePath('/safety/check')
  return response
}

export async function reviewCheck(id: string, result: string) {
  const response = await fetchApi<SafetyCheck>(
    `/safety/checks/${id}/review?result=${result}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/check')
  return response
}

export async function deleteCheck(id: string) {
  const response = await fetchApi<null>(`/safety/checks/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/check')
  return response
}

// ============ HazardReport Actions ============

export async function fetchHazardStats(): Promise<ApiResponse<HazardStats>> {
  const response = await fetchApi<HazardStats>('/safety/hazards/stats')
  return response
}

export async function getHazards(params: HazardReportQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.rectification_status) searchParams.set('rectification_status', params.rectification_status)
  if (params.overall_status) searchParams.set('overall_status', params.overall_status)
  if (params.hazard_type) searchParams.set('hazard_type', params.hazard_type)
  if (params.hazard_level) searchParams.set('hazard_level', params.hazard_level)
  if (params.hazard_category) searchParams.set('hazard_category', params.hazard_category)
  if (params.inspection_category) searchParams.set('inspection_category', params.inspection_category)
  if (params.department) searchParams.set('department', params.department)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/hazards${queryString ? `?${queryString}` : ''}`
  return fetchApi<HazardReport[]>(endpoint)
}

export async function getHazard(id: string) {
  return fetchApi<HazardReport>(`/safety/hazards/${id}`)
}

/** 根据部门名称查询部门负责人 */
export async function getDepartmentLeader(departmentName: string) {
  return fetchApi<{ department: string; leader_name: string | null; leader_id: string | null }>(
    `/safety/hazards/department-leader?department_name=${encodeURIComponent(departmentName)}`
  )
}

export async function createHazard(data: HazardReportFormData) {
  const response = await fetchApi<HazardReport>('/safety/hazards', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/hazard')
  return response
}

export async function updateHazard(id: string, data: Partial<HazardReportFormData>) {
  const response = await fetchApi<HazardReport>(`/safety/hazards/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/hazard')
  return response
}

export async function startRectification(id: string) {
  const response = await fetchApi<HazardReport>(
    `/safety/hazards/${id}/rectification/start`,
    { method: 'POST' }
  )
  revalidatePath('/safety/hazard')
  return response
}

export async function confirmCheck(id: string, data: ConfirmCheckRequest) {
  const response = await fetchApi<SafetyCheck>(
    `/safety/checks/${id}/confirm`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety')
  return response
}

export async function replyRectification(id: string, data: RectificationReplyRequest) {
  const response = await fetchApi<HazardReport>(
    `/safety/hazards/${id}/rectification/reply`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazard')
  return response
}

export async function verifyLevel(id: string, data: VerifyLevelRequest) {
  const response = await fetchApi<HazardReport>(
    `/safety/hazards/${id}/rectification/verify-level`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazard')
  return response
}

export async function reworkRectification(id: string, data: RectificationReplyRequest) {
  const response = await fetchApi<HazardReport>(
    `/safety/hazards/${id}/rectification/rework`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazard')
  return response
}

export async function deleteHazard(id: string) {
  const response = await fetchApi<null>(`/safety/hazards/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/hazard')
  return response
}

export async function deleteHazards(ids: string[]) {
  const results = await Promise.allSettled(
    ids.map((id) =>
      fetchApi<null>(`/safety/hazards/${id}`, { method: 'DELETE' })
    )
  )
  revalidatePath('/safety/hazard')
  const succeeded = results.filter((r) => r.status === 'fulfilled').length
  const failed = results.filter((r) => r.status === 'rejected').length
  return { succeeded, failed, total: ids.length }
}

export async function uploadHazardPhoto(id: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/hazards/${id}/upload-photo`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  revalidatePath('/safety/hazard')
  return response.json()
}

export async function uploadRectificationPhoto(id: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/hazards/${id}/upload-rectification-photo`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  revalidatePath('/safety/hazard')
  return response.json()
}

export async function runHazardAI(hazardId: string, scriptNumber: number) {
  const response = await fetchApi<HazardReport>(
    `/safety/hazards/${hazardId}/ai/run/${scriptNumber}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/hazard')
  return response
}

// ============ Accident Actions ============

export async function getAccidents(params: AccidentQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.accident_type) searchParams.set('accident_type', params.accident_type)
  if (params.accident_level) searchParams.set('accident_level', params.accident_level)
  if (params.department) searchParams.set('department', params.department)
  if (params.date_from) searchParams.set('date_from', params.date_from)
  if (params.date_to) searchParams.set('date_to', params.date_to)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/accidents${queryString ? `?${queryString}` : ''}`
  return fetchApi<Accident[]>(endpoint)
}

export async function getAccident(id: string) {
  return fetchApi<Accident>(`/safety/accidents/${id}`)
}

export async function createAccident(data: AccidentFormData) {
  const response = await fetchApi<Accident>('/safety/accidents', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/accident')
  return response
}

export async function updateAccident(id: string, data: Partial<AccidentFormData>) {
  const response = await fetchApi<Accident>(`/safety/accidents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/accident')
  return response
}

export async function investigateAccident(id: string) {
  const response = await fetchApi<Accident>(
    `/safety/accidents/${id}/investigate`,
    { method: 'POST' }
  )
  revalidatePath('/safety/accident')
  return response
}

export async function resolveAccident(
  id: string,
  directCause: string,
  rootCause: string,
  handlingMeasures: string,
  correctiveActions?: string,
  investigationFindings?: string,
  investigationMethod?: string
) {
  const params = new URLSearchParams({ direct_cause: directCause, root_cause: rootCause, handling_measures: handlingMeasures })
  if (correctiveActions) params.set('corrective_actions', correctiveActions)
  if (investigationFindings) params.set('investigation_findings', investigationFindings)
  if (investigationMethod) params.set('investigation_method', investigationMethod)

  const response = await fetchApi<Accident>(
    `/safety/accidents/${id}/resolve?${params.toString()}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/accident')
  return response
}

export async function startCapa(
  id: string,
  deadline: string,
  responsible: string
) {
  const params = new URLSearchParams({ corrective_action_deadline: deadline, corrective_action_responsible: responsible })
  const response = await fetchApi<Accident>(
    `/safety/accidents/${id}/start-capa?${params.toString()}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/accident')
  return response
}

export async function verifyCapa(id: string) {
  const response = await fetchApi<Accident>(
    `/safety/accidents/${id}/verify-capa`,
    { method: 'POST' }
  )
  revalidatePath('/safety/accident')
  return response
}

export async function closeAccident(id: string) {
  const response = await fetchApi<Accident>(
    `/safety/accidents/${id}/close`,
    { method: 'POST' }
  )
  revalidatePath('/safety/accident')
  return response
}

export async function deleteAccident(id: string) {
  const response = await fetchApi<null>(`/safety/accidents/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/accident')
  return response
}

// ============ Contractor Actions ============

export async function getContractors(params: ContractorQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.qualification_type) searchParams.set('qualification_type', params.qualification_type)
  if (params.training_status) searchParams.set('training_status', params.training_status)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/contractors${queryString ? `?${queryString}` : ''}`
  return fetchApi<Contractor[]>(endpoint)
}

export async function getContractor(id: string) {
  return fetchApi<Contractor>(`/safety/contractors/${id}`)
}

export async function createContractor(data: ContractorFormData) {
  const response = await fetchApi<Contractor>('/safety/contractors', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/contractor')
  return response
}

export async function updateContractor(id: string, data: Partial<ContractorFormData>) {
  const response = await fetchApi<Contractor>(`/safety/contractors/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/contractor')
  return response
}

export async function deleteContractor(id: string) {
  const response = await fetchApi<null>(`/safety/contractors/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/contractor')
  return response
}

export async function blacklistContractor(id: string) {
  const response = await fetchApi<Contractor>(`/safety/contractors/${id}/blacklist`, { method: 'POST' })
  revalidatePath('/safety/contractor')
  return response
}

export async function activateContractor(id: string) {
  const response = await fetchApi<Contractor>(`/safety/contractors/${id}/activate`, { method: 'POST' })
  revalidatePath('/safety/contractor')
  return response
}

export async function updateContractorTraining(id: string, trainingStatus: string) {
  const params = new URLSearchParams({ training_status: trainingStatus })
  const response = await fetchApi<Contractor>(
    `/safety/contractors/${id}/update-training?${params.toString()}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/contractor')
  return response
}

export async function getWorkRecords(contractorId: string) {
  return fetchApi<ContractorWorkRecord[]>(`/safety/contractors/${contractorId}/work-records`)
}

export async function createWorkRecord(contractorId: string, data: ContractorWorkRecordFormData) {
  const response = await fetchApi<ContractorWorkRecord>(
    `/safety/contractors/${contractorId}/work-records`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/contractor')
  return response
}

export async function updateWorkRecord(
  contractorId: string, recordId: string, data: Partial<ContractorWorkRecordFormData>
) {
  const response = await fetchApi<ContractorWorkRecord>(
    `/safety/contractors/${contractorId}/work-records/${recordId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/contractor')
  return response
}

export async function deleteWorkRecord(contractorId: string, recordId: string) {
  const response = await fetchApi<null>(
    `/safety/contractors/${contractorId}/work-records/${recordId}`,
    { method: 'DELETE' }
  )
  revalidatePath('/safety/contractor')
  return response
}

export async function evaluateWorkRecord(
  contractorId: string, recordId: string, score: number, comments?: string, evaluator?: string
) {
  const response = await fetchApi<ContractorWorkRecord>(
    `/safety/contractors/${contractorId}/work-records/${recordId}/evaluate`,
    { method: 'POST', body: JSON.stringify({ score, comments, evaluator }) }
  )
  revalidatePath('/safety/contractor')
  return response
}

// ============ SafetyTraining Actions ============

export async function getTrainings(params: SafetyTrainingQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.training_type) searchParams.set('training_type', params.training_type)
  if (params.department) searchParams.set('department', params.department)

  const queryString = searchParams.toString()
  const endpoint = `/safety/trainings${queryString ? `?${queryString}` : ''}`
  return fetchApi<SafetyTraining[]>(endpoint)
}

export async function getTraining(id: string) {
  return fetchApi<SafetyTraining>(`/safety/trainings/${id}`)
}

export async function createTraining(data: SafetyTrainingFormData) {
  const response = await fetchApi<SafetyTraining>('/safety/trainings', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/training')
  return response
}

export async function updateTraining(id: string, data: Partial<SafetyTrainingFormData>) {
  const response = await fetchApi<SafetyTraining>(`/safety/trainings/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/training')
  return response
}

export async function startTraining(id: string) {
  const response = await fetchApi<SafetyTraining>(
    `/safety/trainings/${id}/start`,
    { method: 'POST' }
  )
  revalidatePath('/safety/training')
  return response
}

export async function completeTraining(id: string) {
  const response = await fetchApi<SafetyTraining>(
    `/safety/trainings/${id}/complete`,
    { method: 'POST' }
  )
  revalidatePath('/safety/training')
  return response
}

export async function deleteTraining(id: string) {
  const response = await fetchApi<null>(`/safety/trainings/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/training')
  return response
}

// ============ TrainingRecord Actions ============

export async function getTrainingRecords(trainingId: string) {
  return fetchApi<TrainingRecord[]>(`/safety/trainings/${trainingId}/records`)
}

export async function createTrainingRecord(trainingId: string, data: TrainingRecordFormData) {
  const response = await fetchApi<TrainingRecord>(
    `/safety/trainings/${trainingId}/records`,
    {
      method: 'POST',
      body: JSON.stringify({ ...data, training_id: trainingId }),
    }
  )
  revalidatePath(`/safety/training`)
  return response
}

export async function updateTrainingRecord(recordId: string, data: Partial<TrainingRecordFormData>) {
  const response = await fetchApi<TrainingRecord>(
    `/safety/training-records/${recordId}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/safety/training')
  return response
}

export async function deleteTrainingRecord(recordId: string) {
  const response = await fetchApi<null>(
    `/safety/training-records/${recordId}`,
    { method: 'DELETE' }
  )
  revalidatePath('/safety/training')
  return response
}

// ============ Training Certificate Actions ============

export async function getTrainingCertificates(
  params: { page?: number; page_size?: number; certificate_status?: string; keyword?: string } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.certificate_status) searchParams.set('certificate_status', params.certificate_status)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  const qs = searchParams.toString()
  const endpoint = `/safety/training-certificates${qs ? `?${qs}` : ''}`
  return fetchApi<TrainingRecord[]>(endpoint)
}

export async function getExpiringCertificates() {
  return fetchApi<TrainingRecord[]>('/safety/training-certificates/expiring')
}

// ============ HazardIdentification Actions ============

export async function getHazardIdentifications(
  params: import('@/types/safety').HazardIdentificationQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.department) searchParams.set('department', params.department)
  if (params.overall_status) searchParams.set('overall_status', params.overall_status)
  if (params.ai_node_progress) searchParams.set('ai_node_progress', params.ai_node_progress)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  if (params.position) searchParams.set('position', params.position)
  if (params.risk_level) searchParams.set('risk_level', params.risk_level)
  if (params.date_from) searchParams.set('date_from', params.date_from)
  if (params.date_to) searchParams.set('date_to', params.date_to)

  const queryString = searchParams.toString()
  const endpoint = `/safety/hazard-identifications${queryString ? `?${queryString}` : ''}`
  return fetchApi<import('@/types/safety').HazardIdentification[]>(endpoint)
}

export async function getHIStats() {
  return fetchApi<import('@/types/safety').HazardIdentificationStats>(
    '/safety/hazard-identifications/stats'
  )
}

export async function getHILedgerStats(
  params: {
    department?: string
    position?: string
    risk_level?: string
    date_from?: string
    date_to?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.department) searchParams.set('department', params.department)
  if (params.position) searchParams.set('position', params.position)
  if (params.risk_level) searchParams.set('risk_level', params.risk_level)
  if (params.date_from) searchParams.set('date_from', params.date_from)
  if (params.date_to) searchParams.set('date_to', params.date_to)
  const qs = searchParams.toString()
  return fetchApi<import('@/types/safety').HazardLedgerStats>(
    `/safety/hazard-identifications/ledger-stats${qs ? `?${qs}` : ''}`
  )
}

export async function getHazardIdentification(id: string) {
  return fetchApi<import('@/types/safety').HazardIdentification>(
    `/safety/hazard-identifications/${id}`
  )
}

export async function createHazardIdentification(
  data: import('@/types/safety').HazardIdentificationFormData
) {
  const response = await fetchApi<import('@/types/safety').HazardIdentification>(
    '/safety/hazard-identifications',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazard-identification')
  return response
}

export async function updateHazardIdentification(
  id: string,
  data: Partial<import('@/types/safety').HazardIdentification>
) {
  const response = await fetchApi<import('@/types/safety').HazardIdentification>(
    `/safety/hazard-identifications/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazard-identification')
  return response
}

export async function submitHazardIdentification(id: string) {
  const response = await fetchApi<import('@/types/safety').HazardIdentification>(
    `/safety/hazard-identifications/${id}/submit`,
    { method: 'POST' }
  )
  revalidatePath('/safety/hazard-identification')
  return response
}

export async function runHazardScript(
  id: string,
  scriptNumber: number,
  aiOutput?: Record<string, unknown>
) {
  const body: Record<string, unknown> = { script_number: scriptNumber }
  if (aiOutput) {
    body.ai_output = aiOutput
  }
  const response = await fetchApi<import('@/types/safety').HazardIdentification>(
    `/safety/hazard-identifications/${id}/run-script`,
    { method: 'POST', body: JSON.stringify(body) }
  )
  revalidatePath('/safety/hazard-identification')
  return response
}

export async function reviewHazardScript(
  id: string,
  scriptNumber: number,
  action: 'approved' | 'rejected'
) {
  const response = await fetchApi<import('@/types/safety').HazardIdentification>(
    `/safety/hazard-identifications/${id}/review`,
    {
      method: 'POST',
      body: JSON.stringify({ script_number: scriptNumber, action }),
    }
  )
  revalidatePath('/safety/hazard-identification')
  return response
}

export async function uploadHazardAttachment(id: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/hazard-identifications/${id}/upload`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  revalidatePath('/safety/hazard-identification')
  return response.json()
}

export async function deleteHazardIdentification(id: string) {
  const response = await fetchApi<null>(
    `/safety/hazard-identifications/${id}`,
    { method: 'DELETE' }
  )
  revalidatePath('/safety/hazard-identification')
  return response
}

// ============ Hazard Identification AI Export ============

export async function parseHazardExportQuery(naturalQuery: string) {
  return fetchApi<import('@/types/safety').HazardLedgerExportParsedFilters>(
    '/safety/hazard-identifications/parse-query',
    {
      method: 'POST',
      body: JSON.stringify({ natural_query: naturalQuery }),
    }
  )
}

export async function exportHazardLedgerPdf(
  params: import('@/types/safety').HazardLedgerExportRequest
): Promise<ApiResponse<string>> {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(`${API_BASE}/safety/hazard-identifications/export-pdf`, {
    method: 'POST',
    headers: { ...authHeaders },
    body: JSON.stringify(params),
  })

  if (!response.ok) {
    const errorText = await response.text()
    return { code: response.status, message: `导出失败: ${errorText}`, data: '' } as ApiResponse<string>
  }

  // 在 Server Action 中不能使用 browser API，返回 base64 给客户端处理下载
  const arrayBuffer = await response.arrayBuffer()
  const base64 = Buffer.from(arrayBuffer).toString('base64')
  return { code: 0, message: 'ok', data: base64 }
}

// ── 危险源辨识台账 Excel 导入 ──

export async function getHazardFilterOptions(): Promise<
  ApiResponse<import('@/types/safety').HazardFilterOptions>
> {
  return fetchApi<import('@/types/safety').HazardFilterOptions>(
    '/safety/hazard-identifications/filter-options'
  )
}

export async function parseHazardLedgerImport(
  file: File
): Promise<ApiResponse<import('@/types/safety').HazardImportPreview>> {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/hazard-identifications/import/parse`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  return response.json()
}

export async function importHazardLedger(
  file: File,
  department: string,
  sheets: string[]
): Promise<ApiResponse<import('@/types/safety').HazardImportResult>> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('department', department)
  formData.append('sheets', JSON.stringify(sheets))
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(`${API_BASE}/safety/hazard-identifications/import`, {
    method: 'POST',
    headers: uploadHeaders,
    body: formData,
  })
  revalidatePath('/safety/hazard-identification/ledger')
  return response.json()
}

export async function getSafetyEnums() {
  return fetchApi<Record<string, Array<{ value: string; label: string }>>>('/safety/enums')
}

// ============ OperationRegulation Actions ============

export async function getRegulations(params: OperationRegulationQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.position) searchParams.set('position', params.position)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/regulations${queryString ? `?${queryString}` : ''}`
  return fetchApi<OperationRegulation[]>(endpoint)
}

export async function getRegulation(id: string) {
  return fetchApi<OperationRegulation>(`/safety/regulations/${id}`)
}

export async function createRegulation(data: OperationRegulationFormData) {
  const response = await fetchApi<OperationRegulation>('/safety/regulations', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/regulation')
  return response
}

export async function updateRegulation(id: string, data: Partial<OperationRegulationFormData>) {
  const response = await fetchApi<OperationRegulation>(`/safety/regulations/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/regulation')
  return response
}

export async function deleteRegulation(id: string) {
  const response = await fetchApi<null>(`/safety/regulations/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/regulation')
  return response
}

export async function uploadRegulationDocument(id: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/regulations/${id}/upload`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`上传失败: ${response.status} ${text}`)
  }
  revalidatePath('/safety/regulation')
  return response.json()
}

// ============ SOP Generator Actions ============

export async function generateSop(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/regulations/generate`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`生成失败 (${response.status}): ${text}`)
  }
  revalidatePath('/safety/regulation')
  return response.json()
}

export async function updateSopContent(regulationId: string, content: string, status?: string) {
  const response = await fetchApi<OperationRegulation>(
    `/safety/regulations/${regulationId}/content`,
    { method: 'PUT', body: JSON.stringify({ content, status }) }
  )
  revalidatePath('/safety/regulation')
  return response
}

export async function exportSopPdf(regulationId: string): Promise<ApiResponse<Blob>> {
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...headers } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/regulations/${regulationId}/export`,
    { method: 'POST', headers }
  )
  if (!response.ok) {
    const text = await response.text()
    return { code: response.status, message: `导出 PDF 失败: ${text}` } as ApiResponse<Blob>
  }
  const blob = await response.blob()
  return { code: 0, message: 'ok', data: blob }
}

// ============ Regulation Batch Upload & Compliance Review Actions ============

export async function batchUploadRegulations(
  files: File[],
  options: { hintWorkshop?: string; useAi?: boolean } = {}
): Promise<ApiResponse<RegulationBatchUploadResponse>> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  if (options.hintWorkshop) formData.append('hint_workshop', options.hintWorkshop)
  formData.append('use_ai', String(options.useAi !== false))
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/regulations/batch-upload`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  if (!response.ok) {
    const text = await response.text()
    return { code: response.status, message: `批量导入失败: ${text}` } as ApiResponse<RegulationBatchUploadResponse>
  }
  revalidatePath('/safety/regulation')
  return response.json()
}

export async function runComplianceReview(
  regulationId: string
): Promise<ApiResponse<RegulationReview>> {
  const response = await fetchApi<RegulationReview>(
    `/safety/regulations/${regulationId}/compliance-review`,
    { method: 'POST' }
  )
  revalidatePath('/safety/regulation')
  return response
}

export async function getRegulationReviews(
  regulationId: string
): Promise<ApiResponse<{ items: RegulationReview[]; total: number }>> {
  return fetchApi(`/safety/regulations/${regulationId}/reviews`)
}

export async function getLatestRegulationReviews(
  regulationIds: string[]
): Promise<ApiResponse<RegulationLatestReviewEntry[]>> {
  const query = new URLSearchParams({ regulation_ids: regulationIds.join(',') })
  return fetchApi(`/safety/regulation-reviews/latest?${query.toString()}`)
}

export async function getRegulationDocumentPreview(
  regulationId: string
): Promise<ApiResponse<RegulationDocumentPreview>> {
  return fetchApi(`/safety/regulations/${regulationId}/document-content`)
}

export async function downloadRegulationDocument(
  regulationId: string,
  fileName?: string
): Promise<void> {
  const headers = await getAuthHeaders()
  const response = await fetch(
    `${API_BASE}/safety/regulations/${regulationId}/document`,
    { headers }
  )
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`下载失败 (${response.status}): ${text}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName || '操规文档'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ============ RegulationRevision Actions ============

export async function getRevisions(params: RegulationRevisionQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.regulation_id) searchParams.set('regulation_id', params.regulation_id)
  if (params.revision_type) searchParams.set('revision_type', params.revision_type)
  if (params.review_opinion) searchParams.set('review_opinion', params.review_opinion)
  if (params.revision_scope) searchParams.set('revision_scope', params.revision_scope)

  const queryString = searchParams.toString()
  const endpoint = `/safety/revisions${queryString ? `?${queryString}` : ''}`
  return fetchApi<RegulationRevision[]>(endpoint)
}

export async function getRevision(id: string) {
  return fetchApi<RegulationRevision>(`/safety/revisions/${id}`)
}

export async function createRevision(data: RegulationRevisionFormData) {
  const response = await fetchApi<RegulationRevision>('/safety/revisions', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/regulation-revision')
  return response
}

export async function updateRevision(id: string, data: Partial<RegulationRevision>) {
  const response = await fetchApi<RegulationRevision>(`/safety/revisions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/regulation-revision')
  return response
}

export async function deleteRevision(id: string) {
  const response = await fetchApi<null>(`/safety/revisions/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/regulation-revision')
  return response
}

export async function manualRevisionComplete(revisionId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/revisions/${revisionId}/manual-complete`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  revalidatePath('/safety/regulation-revision')
  return response.json()
}

export async function aiRevisionGenerate(revisionId: string) {
  const response = await fetchApi<{ generated_content: string }>(
    `/safety/revisions/${revisionId}/ai-generate`,
    { method: 'POST' }
  )
  return response
}

export async function aiRevisionConfirm(
  revisionId: string,
  generatedContent: string,
  documentName?: string
) {
  const params = new URLSearchParams({ generated_content: generatedContent })
  if (documentName) params.set('document_name', documentName)

  const response = await fetchApi<RegulationRevision>(
    `/safety/revisions/${revisionId}/ai-confirm?${params.toString()}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/regulation-revision')
  return response
}

export async function identifyRevisionScope(revisionId: string) {
  const response = await fetchApi<RegulationRevision>(
    `/safety/revisions/${revisionId}/identify-scope`,
    { method: 'POST' }
  )
  revalidatePath('/safety/regulation-revision')
  return response
}

// ============ AI Workflow Config Actions ============

export async function getAIWorkflowConfigs(
  params: import('@/types/safety').AIWorkflowConfigQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.module_code) searchParams.set('module_code', params.module_code)
  if (params.is_enabled !== undefined) searchParams.set('is_enabled', String(params.is_enabled))

  const queryString = searchParams.toString()
  const endpoint = `/safety/ai-workflow-configs${queryString ? `?${queryString}` : ''}`
  return fetchApi<import('@/types/safety').AIWorkflowConfig[]>(endpoint)
}

export async function getAIWorkflowConfig(id: string) {
  return fetchApi<import('@/types/safety').AIWorkflowConfig>(
    `/safety/ai-workflow-configs/${id}`
  )
}

export async function createAIWorkflowConfig(
  data: import('@/types/safety').AIWorkflowConfigFormData
) {
  const response = await fetchApi<import('@/types/safety').AIWorkflowConfig>(
    '/safety/ai-workflow-configs',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/ai-workflow-config')
  return response
}

export async function updateAIWorkflowConfig(
  id: string,
  data: Partial<import('@/types/safety').AIWorkflowConfig>
) {
  const response = await fetchApi<import('@/types/safety').AIWorkflowConfig>(
    `/safety/ai-workflow-configs/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/ai-workflow-config')
  return response
}

export async function deleteAIWorkflowConfig(id: string) {
  const response = await fetchApi<null>(`/safety/ai-workflow-configs/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/ai-workflow-config')
  return response
}

// ============ AI Workflow Attachment Actions ============

export async function uploadWorkflowAttachment(
  file: File
): Promise<ApiResponse<import('@/types/safety').ReferenceAttachment>> {
  const formData = new FormData()
  formData.append('file', file)

  // 只传 Authorization，不能手动设置 Content-Type —— 浏览器需自动设置
  // multipart/form-data 的 boundary，否则后端无法解析 FormData
  const token = await getServerToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE}/safety/ai-workflow-configs/attachments/upload`, {
    method: 'POST',
    headers,
    body: formData,
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorBody = await response.json()
      if (errorBody.message) errorMessage = errorBody.message
    } catch { /* ignore */ }
    return { code: response.status, message: errorMessage } as ApiResponse<import('@/types/safety').ReferenceAttachment>
  }

  return response.json()
}

export async function deleteWorkflowAttachment(
  attachmentId: string
): Promise<ApiResponse<null>> {
  return fetchApi<null>(`/safety/ai-workflow-configs/attachments/${attachmentId}`, {
    method: 'DELETE',
  })
}

export async function createKnowledgeAttachments(
  knowledgeIds: string[]
): Promise<ApiResponse<import('@/types/safety').ReferenceAttachment[]>> {
  return fetchApi<import('@/types/safety').ReferenceAttachment[]>(
    '/safety/ai-workflow-configs/attachments/from-knowledge',
    { method: 'POST', body: JSON.stringify({ knowledge_ids: knowledgeIds }) }
  )
}

// ============ SpecialOperationPersonnel Actions ============

export async function getPersonnelList(params: SpecialOperationPersonnelQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.certificate_type) searchParams.set('certificate_type', params.certificate_type)
  if (params.department) searchParams.set('department', params.department)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/special-operation-personnel${queryString ? `?${queryString}` : ''}`
  return fetchApi<SpecialOperationPersonnel[]>(endpoint)
}

export async function getPersonnel(id: string) {
  return fetchApi<SpecialOperationPersonnel>(`/safety/special-operation-personnel/${id}`)
}

export async function createPersonnel(data: SpecialOperationPersonnelFormData) {
  const response = await fetchApi<SpecialOperationPersonnel>(
    '/safety/special-operation-personnel',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/special-ops-personnel')
  return response
}

export async function updatePersonnel(id: string, data: Partial<SpecialOperationPersonnelFormData>) {
  const response = await fetchApi<SpecialOperationPersonnel>(
    `/safety/special-operation-personnel/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/special-ops-personnel')
  return response
}

export async function deletePersonnel(id: string) {
  const response = await fetchApi<null>(`/safety/special-operation-personnel/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/special-ops-personnel')
  return response
}

// ============ SpecialOperationPermit Actions ============

export async function getPermitList(params: SpecialOperationPermitQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.operation_type) searchParams.set('operation_type', params.operation_type)
  if (params.operation_level) searchParams.set('operation_level', params.operation_level)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/special-operation-permits${queryString ? `?${queryString}` : ''}`
  return fetchApi<SpecialOperationPermit[]>(endpoint)
}

export async function getPermit(id: string) {
  return fetchApi<SpecialOperationPermit>(`/safety/special-operation-permits/${id}`)
}

export async function createPermit(data: SpecialOperationPermitFormData) {
  const response = await fetchApi<SpecialOperationPermit>(
    '/safety/special-operation-permits',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function updatePermit(id: string, data: Partial<SpecialOperationPermitFormData>) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function deletePermit(id: string) {
  const response = await fetchApi<null>(`/safety/special-operation-permits/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function submitPermit(id: string) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}/submit`,
    { method: 'POST' }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function approvePermit(id: string) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}/approve`,
    { method: 'POST' }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function rejectPermit(id: string, reason: string) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}/reject?reason=${encodeURIComponent(reason)}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function startPermit(id: string) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}/start`,
    { method: 'POST' }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function completePermit(id: string, method: string) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}/complete?method=${encodeURIComponent(method)}`,
    { method: 'POST' }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

export async function archivePermit(id: string) {
  const response = await fetchApi<SpecialOperationPermit>(
    `/safety/special-operation-permits/${id}/archive`,
    { method: 'POST' }
  )
  revalidatePath('/safety/special-ops-permits')
  return response
}

// ============ Safety Knowledge Article Actions ============

export async function getKnowledgeArticles(params: SafetyKnowledgeArticleQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.regulation_status) searchParams.set('regulation_status', params.regulation_status)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  const queryString = searchParams.toString()
  const endpoint = `/safety/knowledge-articles${queryString ? '?' + queryString : ''}`
  return fetchApi<SafetyKnowledgeArticle[]>(endpoint)
}

export async function getKnowledgeArticle(id: string) {
  return fetchApi<SafetyKnowledgeArticle>(`/safety/knowledge-articles/${id}`)
}

export async function createKnowledgeArticle(data: SafetyKnowledgeArticleFormData) {
  const response = await fetchApi<SafetyKnowledgeArticle>('/safety/knowledge-articles', {
    method: 'POST', body: JSON.stringify(data),
  })
  revalidatePath('/safety/knowledge-base')
  return response
}

export async function updateKnowledgeArticle(id: string, data: Partial<SafetyKnowledgeArticleFormData>) {
  const response = await fetchApi<SafetyKnowledgeArticle>(`/safety/knowledge-articles/${id}`, {
    method: 'PUT', body: JSON.stringify(data),
  })
  revalidatePath('/safety/knowledge-base')
  return response
}

export async function deleteKnowledgeArticle(id: string) {
  const response = await fetchApi<null>(`/safety/knowledge-articles/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/knowledge-base')
  return response
}


export async function uploadKnowledgeAttachments(id: string, files: File[]) {
  if (!files.length) return { code: 200, data: null }
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/knowledge-articles/${id}/attachments`,
    {
      method: 'POST',
      headers: { ...uploadHeaders, 'X-Dazah-Page-Key': 'safety:regulation-info:knowledge-base' },
      body: formData,
    }
  )
  return response.json()
}

export async function deleteKnowledgeAttachment(id: string, token: string) {
  const res = await fetchApi<SafetyKnowledgeArticle>(
    `/safety/knowledge-articles/${id}/attachments/${token}`,
    {
      method: 'DELETE',
      headers: { 'X-Dazah-Page-Key': 'safety:regulation-info:knowledge-base' },
    }
  )
  return res
}

const RADAR_PAGE_KEY = 'safety:regulation-info:knowledge-base'

export async function getRadarRuns(limit = 10) {
  const res = await fetchApi<Record<string, unknown>[]>(
    `/safety/knowledge-articles/radar/runs?limit=${limit}`,
    { headers: { 'X-Dazah-Page-Key': RADAR_PAGE_KEY } },
  )
  return res
}

export interface RadarRunDetail {
  id: string
  status: string
  started_at: string
  items?: {
    action: string
    name: string
    date?: string
    old_date?: string
    new_date?: string
    url?: string
    site?: string
    reason?: string
    new_standard_no?: string
  }[] | null
  error_message?: string | null
}

export async function testRadarNotify() {
  const res = await fetchApi<{ sent: number; errors?: string[] }>(
    '/safety/knowledge-articles/radar/notify/test',
    {
      method: 'POST',
      headers: { 'X-Dazah-Page-Key': 'safety:system-config:safety-feishu-settings' },
    },
  )
  return res
}

export async function testHazardDueNotify() {
  const res = await fetchApi<{ sent: number; errors?: string[] }>(
    '/safety/feishu-settings/hazard-due-notify/test',
    {
      method: 'POST',
      headers: { 'X-Dazah-Page-Key': 'safety:system-config:safety-feishu-settings' },
    },
  )
  return res
}

export async function getRadarRunDetail(runId: string) {
  const res = await fetchApi<RadarRunDetail>(
    `/safety/knowledge-articles/radar/runs/${runId}`,
    { headers: { 'X-Dazah-Page-Key': RADAR_PAGE_KEY } },
  )
  return res
}

export async function runRadarScan(dryRun = false) {
  const res = await fetchApi<Record<string, unknown>>(
    `/safety/knowledge-articles/radar/run?dry_run=${dryRun}`,
    {
      method: 'POST',
      headers: { 'X-Dazah-Page-Key': RADAR_PAGE_KEY },
    },
  )
  return res
}

export async function syncSafetyKnowledge() {
  const res = await fetchApi<Record<string, number | string>>('/safety/knowledge-articles/feishu/sync', {
    method: 'POST',
    headers: { 'X-Dazah-Page-Key': 'safety:regulation-info:knowledge-base' },
  })
  return res
}

// ==================== 八大特殊作业报备 Actions ====================

export async function getSpecialOperationReports(params?: SpecialOperationReportQueryParams) {
  const query = new URLSearchParams()
  if (params) {
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    if (params.status) query.set('status', params.status)
    if (params.operation_type) query.set('operation_type', params.operation_type)
    if (params.operation_level) query.set('operation_level', params.operation_level)
    if (params.risk_level) query.set('risk_level', params.risk_level)
    if (params.department) query.set('department', params.department)
    if (params.date_from) query.set('date_from', params.date_from)
    if (params.date_to) query.set('date_to', params.date_to)
    if (params.keyword) query.set('keyword', params.keyword)
    if (params.is_critical !== undefined) query.set('is_critical', String(params.is_critical))
  }
  const qs = query.toString()
  const response = await fetchApi<SpecialOperationReport[]>(`/safety/special-operation-reports${qs ? `?${qs}` : ''}`)
  return response
}

export async function getSpecialOperationReport(id: string) {
  const response = await fetchApi<SpecialOperationReport>(`/safety/special-operation-reports/${id}`)
  return response
}

export async function createSpecialOperationReport(data: SpecialOperationReportFormData) {
  const response = await fetchApi<SpecialOperationReport>('/safety/special-operation-reports', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/risk-reporting')
  revalidatePath('/safety/special-ops')

  return response
}

export async function updateSpecialOperationReport(id: string, data: Partial<SpecialOperationReportFormData>) {
  const response = await fetchApi<SpecialOperationReport>(`/safety/special-operation-reports/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/risk-reporting')
  revalidatePath('/safety/special-ops')

  return response
}

export async function deleteSpecialOperationReport(id: string) {
  const response = await fetchApi<null>(`/safety/special-operation-reports/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/risk-reporting')

  return response
}

export async function submitSpecialOperationReport(id: string) {
  const response = await fetchApi<SpecialOperationReport>(`/safety/special-operation-reports/${id}/submit`, { method: 'POST' })
  revalidatePath('/safety/risk-reporting')
  revalidatePath('/safety/special-ops')

  return response
}

export async function approveSpecialOperationReport(id: string) {
  const response = await fetchApi<SpecialOperationReport>(`/safety/special-operation-reports/${id}/approve`, { method: 'POST' })
  revalidatePath('/safety/risk-reporting')
  revalidatePath('/safety/special-ops')

  return response
}

export async function rejectSpecialOperationReport(id: string, reason: string) {
  const response = await fetchApi<SpecialOperationReport>(`/safety/special-operation-reports/${id}/reject?reason=${encodeURIComponent(reason)}`, { method: 'POST' })
  revalidatePath('/safety/risk-reporting')
  revalidatePath('/safety/special-ops')

  return response
}

// ==================== 特殊作业台账 Actions ====================

export async function getSpecialOperationLedger(params?: SpecialOperationLedgerQueryParams) {
  const query = new URLSearchParams()
  if (params) {
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    if (params.operation_type) query.set('operation_type', params.operation_type)
    if (params.operation_level) query.set('operation_level', params.operation_level)
    if (params.risk_level) query.set('risk_level', params.risk_level)
    if (params.department) query.set('department', params.department)
    if (params.date_from) query.set('date_from', params.date_from)
    if (params.date_to) query.set('date_to', params.date_to)
    if (params.keyword) query.set('keyword', params.keyword)
    if (params.is_critical !== undefined) query.set('is_critical', String(params.is_critical))
  }
  const qs = query.toString()
  const response = await fetchApi<SpecialOperationReport[]>(`/safety/special-operation-ledger${qs ? `?${qs}` : ''}`)
  return response
}

export async function getSpecialOperationLedgerStats(params?: {
  operation_type?: string
  operation_level?: string
  risk_level?: string
  department?: string
  date_from?: string
  date_to?: string
  keyword?: string
  is_critical?: boolean
}) {
  const search = new URLSearchParams()
  if (params?.operation_type) search.set('operation_type', params.operation_type)
  if (params?.operation_level) search.set('operation_level', params.operation_level)
  if (params?.risk_level) search.set('risk_level', params.risk_level)
  if (params?.department) search.set('department', params.department)
  if (params?.date_from) search.set('date_from', params.date_from)
  if (params?.date_to) search.set('date_to', params.date_to)
  if (params?.keyword) search.set('keyword', params.keyword)
  if (params?.is_critical !== undefined) search.set('is_critical', String(params.is_critical))
  const query = search.toString()
  const response = await fetchApi<SpecialOperationLedgerStats[]>(
    `/safety/special-operation-ledger/stats${query ? `?${query}` : ''}`
  )
  return response
}

// ==================== 每日风险作业报备 Actions ====================

export async function getDailyRiskReports(params?: DailyRiskReportQueryParams) {
  const query = new URLSearchParams()
  if (params) {
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    if (params.status) query.set('status', params.status)
    if (params.department) query.set('department', params.department)
    if (params.report_date) query.set('report_date', params.report_date)
    if (params.keyword) query.set('keyword', params.keyword)
    if (params.report_type) query.set('report_type', params.report_type)
  }
  const qs = query.toString()
  const response = await fetchApi<DailyRiskReport[]>(`/safety/daily-risk-reports${qs ? `?${qs}` : ''}`)
  return response
}

export async function getDailyRiskReport(id: string) {
  const response = await fetchApi<DailyRiskReport>(`/safety/daily-risk-reports/${id}`)
  return response
}

export async function createDailyRiskReport(data: DailyRiskReportFormData) {
  const response = await fetchApi<DailyRiskReport>('/safety/daily-risk-reports', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/risk-reporting')
  return response
}

export async function updateDailyRiskReport(id: string, data: Partial<DailyRiskReportFormData>) {
  const response = await fetchApi<DailyRiskReport>(`/safety/daily-risk-reports/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/risk-reporting')
  return response
}

export async function deleteDailyRiskReport(id: string) {
  const response = await fetchApi<null>(`/safety/daily-risk-reports/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/risk-reporting')
  return response
}

export async function submitDailyRiskReport(id: string) {
  const response = await fetchApi<DailyRiskReport>(`/safety/daily-risk-reports/${id}/submit`, { method: 'POST' })
  revalidatePath('/safety/risk-reporting')
  return response
}

export async function approveDailyRiskReport(id: string) {
  const response = await fetchApi<DailyRiskReport>(`/safety/daily-risk-reports/${id}/approve`, { method: 'POST' })
  revalidatePath('/safety/risk-reporting')
  return response
}

export async function rejectDailyRiskReport(id: string, reason: string) {
  const response = await fetchApi<DailyRiskReport>(`/safety/daily-risk-reports/${id}/reject?reason=${encodeURIComponent(reason)}`, { method: 'POST' })
  revalidatePath('/safety/risk-reporting')
  return response
}

export async function getHazardRiskOptions(params?: {
  department?: string
  keyword?: string
  page?: number
  page_size?: number
}) {
  const query = new URLSearchParams()
  if (params) {
    if (params.page) query.set('page', String(params.page))
    if (params.page_size) query.set('page_size', String(params.page_size))
    if (params.department) query.set('department', params.department)
    if (params.keyword) query.set('keyword', params.keyword)
  }
  const qs = query.toString()
  const response = await fetchApi<HazardRiskOption[]>(`/safety/hazard-identifications/risk-options${qs ? `?${qs}` : ''}`)
  return response
}

// ==================== 职业危害因素监测 Actions ====================


export async function getOhHazardMonitors(params: OhHazardMonitorQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.detection_type) searchParams.set('detection_type', params.detection_type)
  if (params.workplace) searchParams.set('workplace', params.workplace)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  const qs = searchParams.toString()
  const endpoint = `/safety/oh-hazard-monitors${qs ? '?' + qs : ''}`
  return fetchApi<OhHazardMonitor[]>(endpoint)
}

export async function getOhHazardMonitor(id: string) {
  return fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}`)
}

export async function createOhHazardMonitor(data: OhHazardMonitorFormData) {
  const res = await fetchApi<OhHazardMonitor>('/safety/oh-hazard-monitors', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function updateOhHazardMonitor(id: string, data: Partial<OhHazardMonitorFormData>) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function deleteOhHazardMonitor(id: string) {
  const res = await fetchApi<null>(`/safety/oh-hazard-monitors/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/occupational-health')
  return res
}

// Monitor Workflow
export async function startMonitor(id: string) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/start`, { method: 'POST' })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function completeMonitor(id: string) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/complete`, { method: 'POST' })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function verifyMonitor(id: string, data: { verified_by?: string; comments?: string }) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/verify`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

// Monitor Sub-records
export async function addDetectionResult(id: string, data: Record<string, unknown>) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/detection-results`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function updateDetectionResult(id: string, index: number, data: Record<string, unknown>) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/detection-results/${index}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function deleteDetectionResult(id: string, index: number) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/detection-results/${index}`, { method: 'DELETE' })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function addMonitorAbnormality(id: string, data: Record<string, unknown>) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/abnormality-records`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function updateMonitorAbnormalityStatus(id: string, index: number, status: string) {
  const res = await fetchApi<OhHazardMonitor>(`/safety/oh-hazard-monitors/${id}/abnormality-records/${index}?status=${encodeURIComponent(status)}`, { method: 'PUT' })
  revalidatePath('/safety/occupational-health')
  return res
}


// ==================== 职业健康体检 Actions ====================


export async function getOhHealthExams(params: OhHealthExamQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.exam_type) searchParams.set('exam_type', params.exam_type)
  if (params.department) searchParams.set('department', params.department)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  const qs = searchParams.toString()
  const endpoint = `/safety/oh-health-exams${qs ? '?' + qs : ''}`
  return fetchApi<OhHealthExam[]>(endpoint)
}

export async function getOhHealthExam(id: string) {
  return fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}`)
}

export async function createOhHealthExam(data: OhHealthExamFormData) {
  const res = await fetchApi<OhHealthExam>('/safety/oh-health-exams', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function updateOhHealthExam(id: string, data: Partial<OhHealthExamFormData>) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function deleteOhHealthExam(id: string) {
  const res = await fetchApi<null>(`/safety/oh-health-exams/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/occupational-health')
  return res
}

// Exam Workflow
export async function startExam(id: string) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/start`, { method: 'POST' })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function completeExam(id: string) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/complete`, { method: 'POST' })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function archiveExam(id: string) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/archive`, { method: 'POST' })
  revalidatePath('/safety/occupational-health')
  return res
}

// Exam Sub-records
export async function addExamItem(id: string, data: Record<string, unknown>) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/exam-items`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function updateExamItem(id: string, index: number, data: Record<string, unknown>) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/exam-items/${index}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function deleteExamItem(id: string, index: number) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/exam-items/${index}`, { method: 'DELETE' })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function setExamConclusion(id: string, conclusion: string, remarks?: string) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/conclusion`, {
    method: 'PUT',
    body: JSON.stringify({ conclusion, remarks }),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function addExamAbnormality(id: string, data: Record<string, unknown>) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/abnormality-records`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function updateExamAbnormalityStatus(id: string, index: number, status: string) {
  const res = await fetchApi<OhHealthExam>(`/safety/oh-health-exams/${id}/abnormality-records/${index}?status=${encodeURIComponent(status)}`, { method: 'PUT' })
  revalidatePath('/safety/occupational-health')
  return res
}

// ==================== 检测报告导入 Actions ====================

const OH_DETECTION_PAGE_KEY = 'safety:occupational-health-group:oh-monitor'

export async function getOhDetectionReports(
  params: { page?: number; page_size?: number; keyword?: string; year?: number } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.keyword) searchParams.set('keyword', params.keyword)
  if (params.year) searchParams.set('year', String(params.year))
  const qs = searchParams.toString()
  return fetchApi<OhDetectionReport[]>(
    `/safety/oh-detection-reports${qs ? '?' + qs : ''}`,
    { headers: { 'X-Dazah-Page-Key': OH_DETECTION_PAGE_KEY } }
  )
}

export async function getOhDetectionReport(id: string) {
  return fetchApi<OhDetectionReport>(`/safety/oh-detection-reports/${id}`, {
    headers: { 'X-Dazah-Page-Key': OH_DETECTION_PAGE_KEY },
  })
}

export async function getOhDetectionResults(id: string, params: OhDetectionResultQueryParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  if (params.factor_category) searchParams.set('factor_category', params.factor_category)
  if (params.record_type) searchParams.set('record_type', params.record_type)
  if (params.workshop) searchParams.set('workshop', params.workshop)
  if (params.verdict) searchParams.set('verdict', params.verdict)
  if (params.is_noise_post !== undefined && params.is_noise_post !== null) {
    searchParams.set('is_noise_post', String(params.is_noise_post))
  }
  if (params.keyword) searchParams.set('keyword', params.keyword)
  const qs = searchParams.toString()
  return fetchApi<OhDetectionResult[]>(
    `/safety/oh-detection-reports/${id}/results${qs ? '?' + qs : ''}`,
    { headers: { 'X-Dazah-Page-Key': OH_DETECTION_PAGE_KEY } }
  )
}

async function uploadDetectionReport<T>(
  endpoint: string,
  file: File,
  fields: Record<string, string> = {}
): Promise<ApiResponse<T>> {
  const formData = new FormData()
  formData.append('file', file)
  for (const [key, value] of Object.entries(fields)) {
    if (value !== '') formData.append(key, value)
  }
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  uploadHeaders['X-Dazah-Page-Key'] = OH_DETECTION_PAGE_KEY
  let response: Response
  try {
    response = await fetch(`${API_BASE}/safety/oh-detection-reports/${endpoint}`, {
      method: 'POST',
      headers: uploadHeaders,
      body: formData,
    })
  } catch {
    return { code: -1, message: '网络请求失败，无法连接到后端服务' } as ApiResponse<T>
  }
  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorJson = await response.json()
      errorMessage = errorJson.message || errorJson.detail || errorMessage
    } catch {
      // 保留默认错误信息
    }
    return { code: response.status, message: errorMessage } as ApiResponse<T>
  }
  return response.json()
}

export async function parseOhDetectionReport(file: File) {
  return uploadDetectionReport<OhDetectionParsePreview>('parse', file)
}

export async function importOhDetectionReport(
  file: File,
  fields: {
    report_no: string
    report_name?: string
    company_name?: string
    detection_agency?: string
    detection_date?: string
    remark?: string
  }
) {
  const res = await uploadDetectionReport<OhDetectionImportResult>('import', file, {
    report_no: fields.report_no,
    report_name: fields.report_name || '',
    company_name: fields.company_name || '',
    detection_agency: fields.detection_agency || '',
    detection_date: fields.detection_date || '',
    remark: fields.remark || '',
  })
  revalidatePath('/safety/occupational-health')
  return res
}

export async function deleteOhDetectionReport(id: string) {
  const res = await fetchApi<null>(`/safety/oh-detection-reports/${id}`, {
    method: 'DELETE',
    headers: { 'X-Dazah-Page-Key': OH_DETECTION_PAGE_KEY },
  })
  revalidatePath('/safety/occupational-health')
  return res
}

// ============ Scheduled Tasks ============

export async function getScheduledTasks(params: ScheduledTaskQueryParams = {}) {
  const { page = 1, page_size = 20, is_enabled, search } = params
  const qs = new URLSearchParams({ page: String(page), page_size: String(page_size) })
  if (is_enabled !== undefined) qs.set('is_enabled', String(is_enabled))
  if (search) qs.set('search', search)
  const res = await fetchApi<ScheduledTask[]>(`/safety/scheduled-tasks?${qs.toString()}`)
  return res
}

export async function getScheduledTask(id: string) {
  const res = await fetchApi<ScheduledTask>(`/safety/scheduled-tasks/${id}`)
  return res
}

export async function createScheduledTask(data: ScheduledTaskFormData) {
  const res = await fetchApi<ScheduledTask>('/safety/scheduled-tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/scheduled-tasks')
  return res
}

export async function updateScheduledTask(id: string, data: Partial<ScheduledTaskFormData>) {
  const res = await fetchApi<ScheduledTask>(`/safety/scheduled-tasks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/scheduled-tasks')
  return res
}

export async function deleteScheduledTask(id: string) {
  const res = await fetchApi<null>(`/safety/scheduled-tasks/${id}`, { method: 'DELETE' })
  revalidatePath('/safety/scheduled-tasks')
  return res
}

export async function toggleScheduledTask(id: string, enabled: boolean) {
  const res = await fetchApi<ScheduledTask>(`/safety/scheduled-tasks/${id}/toggle?enabled=${enabled}`, { method: 'POST' })
  revalidatePath('/safety/scheduled-tasks')
  return res
}

export async function runScheduledTaskNow(id: string) {
  const res = await fetchApi<ScheduledTaskLog>(`/safety/scheduled-tasks/${id}/run`, { method: 'POST' })
  revalidatePath('/safety/scheduled-tasks')
  return res
}

export async function getScheduledTaskLogs(taskId: string, page = 1, page_size = 20) {
  const qs = new URLSearchParams({ page: String(page), page_size: String(page_size) })
  const res = await fetchApi<ScheduledTaskLog[]>(`/safety/scheduled-tasks/${taskId}/logs?${qs.toString()}`)
  return res
}

export async function getDataSourceOptions() {
  const res = await fetchApi<DataSourceOption[]>('/safety/scheduled-tasks/data-source-options')
  return res
}

export async function getFeishuChats() {
  const res = await fetchApi<FeishuChat[]>('/safety/scheduled-tasks/feishu-chats')
  return res
}

export async function previewCard(data: CardPreviewRequest) {
  const res = await fetchApi<CardPreviewResponse>('/safety/scheduled-tasks/preview-card', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res
}

// ============ Feishu Settings ============

export async function getSafetyFeishuSettings() {
  const res = await fetchApi<SafetyFeishuAppSettingsDetail>('/safety/feishu-settings/app', {
    headers: { 'X-Dazah-Page-Key': 'safety:system-config:safety-feishu-settings' },
  })
  return res
}

export async function saveSafetyFeishuSettings(data: UpdateSafetyFeishuAppSettingsRequest) {
  const res = await fetchApi<SafetyFeishuAppSettingsDetail>('/safety/feishu-settings/app', {
    method: 'PUT',
    body: JSON.stringify(data),
    headers: { 'X-Dazah-Page-Key': 'safety:system-config:safety-feishu-settings' },
  })
  return res
}

export async function testSafetyFeishuSettings() {
  const res = await fetchApi<SafetyFeishuSettingsTestResult>('/safety/feishu-settings/app/test', {
    method: 'POST',
    headers: { 'X-Dazah-Page-Key': 'safety:system-config:safety-feishu-settings' },
  })
  return res
}

export async function getSafetyFeishuWsStatus() {
  const res = await fetchApi<Record<string, unknown>>('/safety/feishu/ws/status')
  return res
}

export async function restartSafetyFeishuWs() {
  const res = await fetchApi<Record<string, unknown>>('/safety/feishu/ws/restart', {
    method: 'POST',
  })
  return res
}

// ============ 页面飞书多维表格镜像 ============

export async function getSafetyPageTableTabs(params: { pageKey: string }) {
  return fetchApi<PageTableTabListResponse>(
    `/safety/page-tables/${encodeURIComponent(params.pageKey)}/tabs`,
    { headers: { 'X-Dazah-Page-Key': params.pageKey } }
  )
}

export async function getSafetyPageTableRecords(params: {
  pageKey: string
  page?: number
  pageSize?: number
  keyword?: string
  sortField?: string | null
  sortDirection?: 'asc' | 'desc'
  filterField?: string | null
  filterValue?: string | null
  conditions?: Array<{ field: string; value: string; op?: 'eq' | 'neq' | 'gte' | 'lte' }>
  tableId?: string | null
  overLimitOnly?: boolean
}) {
  const search = new URLSearchParams()
  if (params.page) search.set('page', String(params.page))
  if (params.pageSize) search.set('page_size', String(params.pageSize))
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.sortField) search.set('sort_field', params.sortField)
  if (params.sortDirection) search.set('sort_direction', params.sortDirection)
  if (params.filterField) search.set('filter_field', params.filterField)
  if (params.filterValue) search.set('filter_value', params.filterValue)
  if (params.conditions?.length) {
    search.set('conditions', JSON.stringify(params.conditions))
  }
  if (params.tableId) search.set('table_id', params.tableId)
  if (params.overLimitOnly) search.set('over_limit_only', 'true')
  const query = search.toString()
  const res = await fetchApi<PageTableRecordsResponse>(
    `/safety/page-tables/${encodeURIComponent(params.pageKey)}/records${query ? `?${query}` : ''}`,
    { headers: { 'X-Dazah-Page-Key': params.pageKey } }
  )
  return res
}

// 未关闭隐患明细（安全总览驾驶舱卡片）：数据来自 24小时值班隐患 /
// 隐患台账两张镜像表，请求携带对应页面键
export async function getOpenHazardDetails(params: {
  source: 'duty' | 'ledger'
  limit?: number
}) {
  const pageKeys: Record<string, string> = {
    duty: 'safety:risk-hazard:hazard-inspection:hazard-duty',
    ledger: 'safety:risk-hazard:hazard-inspection:hazard-quick-report',
  }
  const search = new URLSearchParams()
  search.set('source', params.source)
  if (params.limit) search.set('limit', String(params.limit))
  return fetchApi<components['schemas']['OpenHazardDetailItem'][]>(
    `/safety/open-hazard-details?${search.toString()}`,
    { headers: { 'X-Dazah-Page-Key': pageKeys[params.source] } }
  )
}

export async function getSafetyPageTableStats(params: {
  pageKey: string
  groupBy?: string[]
  tableId?: string | null
  keyword?: string
  conditions?: Array<{ field: string; value: string; op?: 'eq' | 'neq' | 'gte' | 'lte' }>
  dueField?: string
  closeField?: string
}) {
  const search = new URLSearchParams()
  for (const field of params.groupBy ?? []) search.append('group_by', field)
  if (params.tableId) search.set('table_id', params.tableId)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.conditions?.length) {
    search.set('conditions', JSON.stringify(params.conditions))
  }
  if (params.dueField) search.set('due_field', params.dueField)
  if (params.closeField) search.set('close_field', params.closeField)
  const query = search.toString()
  return fetchApi<PageTableStatsResponse>(
    `/safety/page-tables/${encodeURIComponent(params.pageKey)}/stats${query ? `?${query}` : ''}`,
    { headers: { 'X-Dazah-Page-Key': params.pageKey } }
  )
}

export async function getSafetyPageTableFieldValues(params: {
  pageKey: string
  field: string
  tableId?: string | null
}) {
  const search = new URLSearchParams()
  search.set('field', params.field)
  if (params.tableId) search.set('table_id', params.tableId)
  const query = search.toString()
  return fetchApi<PageTableFieldValuesResponse>(
    `/safety/page-tables/${encodeURIComponent(params.pageKey)}/values${query ? `?${query}` : ''}`,
    { headers: { 'X-Dazah-Page-Key': params.pageKey } }
  )
}

export async function createSafetyPageTableRecord(params: {
  pageKey: string
  fields: Record<string, unknown>
  tableId?: string | null
}) {
  const search = new URLSearchParams()
  if (params.tableId) search.set('table_id', params.tableId)
  const query = search.toString()
  const res = await fetchApi<PageTableRecord>(
    `/safety/page-tables/${encodeURIComponent(params.pageKey)}/records${query ? `?${query}` : ''}`,
    {
      method: 'POST',
      body: JSON.stringify({ fields: params.fields }),
      headers: { 'X-Dazah-Page-Key': params.pageKey },
    }
  )
  return res
}

export async function updateSafetyPageTableRecord(params: {
  pageKey: string
  recordId: string
  fields: Record<string, unknown>
  tableId?: string | null
}) {
  const search = new URLSearchParams()
  if (params.tableId) search.set('table_id', params.tableId)
  const query = search.toString()
  const res = await fetchApi<PageTableRecord>(
    `/safety/page-tables/${encodeURIComponent(params.pageKey)}/records/${encodeURIComponent(params.recordId)}${query ? `?${query}` : ''}`,
    {
      method: 'PUT',
      body: JSON.stringify({ fields: params.fields }),
      headers: { 'X-Dazah-Page-Key': params.pageKey },
    }
  )
  return res
}

export async function uploadSafetyPageTableAttachment(params: {
  pageKey: string
  recordId: string
  fieldName: string
  file: File
  tableId?: string | null
}) {
  const formData = new FormData()
  formData.append('file', params.file)
  const search = new URLSearchParams()
  if (params.tableId) search.set('table_id', params.tableId)
  const query = search.toString()
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/page-tables/${encodeURIComponent(params.pageKey)}/records/${encodeURIComponent(params.recordId)}/attachments/${encodeURIComponent(params.fieldName)}${query ? `?${query}` : ''}`,
    {
      method: 'POST',
      headers: { ...uploadHeaders, 'X-Dazah-Page-Key': params.pageKey },
      body: formData,
    }
  )
  const payload = (await response.json()) as ApiResponse<PageTableAttachmentUploadResponse>
  return payload
}

// ============ 页面飞书表格绑定配置 ============

export async function getSafetyPageFeishuConfigs() {
  const res = await fetchApi<PageFeishuConfigListResponse>('/safety/page-feishu-configs', {
    headers: { 'X-Dazah-Page-Key': SAFETY_FEISHU_SETTINGS_PAGE_KEY },
  })
  return res
}

export async function saveSafetyPageFeishuConfig(
  pageKey: string,
  data: UpdatePageFeishuConfigRequest
) {
  const res = await fetchApi<PageFeishuConfigItem>(
    `/safety/page-feishu-configs/${encodeURIComponent(pageKey)}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
      headers: { 'X-Dazah-Page-Key': SAFETY_FEISHU_SETTINGS_PAGE_KEY },
    }
  )
  return res
}

export async function testSafetyPageFeishuConfig(pageKey: string) {
  const res = await fetchApi<PageFeishuConfigTestResult>(
    `/safety/page-feishu-configs/${encodeURIComponent(pageKey)}/test`,
    {
      method: 'POST',
      headers: { 'X-Dazah-Page-Key': SAFETY_FEISHU_SETTINGS_PAGE_KEY },
    }
  )
  return res
}

export async function syncSafetyPageFeishuConfig(pageKey: string) {
  const res = await fetchApi<PageFeishuConfigItem>(
    `/safety/page-feishu-configs/${encodeURIComponent(pageKey)}/sync`,
    {
      method: 'POST',
      headers: { 'X-Dazah-Page-Key': SAFETY_FEISHU_SETTINGS_PAGE_KEY },
    }
  )
  return res
}

export async function resolveSafetyPageFeishuUrl(url: string) {
  const res = await fetchApi<ResolvedPageFeishuUrl>('/safety/page-feishu-configs/resolve', {
    method: 'POST',
    body: JSON.stringify({ url }),
    headers: { 'X-Dazah-Page-Key': SAFETY_FEISHU_SETTINGS_PAGE_KEY },
  })
  return res
}

// Legacy hazard revision functions (stubs for backward compatibility)
export async function getHazardRevisionRecords(): Promise<any[]> {
  console.warn('getHazardRevisionRecords is deprecated')
  return []
}

export async function createHazardRevisionRecord(): Promise<any> {
  console.warn('createHazardRevisionRecord is deprecated')
  return null
}

export async function updateHazardRevisionRecord(): Promise<any> {
  console.warn('updateHazardRevisionRecord is deprecated')
  return null
}

export async function deleteHazardRevisionRecord(): Promise<void> {
  console.warn('deleteHazardRevisionRecord is deprecated')
}

export async function approveHazardRevision(): Promise<any> {
  console.warn('approveHazardRevision is deprecated')
  return null
}

export async function uploadHazardRevisionDocument(): Promise<any> {
  console.warn('uploadHazardRevisionDocument is deprecated')
  return null
}

export async function linkRevisionToArchive(): Promise<any> {
  console.warn('linkRevisionToArchive is deprecated')
  return null
}

export async function getHazardRevisionArchives(): Promise<any[]> {
  console.warn('getHazardRevisionArchives is deprecated')
  return []
}

export async function createHazardRevisionArchive(): Promise<any> {
  console.warn('createHazardRevisionArchive is deprecated')
  return null
}

export async function updateHazardRevisionArchive(): Promise<any> {
  console.warn('updateHazardRevisionArchive is deprecated')
  return null
}

export async function deleteHazardRevisionArchive(): Promise<void> {
  console.warn('deleteHazardRevisionArchive is deprecated')
}

export async function completeRectification(): Promise<any> {
  console.warn('completeRectification is deprecated')
  return null
}

export async function verifyRectification(): Promise<any> {
  console.warn('verifyRectification is deprecated')
  return null
}

// ============ 灭火器 / 消防栓点检 ============

type FireEquipmentListResponse =
  components['schemas']['FireEquipmentListResponse']
type FireEquipmentStats = components['schemas']['FireEquipmentStats']
type FireEquipmentDetailResponse =
  components['schemas']['FireEquipmentDetailResponse']
type FireInspectionListResponse =
  components['schemas']['FireInspectionListResponse']
type FireInspectionRecordItem =
  components['schemas']['FireInspectionRecordItem']
type CreateFireInspectionRequest =
  components['schemas']['CreateFireInspectionRequest']

/**
 * 消防点检页的页面上下文头：台账、详情与提交接口都绑定该页权限，
 * 与镜像页数据接口的 X-Dazah-Page-Key 口径一致。
 */
function fireEquipmentPageHeaders(pageKey: string): Record<string, string> {
  return { 'X-Dazah-Page-Key': pageKey }
}

export async function getFireEquipmentList(params: {
  pageKey: string
  page?: number
  pageSize?: number
  equipmentType?: string | null
  keyword?: string | null
  tableId?: string | null
  monthStatus?: string | null
  expiryStatus?: string | null
}) {
  const search = new URLSearchParams()
  search.set('page', String(params.page ?? 1))
  search.set('page_size', String(params.pageSize ?? 20))
  if (params.equipmentType) search.set('equipment_type', params.equipmentType)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.tableId) search.set('table_id', params.tableId)
  if (params.monthStatus) search.set('month_status', params.monthStatus)
  if (params.expiryStatus) search.set('expiry_status', params.expiryStatus)
  return fetchApi<FireEquipmentListResponse>(
    `/safety/fire-equipment?${search.toString()}`,
    { headers: fireEquipmentPageHeaders(params.pageKey) }
  )
}

export async function getFireEquipmentStats(params: { pageKey: string }) {
  return fetchApi<FireEquipmentStats>('/safety/fire-equipment/stats', {
    headers: fireEquipmentPageHeaders(params.pageKey),
  })
}

export async function getFireEquipmentDetail(params: {
  pageKey: string
  equipmentId: string
}) {
  return fetchApi<FireEquipmentDetailResponse>(
    `/safety/fire-equipment/${encodeURIComponent(params.equipmentId)}`,
    { headers: fireEquipmentPageHeaders(params.pageKey) }
  )
}

export async function getFireInspectionRecords(params: {
  pageKey: string
  page?: number
  pageSize?: number
  equipmentType?: string | null
  result?: string | null
  keyword?: string | null
  inspectedFrom?: string | null
  inspectedTo?: string | null
}) {
  const search = new URLSearchParams()
  search.set('page', String(params.page ?? 1))
  search.set('page_size', String(params.pageSize ?? 20))
  if (params.equipmentType) search.set('equipment_type', params.equipmentType)
  if (params.result) search.set('result', params.result)
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.inspectedFrom) search.set('inspected_from', params.inspectedFrom)
  if (params.inspectedTo) search.set('inspected_to', params.inspectedTo)
  return fetchApi<FireInspectionListResponse>(
    `/safety/fire-inspection-records?${search.toString()}`,
    { headers: fireEquipmentPageHeaders(params.pageKey) }
  )
}

export async function submitFireEquipmentInspection(params: {
  pageKey: string
  equipmentId: string
  data: CreateFireInspectionRequest
}): Promise<ApiResponse<FireInspectionRecordItem>> {
  return fetchApi<FireInspectionRecordItem>(
    `/safety/fire-equipment/${encodeURIComponent(params.equipmentId)}/inspections`,
    {
      method: 'POST',
      headers: {
        ...fireEquipmentPageHeaders(params.pageKey),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params.data),
    }
  )
}

export async function syncFireEquipment(params: { pageKey: string }) {
  return fetchApi<FireEquipmentStats>('/safety/fire-equipment/sync', {
    method: 'POST',
    headers: fireEquipmentPageHeaders(params.pageKey),
  })
}

type FireInspectionWritebackInitResponse =
  components['schemas']['FireInspectionWritebackInitResponse']

/** 一键在绑定的 Base 下创建（或复用）「点检记录」回写子表。 */
export async function initFireEquipmentWritebackTable(params: { pageKey: string }) {
  return fetchApi<FireInspectionWritebackInitResponse>(
    '/safety/fire-equipment/writeback-table/init',
    {
      method: 'POST',
      headers: fireEquipmentPageHeaders(params.pageKey),
    }
  )
}

export async function testFireExpiryNotify() {
  const res = await fetchApi<{ sent: number; errors?: string[] }>(
    '/safety/feishu-settings/fire-expiry-notify/test',
    {
      method: 'POST',
      headers: { 'X-Dazah-Page-Key': 'safety:system-config:safety-feishu-settings' },
    },
  )
  return res
}

type FireEquipmentDashboardResponse =
  components['schemas']['FireEquipmentDashboardResponse']

export async function getFireEquipmentDashboard(params: { pageKey: string }) {
  return fetchApi<FireEquipmentDashboardResponse>(
    '/safety/fire-equipment/dashboard',
    { headers: fireEquipmentPageHeaders(params.pageKey) }
  )
}

// ============ 应急处置卡 ============

type EmergencyCardItem = components['schemas']['EmergencyCardResponse']
type EmergencyCardListData = components['schemas']['EmergencyCardListResponse']
type EmergencyCardStatsData = components['schemas']['EmergencyCardStatsResponse']
type EmergencyCardStep = components['schemas']['EmergencyCardStep']
type EmergencyCardCreateInput = components['schemas']['EmergencyCardCreate']
type EmergencyCardUpdateInput = components['schemas']['EmergencyCardUpdate']
type EmergencyCardReviewData = components['schemas']['EmergencyCardReviewResponse']

export type {
  EmergencyCardItem,
  EmergencyCardListData,
  EmergencyCardStatsData,
  EmergencyCardStep,
  EmergencyCardCreateInput,
  EmergencyCardUpdateInput,
  EmergencyCardReviewData,
}

export interface EmergencyCardQueryParams {
  page?: number
  page_size?: number
  workshop?: string
  position?: string
  accident_type?: string
  keyword?: string
}

export async function getEmergencyCards(
  params: EmergencyCardQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.workshop) searchParams.set('workshop', params.workshop)
  if (params.position) searchParams.set('position', params.position)
  if (params.accident_type) {
    searchParams.set('accident_type', params.accident_type)
  }
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  const endpoint = `/safety/emergency-cards${queryString ? `?${queryString}` : ''}`
  return fetchApi<EmergencyCardListData>(endpoint)
}

export async function getEmergencyCardStats() {
  return fetchApi<EmergencyCardStatsData>('/safety/emergency-cards/stats')
}

export async function getEmergencyCard(id: string) {
  return fetchApi<EmergencyCardItem>(`/safety/emergency-cards/${id}`)
}

export async function createEmergencyCard(data: EmergencyCardCreateInput) {
  const response = await fetchApi<EmergencyCardItem>('/safety/emergency-cards', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/emergency-card')
  return response
}

export async function updateEmergencyCard(
  id: string,
  data: EmergencyCardUpdateInput
) {
  const response = await fetchApi<EmergencyCardItem>(
    `/safety/emergency-cards/${id}`,
    {
      method: 'PUT',
      body: JSON.stringify(data),
    }
  )
  revalidatePath('/safety/emergency-card')
  return response
}

export async function deleteEmergencyCard(id: string) {
  const response = await fetchApi<null>(`/safety/emergency-cards/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/emergency-card')
  return response
}

export async function reviewEmergencyCard(id: string) {
  return fetchApi<EmergencyCardReviewData>(
    `/safety/emergency-cards/${id}/ai-review`,
    { method: 'POST' }
  )
}

// ══════════════════════════════════════════════════════════════
// 总览驾驶舱（厂区平面图落点 + 超储 + 近7日统计）
// ══════════════════════════════════════════════════════════════

type SafetyOverviewData = components['schemas']['SafetyOverviewResponse']
type CampusBuildingItem = components['schemas']['CampusBuildingItem']
type MapBuildingMarkers = components['schemas']['MapBuildingMarkers']
type MapRiskItem = components['schemas']['MapRiskItem']
type UnmappedRiskGroup = components['schemas']['UnmappedRiskGroup']
type OverLimitChemicalItem = components['schemas']['OverLimitChemicalItem']

export type {
  SafetyOverviewData,
  CampusBuildingItem,
  MapBuildingMarkers,
  MapRiskItem,
  UnmappedRiskGroup,
  OverLimitChemicalItem,
}

export async function getSafetyOverview() {
  return fetchApi<SafetyOverviewData>('/safety/dashboard/overview')
}

// ══════════════════════════════════════════════════════════════
// 目标责任与绩效
// ══════════════════════════════════════════════════════════════

type SafetyTargetItem = components['schemas']['SafetyTargetResponse']
type SafetyTargetListData = components['schemas']['SafetyTargetListResponse']
type SafetyTargetStatsData = components['schemas']['SafetyTargetStatsResponse']
type SafetyTargetRecordItem = components['schemas']['SafetyTargetRecordResponse']
type SafetyTargetCreateInput = components['schemas']['SafetyTargetCreate']
type SafetyTargetUpdateInput = components['schemas']['SafetyTargetUpdate']
type SafetyTargetRecordUpdateInput =
  components['schemas']['SafetyTargetRecordUpdate']

export type {
  SafetyTargetItem,
  SafetyTargetListData,
  SafetyTargetStatsData,
  SafetyTargetRecordItem,
  SafetyTargetCreateInput,
  SafetyTargetUpdateInput,
  SafetyTargetRecordUpdateInput,
}

export interface SafetyTargetQueryParams {
  page?: number
  page_size?: number
  year?: number
  category?: string
  department?: string
  status?: string
  keyword?: string
}

export async function getSafetyTargets(
  params: SafetyTargetQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.year) searchParams.set('year', String(params.year))
  if (params.category) searchParams.set('category', params.category)
  if (params.department) searchParams.set('department', params.department)
  if (params.status) searchParams.set('status', params.status)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<SafetyTargetListData>(
    `/safety/safety-targets${queryString ? `?${queryString}` : ''}`
  )
}

export async function getSafetyTargetStats(year?: number) {
  const query = year ? `?year=${year}` : ''
  return fetchApi<SafetyTargetStatsData>(`/safety/safety-targets/stats${query}`)
}

export async function getSafetyTarget(id: string) {
  return fetchApi<SafetyTargetItem>(`/safety/safety-targets/${id}`)
}

export async function createSafetyTarget(data: SafetyTargetCreateInput) {
  const response = await fetchApi<SafetyTargetItem>('/safety/safety-targets', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  revalidatePath('/safety/target-performance')
  return response
}

export async function updateSafetyTarget(
  id: string,
  data: SafetyTargetUpdateInput
) {
  const response = await fetchApi<SafetyTargetItem>(
    `/safety/safety-targets/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/target-performance')
  return response
}

export async function deleteSafetyTarget(id: string) {
  const response = await fetchApi<null>(`/safety/safety-targets/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/target-performance')
  return response
}

export async function upsertSafetyTargetRecord(
  targetId: string,
  period: string,
  data: SafetyTargetRecordUpdateInput
) {
  const response = await fetchApi<SafetyTargetRecordItem>(
    `/safety/safety-targets/${targetId}/records/${encodeURIComponent(period)}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/target-performance')
  return response
}

export async function deleteSafetyTargetRecord(
  targetId: string,
  period: string
) {
  const response = await fetchApi<null>(
    `/safety/safety-targets/${targetId}/records/${encodeURIComponent(period)}`,
    { method: 'DELETE' }
  )
  revalidatePath('/safety/target-performance')
  return response
}

// ══════════════════════════════════════════════════════════════
// 安全目标责任书
// ══════════════════════════════════════════════════════════════

type SafetyTargetAgreementItem =
  components['schemas']['SafetyTargetAgreementResponse']
type SafetyTargetAgreementListData =
  components['schemas']['SafetyTargetAgreementListResponse']
type SafetyTargetAgreementStatsData =
  components['schemas']['SafetyTargetAgreementStatsResponse']
type SafetyTargetAgreementCreateInput =
  components['schemas']['SafetyTargetAgreementCreate']
type SafetyTargetAgreementUpdateInput =
  components['schemas']['SafetyTargetAgreementUpdate']

export type {
  SafetyTargetAgreementItem,
  SafetyTargetAgreementListData,
  SafetyTargetAgreementStatsData,
  SafetyTargetAgreementCreateInput,
  SafetyTargetAgreementUpdateInput,
}

export interface SafetyTargetAgreementQueryParams {
  page?: number
  page_size?: number
  year?: number
  department?: string
  category?: string
  status?: string
  keyword?: string
}

export async function getSafetyTargetAgreements(
  params: SafetyTargetAgreementQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.year) searchParams.set('year', String(params.year))
  if (params.department) searchParams.set('department', params.department)
  if (params.category) searchParams.set('category', params.category)
  if (params.status) searchParams.set('status', params.status)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<SafetyTargetAgreementListData>(
    `/safety/safety-target-agreements${queryString ? `?${queryString}` : ''}`
  )
}

export async function getSafetyTargetAgreementStats(year?: number) {
  const query = year ? `?year=${year}` : ''
  return fetchApi<SafetyTargetAgreementStatsData>(
    `/safety/safety-target-agreements/stats${query}`
  )
}

export async function createSafetyTargetAgreement(
  data: SafetyTargetAgreementCreateInput
) {
  const response = await fetchApi<SafetyTargetAgreementItem>(
    '/safety/safety-target-agreements',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/target-performance')
  return response
}

export async function updateSafetyTargetAgreement(
  id: string,
  data: SafetyTargetAgreementUpdateInput
) {
  const response = await fetchApi<SafetyTargetAgreementItem>(
    `/safety/safety-target-agreements/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/target-performance')
  return response
}

export async function deleteSafetyTargetAgreement(id: string) {
  const response = await fetchApi<null>(`/safety/safety-target-agreements/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/target-performance')
  return response
}

// ══════════════════════════════════════════════════════════════
// 安全生产责任制季度考核
// ══════════════════════════════════════════════════════════════

type SafetyDutyAssessmentItemData =
  components['schemas']['SafetyDutyAssessmentResponse']
type SafetyDutyAssessmentListData =
  components['schemas']['SafetyDutyAssessmentListResponse']
type SafetyDutyAssessmentStatsData =
  components['schemas']['SafetyDutyAssessmentStatsResponse']
type SafetyDutyAssessmentCreateInput =
  components['schemas']['SafetyDutyAssessmentCreate']
type SafetyDutyAssessmentUpdateInput =
  components['schemas']['SafetyDutyAssessmentUpdate']
type SafetyDutyTemplateData = components['schemas']['SafetyDutyTemplateResponse']

export type {
  SafetyDutyAssessmentItemData,
  SafetyDutyAssessmentListData,
  SafetyDutyAssessmentStatsData,
  SafetyDutyAssessmentCreateInput,
  SafetyDutyAssessmentUpdateInput,
  SafetyDutyTemplateData,
}

export interface SafetyDutyAssessmentQueryParams {
  page?: number
  page_size?: number
  year?: number
  quarter?: number
  department?: string
  grade?: string
  keyword?: string
}

export async function getSafetyDutyAssessments(
  params: SafetyDutyAssessmentQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.year) searchParams.set('year', String(params.year))
  if (params.quarter) searchParams.set('quarter', String(params.quarter))
  if (params.department) searchParams.set('department', params.department)
  if (params.grade) searchParams.set('grade', params.grade)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<SafetyDutyAssessmentListData>(
    `/safety/safety-duty-assessments${queryString ? `?${queryString}` : ''}`
  )
}

export async function getSafetyDutyAssessmentStats(year?: number) {
  const query = year ? `?year=${year}` : ''
  return fetchApi<SafetyDutyAssessmentStatsData>(
    `/safety/safety-duty-assessments/stats${query}`
  )
}

export async function getSafetyDutyAssessmentTemplate(department: string) {
  const query = `?department=${encodeURIComponent(department)}`
  return fetchApi<SafetyDutyTemplateData>(
    `/safety/safety-duty-assessments/template${query}`
  )
}

export async function createSafetyDutyAssessment(
  data: SafetyDutyAssessmentCreateInput
) {
  const response = await fetchApi<SafetyDutyAssessmentItemData>(
    '/safety/safety-duty-assessments',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/target-performance')
  return response
}

export async function updateSafetyDutyAssessment(
  id: string,
  data: SafetyDutyAssessmentUpdateInput
) {
  const response = await fetchApi<SafetyDutyAssessmentItemData>(
    `/safety/safety-duty-assessments/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/target-performance')
  return response
}

export async function deleteSafetyDutyAssessment(id: string) {
  const response = await fetchApi<null>(`/safety/safety-duty-assessments/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/target-performance')
  return response
}

// ══════════════════════════════════════════════════════════════
// 责任书 / 季度考核 Excel 批量导入
// ══════════════════════════════════════════════════════════════

type SafetyAgreementImportResult =
  components['schemas']['SafetyAgreementImportResultResponse']
type SafetyDutyAssessmentImportResult =
  components['schemas']['SafetyDutyAssessmentImportResultResponse']

export type {
  SafetyAgreementImportResult,
  SafetyDutyAssessmentImportResult,
}

async function downloadExcel(url: string, fileName: string): Promise<void> {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_BASE}${url}`, { headers })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`模板下载失败 (${response.status}): ${text}`)
  }
  const blob = await response.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(link.href)
}

export async function downloadAgreementImportTemplate(): Promise<void> {
  await downloadExcel(
    '/safety/safety-target-agreements/import-template',
    '责任书签订登记模板.xlsx'
  )
}

export async function importAgreementSigns(
  file: File
): Promise<ApiResponse<SafetyAgreementImportResult>> {
  const formData = new FormData()
  formData.append('file', file)
  const uploadHeaders: Record<string, string> = await getAuthHeaders()
  delete uploadHeaders['Content-Type']
  const response = await fetch(
    `${API_BASE}/safety/safety-target-agreements/import`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  revalidatePath('/safety/target-performance')
  return response.json()
}

export async function downloadDutyAssessmentImportTemplate(
  year: number,
  quarter: number
): Promise<void> {
  await downloadExcel(
    `/safety/safety-duty-assessments/import-template?year=${year}&quarter=${quarter}`,
    `责任制考核导入模板-${year}-Q${quarter}.xlsx`
  )
}

export async function importDutyAssessmentResults(
  file: File,
  year: number,
  quarter: number
): Promise<ApiResponse<SafetyDutyAssessmentImportResult>> {
  const formData = new FormData()
  formData.append('file', file)
  const uploadHeaders: Record<string, string> = await getAuthHeaders()
  delete uploadHeaders['Content-Type']
  const response = await fetch(
    `${API_BASE}/safety/safety-duty-assessments/import?year=${year}&quarter=${quarter}`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  revalidatePath('/safety/target-performance')
  return response.json()
}

// ══════════════════════════════════════════════════════════════
// 安全设施台账（洗眼器/气体检测仪/防护设施等）
// ══════════════════════════════════════════════════════════════

type SafetyFacilityItem = components['schemas']['SafetyFacilityResponse']
type SafetyFacilityListData = components['schemas']['SafetyFacilityListResponse']
type SafetyFacilityStatsData = components['schemas']['SafetyFacilityStatsResponse']
type SafetyFacilityChecklistData =
  components['schemas']['SafetyFacilityChecklistResponse']
type SafetyFacilityInspectionItem =
  components['schemas']['SafetyFacilityInspectionResponse']
type SafetyFacilityInspectionListData =
  components['schemas']['SafetyFacilityInspectionListResponse']
type SafetyFacilityCreateInput = components['schemas']['SafetyFacilityCreate']
type SafetyFacilityUpdateInput = components['schemas']['SafetyFacilityUpdate']
type SafetyFacilityInspectionSubmitInput =
  components['schemas']['CreateSafetyFacilityInspectionRequest']

export type {
  SafetyFacilityItem,
  SafetyFacilityListData,
  SafetyFacilityStatsData,
  SafetyFacilityChecklistData,
  SafetyFacilityInspectionItem,
  SafetyFacilityInspectionListData,
  SafetyFacilityCreateInput,
  SafetyFacilityUpdateInput,
  SafetyFacilityInspectionSubmitInput,
}

export interface SafetyFacilityQueryParams {
  page?: number
  page_size?: number
  category?: string
  department?: string
  status?: string
  expiry_status?: string
  keyword?: string
}

export async function getSafetyFacilities(
  params: SafetyFacilityQueryParams = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.category) searchParams.set('category', params.category)
  if (params.department) searchParams.set('department', params.department)
  if (params.status) searchParams.set('status', params.status)
  if (params.expiry_status) {
    searchParams.set('expiry_status', params.expiry_status)
  }
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<SafetyFacilityListData>(
    `/safety/safety-facilities${queryString ? `?${queryString}` : ''}`
  )
}

export async function getSafetyFacilityStats() {
  return fetchApi<SafetyFacilityStatsData>('/safety/safety-facilities/stats')
}

export async function getSafetyFacilityChecklist(category: string) {
  return fetchApi<SafetyFacilityChecklistData>(
    `/safety/safety-facilities/checklist?category=${encodeURIComponent(category)}`
  )
}

export async function getSafetyFacility(id: string) {
  return fetchApi<SafetyFacilityItem>(`/safety/safety-facilities/${id}`)
}

export async function createSafetyFacility(data: SafetyFacilityCreateInput) {
  const response = await fetchApi<SafetyFacilityItem>(
    '/safety/safety-facilities',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/facilities')
  return response
}

export async function updateSafetyFacility(
  id: string,
  data: SafetyFacilityUpdateInput
) {
  const response = await fetchApi<SafetyFacilityItem>(
    `/safety/safety-facilities/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/facilities')
  return response
}

export async function deleteSafetyFacility(id: string) {
  const response = await fetchApi<null>(`/safety/safety-facilities/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/facilities')
  return response
}

export async function submitSafetyFacilityInspection(
  facilityId: string,
  data: SafetyFacilityInspectionSubmitInput
) {
  const response = await fetchApi<SafetyFacilityInspectionItem>(
    `/safety/safety-facilities/${facilityId}/inspections`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/facilities')
  return response
}

export async function getSafetyFacilityInspections(
  params: {
    page?: number
    page_size?: number
    facility_id?: string
    result?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.facility_id) {
    searchParams.set('facility_id', params.facility_id)
  }
  if (params.result) searchParams.set('result', params.result)

  const queryString = searchParams.toString()
  return fetchApi<SafetyFacilityInspectionListData>(
    `/safety/safety-facility-inspections${queryString ? `?${queryString}` : ''}`
  )
}

// ══════════════════════════════════════════════════════════════
// 危化品与 MSDS
// ══════════════════════════════════════════════════════════════

type HazardousChemicalItem = components['schemas']['HazardousChemicalResponse']
type HazardousChemicalListData =
  components['schemas']['HazardousChemicalListResponse']
type HazchemStatsData = components['schemas']['HazchemStatsResponse']
type ChemicalInventoryItem = components['schemas']['ChemicalInventoryResponse']
type ChemicalInventoryListData =
  components['schemas']['ChemicalInventoryListResponse']
type HazardousChemicalCreateInput =
  components['schemas']['HazardousChemicalCreate']
type HazardousChemicalUpdateInput =
  components['schemas']['HazardousChemicalUpdate']
type ChemicalInventoryCreateInput =
  components['schemas']['ChemicalInventoryCreate']
type ChemicalInventoryUpdateInput =
  components['schemas']['ChemicalInventoryUpdate']
type ChemicalMsdsFileItem = components['schemas']['ChemicalMsdsFileItem']
type ChemicalMsdsFileListData =
  components['schemas']['ChemicalMsdsFileListResponse']
type ChemicalMsdsUploadData =
  components['schemas']['ChemicalMsdsUploadResponse']
type MsdsExtractionSuggestion =
  components['schemas']['MsdsExtractionSuggestion']

export type {
  HazardousChemicalItem,
  HazardousChemicalListData,
  HazchemStatsData,
  ChemicalInventoryItem,
  ChemicalInventoryListData,
  HazardousChemicalCreateInput,
  HazardousChemicalUpdateInput,
  ChemicalInventoryCreateInput,
  ChemicalInventoryUpdateInput,
  ChemicalMsdsFileItem,
  ChemicalMsdsFileListData,
  ChemicalMsdsUploadData,
  MsdsExtractionSuggestion,
}

export async function getHazardousChemicals(
  params: {
    page?: number
    page_size?: number
    category?: string
    keyword?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.category) searchParams.set('category', params.category)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<HazardousChemicalListData>(
    `/safety/hazardous-chemicals${queryString ? `?${queryString}` : ''}`
  )
}

export async function getHazchemStats() {
  return fetchApi<HazchemStatsData>('/safety/hazardous-chemicals/stats')
}

export async function getOverLimitChemicals(limit = 10) {
  return fetchApi<ChemicalInventoryItem[]>(
    `/safety/hazardous-chemicals/over-limit?limit=${limit}`
  )
}

export async function createHazardousChemical(
  data: HazardousChemicalCreateInput
) {
  const response = await fetchApi<HazardousChemicalItem>(
    '/safety/hazardous-chemicals',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazchem')
  return response
}

export async function updateHazardousChemical(
  id: string,
  data: HazardousChemicalUpdateInput
) {
  const response = await fetchApi<HazardousChemicalItem>(
    `/safety/hazardous-chemicals/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazchem')
  return response
}

export async function deleteHazardousChemical(id: string) {
  const response = await fetchApi<null>(`/safety/hazardous-chemicals/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/hazchem')
  return response
}

export async function uploadChemicalMsdsFile(chemicalId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  // 上传必须剥离 JSON Content-Type，让浏览器自动生成 multipart boundary
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/hazardous-chemicals/${chemicalId}/msds-files`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  if (!response.ok) {
    const text = await response.text()
    return { code: response.status, message: text } as ApiResponse<ChemicalMsdsUploadData>
  }
  const data = (await response.json()) as ApiResponse<ChemicalMsdsUploadData>
  revalidatePath('/safety/hazchem')
  return data
}

export async function listChemicalMsdsFiles(chemicalId: string) {
  return fetchApi<ChemicalMsdsFileListData>(
    `/safety/hazardous-chemicals/${chemicalId}/msds-files`
  )
}

export async function deleteChemicalMsdsFile(chemicalId: string, fileId: string) {
  const response = await fetchApi<null>(
    `/safety/hazardous-chemicals/${chemicalId}/msds-files/${fileId}`,
    { method: 'DELETE' }
  )
  revalidatePath('/safety/hazchem')
  return response
}

export async function reextractChemicalMsdsFile(chemicalId: string, fileId: string) {
  return fetchApi<ChemicalMsdsUploadData>(
    `/safety/hazardous-chemicals/${chemicalId}/msds-files/${fileId}/extract`,
    { method: 'POST' }
  )
}

/**
 * 拉取 MSDS 附件字节（preview=true 返回浏览器可呈现内容，office 已转 PDF）。
 *
 * Server Action 在服务端执行，无法返回 blob URL 或操作 DOM，因此返回
 * base64 与 MIME，由客户端组件自行组装 Blob/预览地址。
 */
export async function fetchChemicalMsdsBytes(
  chemicalId: string,
  fileId: string,
  preview: boolean
): Promise<{ base64: string; contentType: string }> {
  const headers = await getAuthHeaders()
  const response = await fetch(
    `${API_BASE}/safety/hazardous-chemicals/${chemicalId}/msds-files/${fileId}` +
      (preview ? '/preview' : '/content'),
    { headers }
  )
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`MSDS 读取失败 (${response.status}): ${text}`)
  }
  const buffer = Buffer.from(await response.arrayBuffer())
  return {
    base64: buffer.toString('base64'),
    contentType: response.headers.get('content-type') || 'application/octet-stream',
  }
}

/**
 * 拉取用于下载的 MSDS 原始字节（Server Action，返回 base64）。
 * 客户端拿到后自行触发浏览器下载。
 */
export async function fetchChemicalMsdsDownloadBytes(
  chemicalId: string,
  fileId: string
): Promise<{ base64: string; contentType: string }> {
  return fetchChemicalMsdsBytes(chemicalId, fileId, false)
}

export async function getChemicalInventories(
  params: {
    page?: number
    page_size?: number
    workshop?: string
    chemical_id?: string
    over_limit_only?: boolean
    keyword?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.workshop) searchParams.set('workshop', params.workshop)
  if (params.chemical_id) searchParams.set('chemical_id', params.chemical_id)
  if (params.over_limit_only) {
    searchParams.set('over_limit_only', 'true')
  }
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<ChemicalInventoryListData>(
    `/safety/chemical-inventories${queryString ? `?${queryString}` : ''}`
  )
}

export async function createChemicalInventory(
  data: ChemicalInventoryCreateInput
) {
  const response = await fetchApi<ChemicalInventoryItem>(
    '/safety/chemical-inventories',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazchem')
  return response
}

export async function updateChemicalInventory(
  id: string,
  data: ChemicalInventoryUpdateInput
) {
  const response = await fetchApi<ChemicalInventoryItem>(
    `/safety/chemical-inventories/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/hazchem')
  return response
}

export async function deleteChemicalInventory(id: string) {
  const response = await fetchApi<null>(`/safety/chemical-inventories/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/hazchem')
  return response
}

// ══════════════════════════════════════════════════════════════
// 应急管理（预案 / 演练 / 物资）
// ══════════════════════════════════════════════════════════════

type EmergencyPlanItem = components['schemas']['EmergencyPlanResponse']
type EmergencyPlanListData = components['schemas']['EmergencyPlanListResponse']
type EmergencyDrillItem = components['schemas']['EmergencyDrillResponse']
type EmergencyDrillListData = components['schemas']['EmergencyDrillListResponse']
type EmergencySupplyItem = components['schemas']['EmergencySupplyResponse']
type EmergencySupplyListData =
  components['schemas']['EmergencySupplyListResponse']
type EmergencyMgmtStatsData = components['schemas']['EmergencyMgmtStatsResponse']
type EmergencyPlanCreateInput = components['schemas']['EmergencyPlanCreate']
type EmergencyPlanUpdateInput = components['schemas']['EmergencyPlanUpdate']
type EmergencyDrillCreateInput = components['schemas']['EmergencyDrillCreate']
type EmergencyDrillUpdateInput = components['schemas']['EmergencyDrillUpdate']
type EmergencySupplyCreateInput = components['schemas']['EmergencySupplyCreate']
type EmergencySupplyUpdateInput = components['schemas']['EmergencySupplyUpdate']

export type {
  EmergencyPlanItem,
  EmergencyPlanListData,
  EmergencyDrillItem,
  EmergencyDrillListData,
  EmergencySupplyItem,
  EmergencySupplyListData,
  EmergencyMgmtStatsData,
  EmergencyPlanCreateInput,
  EmergencyPlanUpdateInput,
  EmergencyDrillCreateInput,
  EmergencyDrillUpdateInput,
  EmergencySupplyCreateInput,
  EmergencySupplyUpdateInput,
}

export async function getEmergencyPlans(
  params: {
    page?: number
    page_size?: number
    plan_type?: string
    status?: string
    keyword?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.plan_type) searchParams.set('plan_type', params.plan_type)
  if (params.status) searchParams.set('status', params.status)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<EmergencyPlanListData>(
    `/safety/emergency-plans${queryString ? `?${queryString}` : ''}`
  )
}

export async function getEmergencyMgmtStats() {
  return fetchApi<EmergencyMgmtStatsData>('/safety/emergency-mgmt/stats')
}

export async function createEmergencyPlan(data: EmergencyPlanCreateInput) {
  const response = await fetchApi<EmergencyPlanItem>(
    '/safety/emergency-plans',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function updateEmergencyPlan(
  id: string,
  data: EmergencyPlanUpdateInput
) {
  const response = await fetchApi<EmergencyPlanItem>(
    `/safety/emergency-plans/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function deleteEmergencyPlan(id: string) {
  const response = await fetchApi<null>(`/safety/emergency-plans/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function uploadEmergencyPlanFile(id: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  // 上传必须剥离 JSON Content-Type，让浏览器自动生成 multipart boundary
  const authHeaders = await getAuthHeaders()
  const { 'Content-Type': _, ...uploadHeaders } = authHeaders
  const response = await fetch(
    `${API_BASE}/safety/emergency-plans/${id}/file`,
    { method: 'POST', headers: uploadHeaders, body: formData }
  )
  if (!response.ok) {
    const text = await response.text()
    return { code: response.status, message: text } as ApiResponse<EmergencyPlanItem>
  }
  const data = (await response.json()) as ApiResponse<EmergencyPlanItem>
  revalidatePath('/safety/emergency-mgmt')
  return data
}

export async function downloadEmergencyPlanFile(
  id: string,
  fileName?: string
): Promise<void> {
  const headers = await getAuthHeaders()
  const response = await fetch(
    `${API_BASE}/safety/emergency-plans/${id}/file`,
    { headers }
  )
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`预案下载失败 (${response.status}): ${text}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName || '应急预案'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function getEmergencyDrills(
  params: {
    page?: number
    page_size?: number
    drill_type?: string
    status?: string
    year?: number
    keyword?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.drill_type) searchParams.set('drill_type', params.drill_type)
  if (params.status) searchParams.set('status', params.status)
  if (params.year) searchParams.set('year', String(params.year))
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<EmergencyDrillListData>(
    `/safety/emergency-drills${queryString ? `?${queryString}` : ''}`
  )
}

export async function createEmergencyDrill(data: EmergencyDrillCreateInput) {
  const response = await fetchApi<EmergencyDrillItem>(
    '/safety/emergency-drills',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function updateEmergencyDrill(
  id: string,
  data: EmergencyDrillUpdateInput
) {
  const response = await fetchApi<EmergencyDrillItem>(
    `/safety/emergency-drills/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function deleteEmergencyDrill(id: string) {
  const response = await fetchApi<null>(`/safety/emergency-drills/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function getEmergencySupplies(
  params: {
    page?: number
    page_size?: number
    category?: string
    status?: string
    department?: string
    keyword?: string
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) {
    searchParams.set('page_size', String(params.page_size))
  }
  if (params.category) searchParams.set('category', params.category)
  if (params.status) searchParams.set('status', params.status)
  if (params.department) searchParams.set('department', params.department)
  if (params.keyword) searchParams.set('keyword', params.keyword)

  const queryString = searchParams.toString()
  return fetchApi<EmergencySupplyListData>(
    `/safety/emergency-supplies${queryString ? `?${queryString}` : ''}`
  )
}

export async function createEmergencySupply(data: EmergencySupplyCreateInput) {
  const response = await fetchApi<EmergencySupplyItem>(
    '/safety/emergency-supplies',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function updateEmergencySupply(
  id: string,
  data: EmergencySupplyUpdateInput
) {
  const response = await fetchApi<EmergencySupplyItem>(
    `/safety/emergency-supplies/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/safety/emergency-mgmt')
  return response
}

export async function deleteEmergencySupply(id: string) {
  const response = await fetchApi<null>(`/safety/emergency-supplies/${id}`, {
    method: 'DELETE',
  })
  revalidatePath('/safety/emergency-mgmt')
  return response
}
