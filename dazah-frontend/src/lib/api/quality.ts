import type {
  DeviationAiSession,
  FeishuValidationItem,
  QualityFeishuAppSettingsDetail,
  QualityFeishuEntityFieldMappingBundle,
  QualityFeishuEntitySettingItem,
  QualityFeishuTableOption,
  QualityPullSyncResult,
  QualitySyncConflictItem,
  CapaDetail,
  CapaListItem,
  DeviationDetail,
  DeviationListItem,
  DepartmentContact,
  FeishuCapaLedgerItem,
  FeishuCapaPlanTrackItem,
  FeishuDeviationLedgerRecordItem,
  FeishuDeviationReportRecordItem,
  DeviationInvestigationPushRecordItem,
  ChangeListItem,
  ChangeDetail,
  ChangeActionPlanListItem,
  QualityAiAnalysisLog,
  DeviationDashboardStats,
  CapaDashboardStats,
  ChangeDashboardStats,
  ValidationDashboardStats,
  QualityFeishuSettingsTestResult,
} from '@/types/quality'

type QueryValue = string | number | boolean | readonly string[] | null | undefined
type QueryParams = Record<string, QueryValue>
type ListResult<T> = { items: T[]; total: number; page?: number; page_size?: number }

async function getApiErrorMessage(response: Response): Promise<string> {
  const fallback = `请求失败: ${response.status} ${response.statusText}`
  const errorBody = await response.text().catch(() => '')
  if (!errorBody) return fallback
  try {
    const errorJson = JSON.parse(errorBody)
    if (typeof errorJson.detail === 'string' && errorJson.detail) {
      return errorJson.detail
    }
    if (typeof errorJson.message === 'string' && errorJson.message) {
      return errorJson.message
    }
  } catch {}
  return fallback
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(await getApiErrorMessage(response))
  }
  const data = await response.json()
  if (
    data &&
    typeof data === 'object' &&
    Array.isArray(data.data) &&
    data.meta &&
    typeof data.meta === 'object'
  ) {
    return {
      items: data.data,
      total: data.meta.total ?? data.data.length,
      page: data.meta.page,
      page_size: data.meta.page_size,
    } as T
  }
  return data.data ?? data
}

export async function fetchModuleInfo(): Promise<{ code: string; name: string; description: string }> {
  return apiFetch(`/api/v1/quality/`)
}

// CAPA functions
export async function fetchCapa(id: string): Promise<CapaDetail> {
  return apiFetch<CapaDetail>(`/api/v1/quality/capas/${id}`)
}

// Deviation functions
export async function fetchDeviations(params?: {
  level?: string
  department?: string
  keyword?: string
  page?: number
  page_size?: number
  status?: string
}): Promise<ListResult<DeviationListItem>> {
  return apiFetch<ListResult<DeviationListItem>>(withQuery('/api/v1/quality/deviations', params))
}

export async function fetchDeviation(id: string): Promise<DeviationDetail> {
  return apiFetch<DeviationDetail>(`/api/v1/quality/deviations/${id}`)
}

export async function fetchCapas(params?: {
  source?: string
  category?: string
  keyword?: string
  page?: number
  page_size?: number
  status?: string
}): Promise<ListResult<CapaListItem>> {
  return apiFetch<ListResult<CapaListItem>>(withQuery('/api/v1/quality/capas', params))
}

export async function fetchDepartmentContacts(page: number = 1, page_size: number = 1000): Promise<DepartmentContact[]> {
  const result = await apiFetch<ListResult<DepartmentContact> | DepartmentContact[]>(
    withQuery('/api/v1/quality/department-contacts', { page, page_size })
  )
  return Array.isArray(result) ? result : result.items
}

function withQuery(path: string, params?: QueryParams) {
  const search = new URLSearchParams()
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  })
  const query = search.toString()
  return query ? `${path}?${query}` : path
}

async function downloadBlob(path: string, params?: QueryParams): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(withQuery(path, params))
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const disposition = response.headers.get('content-disposition') || ''
  const filenameMatch = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i)
  const filename = filenameMatch ? decodeURIComponent(filenameMatch[1]) : 'quality-export.xlsx'
  return { blob: await response.blob(), filename }
}

export async function fetchFeishuCapas(params?: QueryParams): Promise<ListResult<FeishuCapaLedgerItem>> {
  const result = await apiFetch<ListResult<FeishuCapaLedgerItem> | FeishuCapaLedgerItem[]>(withQuery('/api/v1/quality/feishu/capas', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchFeishuCapaPlanTracks(params?: QueryParams): Promise<ListResult<FeishuCapaPlanTrackItem>> {
  const result = await apiFetch<ListResult<FeishuCapaPlanTrackItem> | FeishuCapaPlanTrackItem[]>(withQuery('/api/v1/quality/feishu/capa-plan-tracks', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchFeishuDeviationLedgerRecords(params?: QueryParams): Promise<ListResult<FeishuDeviationLedgerRecordItem>> {
  const result = await apiFetch<ListResult<FeishuDeviationLedgerRecordItem> | FeishuDeviationLedgerRecordItem[]>(withQuery('/api/v1/quality/deviation-ledger-records', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchFeishuDeviationReportRecords(params?: QueryParams): Promise<ListResult<FeishuDeviationReportRecordItem>> {
  const result = await apiFetch<ListResult<FeishuDeviationReportRecordItem> | FeishuDeviationReportRecordItem[]>(withQuery('/api/v1/quality/deviation-report-records', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchDeviationReportRecords(params?: QueryParams) {
  return fetchFeishuDeviationReportRecords(params)
}

export async function fetchDeviationInvestigationPushRecords(params?: QueryParams): Promise<ListResult<DeviationInvestigationPushRecordItem>> {
  const result = await apiFetch<ListResult<DeviationInvestigationPushRecordItem> | DeviationInvestigationPushRecordItem[]>(withQuery('/api/v1/quality/deviation-investigation-push-records', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchChanges(params?: QueryParams): Promise<ListResult<ChangeListItem>> {
  const result = await apiFetch<ListResult<ChangeListItem> | ChangeListItem[]>(withQuery('/api/v1/quality/changes', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchChange(id: string): Promise<ChangeDetail> {
  return apiFetch<ChangeDetail>(`/api/v1/quality/changes/${id}`)
}

export async function fetchNextChangeCode(): Promise<{ change_code: string }> {
  return apiFetch<{ change_code: string }>('/api/v1/quality/changes/next-code')
}

export async function fetchChangeActionPlans(params?: QueryParams): Promise<ListResult<ChangeActionPlanListItem>> {
  const result = await apiFetch<ListResult<ChangeActionPlanListItem> | ChangeActionPlanListItem[]>(withQuery('/api/v1/quality/change-action-plans', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchChangeActionPlansByChange(changeId: string): Promise<ChangeActionPlanListItem[]> {
  const result = await apiFetch<ListResult<ChangeActionPlanListItem> | ChangeActionPlanListItem[]>(`/api/v1/quality/changes/${changeId}/action-plans`)
  return Array.isArray(result) ? result : result.items || []
}

export async function fetchDeviationAiSession(deviationId: string): Promise<DeviationAiSession> {
  return apiFetch<DeviationAiSession>(`/api/v1/quality/ai/deviations/${deviationId}/session`)
}

export async function fetchQualityAiLogs(params?: QueryParams): Promise<ListResult<QualityAiAnalysisLog>> {
  const result = await apiFetch<ListResult<QualityAiAnalysisLog> | QualityAiAnalysisLog[]>(withQuery('/api/v1/quality/ai/logs', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchQualityFeishuAppSettings(): Promise<QualityFeishuAppSettingsDetail> {
  return apiFetch<QualityFeishuAppSettingsDetail>('/api/v1/quality/feishu-settings/app')
}

export async function fetchQualityFeishuEntitySettings(): Promise<QualityFeishuEntitySettingItem[]> {
  return apiFetch<QualityFeishuEntitySettingItem[]>('/api/v1/quality/feishu-settings/entities')
}

export async function fetchQualityFeishuEntityTables(
  entityCode: string,
  appToken?: string,
  tableId?: string
): Promise<QualityFeishuTableOption[]> {
  return apiFetch<QualityFeishuTableOption[]>(
    withQuery(`/api/v1/quality/feishu-settings/entities/${entityCode}/tables`, {
      app_token: appToken,
      table_id: tableId,
    })
  )
}

export async function fetchQualityFeishuEntityFieldMappingBundle(entityCode: string, params?: QueryParams): Promise<QualityFeishuEntityFieldMappingBundle> {
  return apiFetch<QualityFeishuEntityFieldMappingBundle>(withQuery(`/api/v1/quality/feishu-settings/entities/${entityCode}/field-mapping`, params))
}

export async function fetchQualitySyncConflicts(params?: QueryParams): Promise<{ items: QualitySyncConflictItem[]; total: number }> {
  const result = await apiFetch<{ items: QualitySyncConflictItem[]; total: number } | QualitySyncConflictItem[]>(
    withQuery('/api/v1/quality/feishu-sync/conflicts', params)
  )
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchFeishuValidations(params?: QueryParams): Promise<{ items: FeishuValidationItem[]; total: number }> {
  const result = await apiFetch<{ items: FeishuValidationItem[]; total: number } | FeishuValidationItem[]>(withQuery('/api/v1/quality/feishu/validations', params))
  return Array.isArray(result) ? { items: result, total: result.length } : result
}

export async function fetchDeviationStatistics(): Promise<DeviationDashboardStats> {
  return apiFetch<DeviationDashboardStats>('/api/v1/quality/statistics/deviations')
}

export async function fetchCapaStatistics(): Promise<CapaDashboardStats> {
  return apiFetch<CapaDashboardStats>('/api/v1/quality/statistics/capas')
}

export async function fetchChangeDashboardStats(): Promise<ChangeDashboardStats> {
  return apiFetch<ChangeDashboardStats>('/api/v1/quality/statistics/changes')
}

export async function fetchValidationDashboardStats(): Promise<ValidationDashboardStats> {
  return apiFetch<ValidationDashboardStats>('/api/v1/quality/statistics/validations')
}

export async function exportFeishuDeviationLedgerRecords(params?: QueryParams): Promise<{ blob: Blob; filename: string }> {
  return downloadBlob('/api/v1/quality/deviation-ledger-records/export', params)
}

export async function exportFeishuDeviationLedgerRecord(recordId: string): Promise<{ blob: Blob; filename: string }> {
  return downloadBlob(`/api/v1/quality/deviation-ledger-records/${recordId}/export`)
}

export async function exportChangeLedger(params?: QueryParams): Promise<{ blob: Blob; filename: string }> {
  return downloadBlob('/api/v1/quality/changes/export', params)
}

export function formatQualitySyncSummary(result: Partial<QualityPullSyncResult> | string | null | undefined) {
  if (!result) return '同步完成'
  if (typeof result === 'string') return result
  const synced = result.synced ?? 0
  const failed = result.failed ?? 0
  const conflicts = result.conflicts ?? 0
  return `同步 ${synced} 条，失败 ${failed} 条，冲突 ${conflicts} 条`
}

export function formatQualityFeishuTestSummary(result: Partial<QualityFeishuSettingsTestResult> | null | undefined) {
  if (!result) return ''
  return result.message || (result.success ? '连接成功' : '连接失败')
}
