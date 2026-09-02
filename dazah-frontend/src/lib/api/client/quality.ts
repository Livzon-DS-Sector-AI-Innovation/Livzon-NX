import type {
  CapaDashboardStats,
  DeviationAiSession,
  DeviationWorkbenchReportDetail,
  DeviationWorkbenchReportListItem,
  DeviationWorkbenchSettings,
  HistoricalDeviationDetail,
  HistoricalDeviationListItem,
  CapaPlanTrackItem,
  ChangeDashboardStats,
  ChangeActionPlanDetail,
  ChangeActionPlanListItem,
  ChangeActionPlanPersonOption,
  DepartmentContact,
  DeviationDashboardStats,
  DeviationInvestigationPushRecordItem,
  FeishuDeviationInvestigationPushRecordItem,
  FeishuDeviationReportRecordItem,
  FeishuValidationItem,
  FeishuValidationPullResult,
  QcValidationFieldsResult,
  QcValidationRecordsResult,
  QcValidationYearStatus,
  InspectionFeishuFieldMeta,
  InspectionFeishuFieldsResult,
  QualityPullSyncResult,
  QualitySyncConflictItem,
  QualityFeishuAppSettingsDetail,
  QualityFeishuEntityFieldMappingBundle,
  QualityFeishuEntitySettingItem,
  QualityFeishuSettingsTestResult,
  QualityFeishuTableOption,
  DeviationReportRecordItem,
  RelatedCapaListItem,
  ValidationDashboardStats,
  ValidationFilters,
  ValidationExecutionItem,
  ValidationListItem,
  FeishuCapaLedgerItem,
  FeishuCapaPlanTrackItem,
  FeishuListResponse,
  ComplaintLedgerItem,
  ReturnApplicationItem,
  ReturnLedgerItem,
  CapaDetail,
  CapaListItem,
  ProductQualityStandardItem,
  ProductQualityProduct,
  SupplierDashboardStats,
  SupplierQualificationItem,
  DocumentDepartmentItem,
  DocumentEntryItem,
  OosOotReportRecordItem,
  OosOotInvestigationPushRecordItem,
} from '@/types/quality'
import type { QualityInspectionDashboardApiResponse } from '@/types/quality-inspection-dashboard'
/**
 * 产品质量客户标准 - 客户端只读 API (GET)
 * 使用相对路径 /api/v1/...，由 proxy.ts 转发到后端
 */

export async function fetchProductQualityProducts(): Promise<ProductQualityProduct[]> {
  const res = await fetch('/api/v1/quality/product-quality-standards')
  if (!res.ok) throw new Error(`获取产品列表失败: ${res.statusText}`)
  const json = await res.json()
  return json.data ?? []
}

export async function fetchProductQualityStandards(
  productCode: string,
  params?: { keyword?: string; page?: string | number; page_size?: string | number }
): Promise<{ items: ProductQualityStandardItem[]; total: number }> {
  const queryParts: string[] = []
  if (params) {
    if (params.keyword) queryParts.push(`keyword=${encodeURIComponent(params.keyword)}`)
    if (params.page) queryParts.push(`page=${encodeURIComponent(String(params.page))}`)
    if (params.page_size) queryParts.push(`page_size=${encodeURIComponent(String(params.page_size))}`)
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`/api/v1/quality/product-quality-standards/${productCode}${query}`)
  if (!res.ok) throw new Error(`获取产品质量标准失败: ${res.statusText}`)
  const json = await res.json()
  return { items: json.data ?? [], total: json.meta?.total ?? 0 }
}

/**
 * 供应商资质 - 客户端只读 API (GET)
 */

export async function fetchSupplierQualifications(params?: {
  keyword?: string
  supplier_name?: string
  material_type?: string
  qualification_name?: string
  is_completed?: boolean
  page?: number
  page_size?: number
}): Promise<{ items: SupplierQualificationItem[]; total: number }> {
  const queryParts: string[] = []
  if (params) {
    if (params.keyword) queryParts.push(`keyword=${encodeURIComponent(params.keyword)}`)
    if (params.supplier_name) queryParts.push(`supplier_name=${encodeURIComponent(params.supplier_name)}`)
    if (params.material_type) queryParts.push(`material_type=${encodeURIComponent(params.material_type)}`)
    if (params.qualification_name) queryParts.push(`qualification_name=${encodeURIComponent(params.qualification_name)}`)
    if (params.is_completed !== undefined) queryParts.push(`is_completed=${String(params.is_completed)}`)
    if (params.page) queryParts.push(`page=${encodeURIComponent(String(params.page))}`)
    if (params.page_size) queryParts.push(`page_size=${encodeURIComponent(String(params.page_size))}`)
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`/api/v1/quality/supplier-qualification${query}`)
  if (!res.ok) throw new Error(`获取供应商资质列表失败: ${res.statusText}`)
  const json = await res.json()
  return { items: json.data ?? [], total: json.meta?.total ?? 0 }
}

/**
 * 供应商统计 - 客户端只读 API (GET)
 */

export async function fetchSupplierStatistics(): Promise<SupplierDashboardStats> {
  const res = await fetch('/api/v1/quality/statistics/suppliers')
  if (!res.ok) throw new Error(`获取供应商统计失败: ${res.statusText}`)
  const json = await res.json()
  return json.data
}

/**
 * 成品检验仪表盘 - 客户端只读 API (GET)
 */

export async function fetchMpaDashboard(
  entityCode = 'qc_finished_internal'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/mpa?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_high_spec' ? '霉酚酸（高规）' : '霉酚酸（内控）'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchMvtDashboard(): Promise<QualityInspectionDashboardApiResponse> {
  const res = await fetch('/api/v1/quality/inspection-dashboard/mvt')
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>

  return {
    data: json.data ?? {
      source_entity_code: 'qc_finished_mvt',
      source_label: '美伐他汀（DMF）',
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: 'qc_finished_mvt',
        source_label: '美伐他汀（DMF）',
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchLftDashboard(
  entityCode = 'qc_finished_lft_ep'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/lft?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_lft_usp' ? '洛伐他汀（USP）' : '洛伐他汀（EP）'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchDlsDashboard(
  entityCode = 'qc_finished_dor_gb'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/dls?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_dor_vet' ? '多拉菌素（兽药）' : '多拉菌素（GB）'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchLkmsDashboard(
  entityCode = 'qc_finished_lkms_vet'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/lkms?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: '林可霉素（兽药）',
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: '林可霉素（兽药）',
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchFormulationsDashboard(
  entityCode = 'qc_finished_flu_powder'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/formulations?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_fen_powder' ? '5%芬苯达唑粉' : '2%氟苯尼考预混剂'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchBbasDashboard(
  entityCode = 'qc_finished_fcc14'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/bbas?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_bbas_hanguang_k1' ? '汉光（K1）' : 'FCC14'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchTryptophanDashboard(
  entityCode = 'qc_finished_trp_granule'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/tryptophan?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_trp_powder' ? '色氨酸粉末' : '色氨酸颗粒'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

export async function fetchWaterDashboard(
  entityCode = 'qc_finished_pure_water'
): Promise<QualityInspectionDashboardApiResponse> {
  const search = new URLSearchParams({ entity_code: entityCode }).toString()
  const res = await fetch(`/api/v1/quality/inspection-dashboard/water?${search}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status} ${res.statusText}`)

  const json = (await res.json()) as Partial<QualityInspectionDashboardApiResponse>
  const sourceLabel = entityCode === 'qc_finished_pure_water' ? '纯化水' : '纯化水等'

  return {
    data: json.data ?? {
      source_entity_code: entityCode,
      source_label: sourceLabel,
      charts: [],
      alerts: [],
      summary: {
        source_entity_code: entityCode,
        source_label: sourceLabel,
        total_records: 0,
        valid_record_count: 0,
        skipped_value_count: 0,
        alert_batch_count: 0,
        alert_metric_count: 0,
        first_notification_sent_count: 0,
        deduplicated_notification_count: 0,
        failed_notification_count: 0,
        unmapped_notification_count: 0,
      },
    },
    meta: {
      configured: json.meta?.configured !== false,
    },
  }
}

// ============ Core Quality APIs (migrated from lib/api/quality.ts) ============

// ---- Helpers ----

interface PaginatedItems<T> {
  items: T[]
  total: number
  page?: number
  page_size?: number
}

function parseError(response: Response): Promise<Error> {
  return response.text().then(text => {
    try {
      const json = JSON.parse(text)
      const detail = json.detail || json.message
      if (detail) return new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    } catch {}
    return new Error(`请求失败: ${response.status} ${response.statusText}`)
  })
}

function parseDownloadFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return utf8Match[1]
    }
  }
  const plainMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  return plainMatch?.[1] || fallback
}

async function fetchQualityFile(
  path: string,
  fallbackFilename: string
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(path)
  if (!response.ok) throw await parseError(response)
  const blob = await response.blob()
  const filename = parseDownloadFilename(
    response.headers.get('content-disposition'),
    fallbackFilename
  )
  return { blob, filename }
}

// ---- Statistics ----

export async function fetchDeviationStatistics(): Promise<DeviationDashboardStats> {
  const res = await fetch('/api/v1/quality/statistics/deviations')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchCapaStatistics(): Promise<CapaDashboardStats> {
  const res = await fetch('/api/v1/quality/statistics/capas')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchChangeDashboardStats(): Promise<ChangeDashboardStats> {
  const res = await fetch('/api/v1/quality/statistics/changes')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchValidationDashboardStats(): Promise<ValidationDashboardStats> {
  const res = await fetch('/api/v1/quality/statistics/validations')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchFeishuValidationDashboardStats(): Promise<ValidationDashboardStats> {
  const res = await fetch('/api/v1/quality/feishu/statistics/validations')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

// ---- CAPA ----

export async function fetchCapa(id: string): Promise<CapaDetail | null> {
  const res = await fetch(`/api/v1/quality/capas/${id}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? null
}

export async function fetchCapas(params?: {
  source?: string
  category?: string
  keyword?: string
  capa_code?: string
  affected_product?: string
  source_code?: string
  evaluation_result?: string
  closure_date_from?: string
  closure_date_to?: string
  department?: string
  qa_confirmer?: string
  page?: number
  page_size?: number
  status?: string
}): Promise<{ items: CapaListItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.status) searchParams.set('status', params.status)
  if (params?.source) searchParams.set('source', params.source)
  if (params?.category) searchParams.set('category', params.category)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.capa_code) searchParams.set('capa_code', params.capa_code)
  if (params?.affected_product) searchParams.set('affected_product', params.affected_product)
  if (params?.source_code) searchParams.set('source_code', params.source_code)
  if (params?.evaluation_result) searchParams.set('evaluation_result', params.evaluation_result)
  if (params?.closure_date_from) searchParams.set('closure_date_from', params.closure_date_from)
  if (params?.closure_date_to) searchParams.set('closure_date_to', params.closure_date_to)
  if (params?.department) searchParams.set('department', params.department)
  if (params?.qa_confirmer) searchParams.set('qa_confirmer', params.qa_confirmer)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/capas${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  const data = json.data
  if (Array.isArray(data)) {
    return { items: data as CapaListItem[], total: json.meta?.total || 0 }
  }
  const d = data || {}
  return { items: (d.items || []) as CapaListItem[], total: d.meta?.total || json.meta?.total || 0 }
}

export async function fetchCapaPlanTracks(params?: {
  capa_id?: string
  capa_code?: string
  progress?: string
  owner_name?: string
  reminder_status?: string
  due_date_from?: string
  due_date_to?: string
  page?: number
  page_size?: number
}): Promise<{ items: CapaPlanTrackItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.capa_id) searchParams.set('capa_id', params.capa_id)
  if (params?.capa_code) searchParams.set('capa_code', params.capa_code)
  if (params?.progress) searchParams.set('progress', params.progress)
  if (params?.owner_name) searchParams.set('owner_name', params.owner_name)
  if (params?.reminder_status) searchParams.set('reminder_status', params.reminder_status)
  if (params?.due_date_from) searchParams.set('due_date_from', params.due_date_from)
  if (params?.due_date_to) searchParams.set('due_date_to', params.due_date_to)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/capa-plan-tracks${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return { items: json.data || [], total: json.meta?.total || 0 }
}

// ---- Deviations ----

export async function fetchDeviations(params?: {
  level?: string
  department?: string
  keyword?: string
  deviation_code?: string
  product_keyword?: string
  has_occurred_before?: string
  is_closed?: string
  investigation_completed_from?: string
  investigation_completed_to?: string
  root_cause_keyword?: string
  corrective_actions_keyword?: string
  page?: number
  page_size?: number
  status?: string
}): Promise<{ items: any[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.status) searchParams.set('status', params.status)
  if (params?.level) searchParams.set('level', params.level)
  if (params?.department) searchParams.set('department', params.department)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.deviation_code) searchParams.set('deviation_code', params.deviation_code)
  if (params?.product_keyword) searchParams.set('product_keyword', params.product_keyword)
  if (params?.has_occurred_before) searchParams.set('has_occurred_before', params.has_occurred_before)
  if (params?.is_closed) searchParams.set('is_closed', params.is_closed)
  if (params?.investigation_completed_from) searchParams.set('investigation_completed_from', params.investigation_completed_from)
  if (params?.investigation_completed_to) searchParams.set('investigation_completed_to', params.investigation_completed_to)
  if (params?.root_cause_keyword) searchParams.set('root_cause_keyword', params.root_cause_keyword)
  if (params?.corrective_actions_keyword) searchParams.set('corrective_actions_keyword', params.corrective_actions_keyword)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/deviations${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  const data = json.data
  if (Array.isArray(data)) {
    return { items: data, total: json.meta?.total || 0 }
  }
  const d = data || {}
  return { items: d.items || [], total: d.meta?.total || json.meta?.total || 0 }
}

export async function fetchDeviation(id: string): Promise<any> {
  const res = await fetch(`/api/v1/quality/deviations/${id}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? null
}

export async function fetchFeishuDeviationReportRecords(params?: {
  page?: number
  page_size?: number
}): Promise<PaginatedItems<FeishuDeviationReportRecordItem>> {
  const searchParams = new URLSearchParams()
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/deviation-report-records${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return {
    items: (json.data || []).map((item: FeishuDeviationReportRecordItem) => ({
      ...item,
      source: 'feishu',
      record_id: item.record_id || item.feishu_base_record_id || item.id,
      product_name_batch: item.product_name_batch ?? item.product_batch ?? null,
    })),
    total: json.meta?.total || 0,
    page: params?.page,
    page_size: params?.page_size,
  }
}

export async function fetchDeviationReportRecords(params?: {
  page?: number
  page_size?: number
}): Promise<PaginatedItems<DeviationReportRecordItem>> {
  return fetchFeishuDeviationReportRecords(params)
}

export async function fetchFeishuDeviationReportRecord(recordId: string): Promise<FeishuDeviationReportRecordItem> {
  const res = await fetch(`/api/v1/quality/deviation-report-records/${recordId}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  const item = json.data as FeishuDeviationReportRecordItem
  return {
    ...item,
    source: 'feishu',
    record_id: item.record_id || item.feishu_base_record_id || item.id,
    product_name_batch: item.product_name_batch ?? item.product_batch ?? null,
  }
}

export async function fetchFeishuDeviationInvestigationPushRecords(params?: {
  deviation_id?: string
  deviation_code?: string
  push_round?: string
  submitter?: string
  department_head_result?: string
  qa_result?: string
  qa_head_result?: string
  submitted_at_from?: string
  submitted_at_to?: string
  page?: number
  page_size?: number
}): Promise<PaginatedItems<FeishuDeviationInvestigationPushRecordItem>> {
  const searchParams = new URLSearchParams()
  if (params?.deviation_id) searchParams.set('deviation_id', params.deviation_id)
  if (params?.deviation_code) searchParams.set('deviation_code', params.deviation_code)
  if (params?.push_round) searchParams.set('push_round', params.push_round)
  if (params?.submitter) searchParams.set('submitter', params.submitter)
  if (params?.department_head_result) searchParams.set('department_head_result', params.department_head_result)
  if (params?.qa_result) searchParams.set('qa_result', params.qa_result)
  if (params?.qa_head_result) searchParams.set('qa_head_result', params.qa_head_result)
  if (params?.submitted_at_from) searchParams.set('submitted_at_from', params.submitted_at_from)
  if (params?.submitted_at_to) searchParams.set('submitted_at_to', params.submitted_at_to)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/deviation-investigation-push-records${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return {
    items: (json.data || []).map((item: FeishuDeviationInvestigationPushRecordItem) => ({
      ...item,
      source: 'feishu',
      record_id: item.record_id || item.feishu_base_record_id || item.id,
    })),
    total: json.meta?.total || 0,
    page: params?.page,
    page_size: params?.page_size,
  }
}

export async function fetchDeviationInvestigationPushRecords(params?: {
  deviation_id?: string
  deviation_code?: string
  push_round?: string
  submitter?: string
  department_head_result?: string
  qa_result?: string
  qa_head_result?: string
  submitted_at_from?: string
  submitted_at_to?: string
  page?: number
  page_size?: number
}): Promise<PaginatedItems<DeviationInvestigationPushRecordItem>> {
  return fetchFeishuDeviationInvestigationPushRecords(params)
}

export async function fetchRelatedCapasForDeviation(
  deviationId: string
): Promise<RelatedCapaListItem[]> {
  const res = await fetch(`/api/v1/quality/deviations/${deviationId}/related-capas`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data || []
}

export async function fetchDeviationAiSession(deviationId: string): Promise<DeviationAiSession> {
  const res = await fetch(`/api/v1/quality/ai/deviations/${deviationId}/session`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

// ---- Changes ----

export async function fetchChanges(params?: {
  change_type?: string
  change_code?: string
  applicant_department?: string
  change_object?: string
  change_level?: string
  application_date_from?: string
  application_date_to?: string
  planned_approval_date_from?: string
  planned_approval_date_to?: string
  execution_date_from?: string
  execution_date_to?: string
  closure_date_from?: string
  closure_date_to?: string
  content_keyword?: string
  page?: number
  page_size?: number
}): Promise<{ items: any[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.change_type) searchParams.set('change_type', params.change_type)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  if (params?.change_code) searchParams.set('change_code', params.change_code)
  if (params?.applicant_department) searchParams.set('applicant_department', params.applicant_department)
  if (params?.change_object) searchParams.set('change_object', params.change_object)
  if (params?.change_level) searchParams.set('change_level', params.change_level)
  if (params?.application_date_from) searchParams.set('application_date_from', params.application_date_from)
  if (params?.application_date_to) searchParams.set('application_date_to', params.application_date_to)
  if (params?.planned_approval_date_from) searchParams.set('planned_approval_date_from', params.planned_approval_date_from)
  if (params?.planned_approval_date_to) searchParams.set('planned_approval_date_to', params.planned_approval_date_to)
  if (params?.execution_date_from) searchParams.set('execution_date_from', params.execution_date_from)
  if (params?.execution_date_to) searchParams.set('execution_date_to', params.execution_date_to)
  if (params?.closure_date_from) searchParams.set('closure_date_from', params.closure_date_from)
  if (params?.closure_date_to) searchParams.set('closure_date_to', params.closure_date_to)
  if (params?.content_keyword) searchParams.set('content_keyword', params.content_keyword)
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/changes${query ? `?${query}` : ''}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  const data = json.data
  if (Array.isArray(data)) {
    return { items: data, total: json.meta?.total || 0 }
  }
  const d = data || {}
  return { items: d.items || [], total: d.meta?.total || json.meta?.total || 0 }
}

export async function fetchChange(id: string): Promise<any> {
  const res = await fetch(`/api/v1/quality/changes/${id}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data || null
}

export async function fetchChangeActionPlans(params?: {
  change_id?: string
  change_code?: string
  project_name?: string
  related_work?: string
  owner_name?: string
  director_name?: string
  status?: string
  delay_flag?: string
  sync_status?: string
  deadline_date_from?: string
  deadline_date_to?: string
  page?: number
  page_size?: number
}): Promise<{ items: ChangeActionPlanListItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.change_id) searchParams.set('change_id', params.change_id)
  if (params?.change_code) searchParams.set('change_code', params.change_code)
  if (params?.project_name) searchParams.set('project_name', params.project_name)
  if (params?.related_work) searchParams.set('related_work', params.related_work)
  if (params?.owner_name) searchParams.set('owner_name', params.owner_name)
  if (params?.director_name) searchParams.set('director_name', params.director_name)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.delay_flag) searchParams.set('delay_flag', params.delay_flag)
  if (params?.sync_status) searchParams.set('sync_status', params.sync_status)
  if (params?.deadline_date_from) searchParams.set('deadline_date_from', params.deadline_date_from)
  if (params?.deadline_date_to) searchParams.set('deadline_date_to', params.deadline_date_to)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/change-action-plans${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return { items: json.data || [], total: json.meta?.total || 0 }
}

export async function fetchChangeActionPlansByChange(changeId: string): Promise<ChangeActionPlanListItem[]> {
  const res = await fetch(`/api/v1/quality/changes/${changeId}/action-plans`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data || []
}

export async function searchChangeActionPlanPersons(
  keyword: string,
  limit = 20,
): Promise<ChangeActionPlanPersonOption[]> {
  const searchParams = new URLSearchParams()
  if (keyword.trim()) searchParams.set('keyword', keyword.trim())
  searchParams.set('limit', String(limit))
  const res = await fetch(`/api/v1/quality/change-action-plans/person-options?${searchParams.toString()}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data || []
}

export async function fetchNextChangeCode(changeType: string = 'technical'): Promise<string> {
  const searchParams = new URLSearchParams()
  if (changeType) searchParams.set('change_type', changeType)
  const res = await fetch(`/api/v1/quality/changes/next-code?${searchParams.toString()}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data?.code || ''
}

// ---- Validations ----

export async function fetchValidations(
  params?: ValidationFilters
): Promise<{ items: ValidationListItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.validation_type) searchParams.set('validation_type', params.validation_type)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.record_code) searchParams.set('record_code', params.record_code)
  if (params?.department) searchParams.set('department', params.department)
  if (params?.planned_end_date_from) searchParams.set('planned_end_date_from', params.planned_end_date_from)
  if (params?.planned_end_date_to) searchParams.set('planned_end_date_to', params.planned_end_date_to)
  if (params?.drafted_at_from) searchParams.set('drafted_at_from', params.drafted_at_from)
  if (params?.drafted_at_to) searchParams.set('drafted_at_to', params.drafted_at_to)
  if (params?.year) searchParams.set('year', String(params.year))
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/feishu/validations${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  const items = (json.data ?? []) as ValidationListItem[]
  return { items, total: json.meta?.total ?? 0 }
}

export async function fetchValidationExecutions(
  validationType: string,
  params?: Omit<ValidationFilters, 'validation_type' | 'planned_end_date_from' | 'planned_end_date_to' | 'record_code'>
): Promise<{ items: ValidationExecutionItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (validationType) searchParams.set('validation_type', validationType)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.department) searchParams.set('department', params.department)
  if (params?.drafted_at_from) searchParams.set('drafted_at_from', params.drafted_at_from)
  if (params?.drafted_at_to) searchParams.set('drafted_at_to', params.drafted_at_to)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/feishu/validations${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  const items = (json.data ?? []) as ValidationExecutionItem[]
  return { items, total: json.meta?.total ?? 0 }
}

export async function fetchFeishuValidations(params?: {
  validation_type?: string
  status?: string
  keyword?: string
  record_code?: string
  department?: string
  page?: number
  page_size?: number
}): Promise<{ items: FeishuValidationItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.validation_type) searchParams.set('validation_type', params.validation_type)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.record_code) searchParams.set('record_code', params.record_code)
  if (params?.department) searchParams.set('department', params.department)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/feishu/validations${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  const items = (json.data ?? []) as FeishuValidationItem[]
  return { items, total: json.meta?.total ?? 0 }
}

// ---- QC验证（按年分表） ----

export async function fetchQcValidationYears(): Promise<QcValidationYearStatus[]> {
  const res = await fetch('/api/v1/quality/validation-qc/years')
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return (json.data?.years ?? []) as QcValidationYearStatus[]
}

export async function fetchQcValidationFields(
  year: number
): Promise<QcValidationFieldsResult> {
  const res = await fetch(`/api/v1/quality/validation-qc/fields?year=${year}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data as QcValidationFieldsResult
}

export async function fetchQcValidationRecords(
  year: number,
  params?: { keyword?: string; page?: number; page_size?: number }
): Promise<QcValidationRecordsResult> {
  const searchParams = new URLSearchParams()
  searchParams.set('year', String(year))
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const res = await fetch(`/api/v1/quality/validation-qc/records?${searchParams.toString()}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data as QcValidationRecordsResult
}

/** 批量生成 QC验证记录分享链接（record_id → 飞书记录链接），用于行级跳转 */
export async function fetchQcValidationShareLinks(
  year: number,
  recordIds: string[]
): Promise<Record<string, string>> {
  const res = await fetch(
    `/api/v1/quality/validation-qc/records/share-links?year=${year}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields: { record_ids: recordIds } }),
    }
  )
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return (json.data?.record_share_links ?? {}) as Record<string, string>
}

// ---- Feishu Settings ----

export async function fetchQualitySyncConflicts(params?: {
  limit?: number
}): Promise<{ items: QualitySyncConflictItem[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.limit) searchParams.set('limit', String(params.limit))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/feishu-sync/conflicts${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return { items: json.data || [], total: json.meta?.total || 0 }
}

export async function fetchQualityFeishuAppSettings(): Promise<QualityFeishuAppSettingsDetail> {
  const res = await fetch('/api/v1/quality/feishu-settings/app')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchQualityFeishuEntitySettings(): Promise<QualityFeishuEntitySettingItem[]> {
  const res = await fetch('/api/v1/quality/feishu-settings/entities')
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchQualityFeishuEntityTables(
  entityCode: string,
  appToken?: string
): Promise<QualityFeishuTableOption[]> {
  const searchParams = new URLSearchParams()
  if (appToken?.trim()) searchParams.set('app_token', appToken.trim())
  const query = searchParams.toString()
  const res = await fetch(
    `/api/v1/quality/feishu-settings/entities/${entityCode}/tables${query ? `?${query}` : ''}`
  )
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

export async function fetchQualityFeishuEntityFieldMappingBundle(
  entityCode: string,
  params?: {
    app_token?: string
    table_id?: string
  }
): Promise<QualityFeishuEntityFieldMappingBundle> {
  const searchParams = new URLSearchParams()
  if (params?.app_token?.trim()) searchParams.set('app_token', params.app_token.trim())
  if (params?.table_id?.trim()) searchParams.set('table_id', params.table_id.trim())
  const query = searchParams.toString()
  const res = await fetch(
    `/api/v1/quality/feishu-settings/entities/${entityCode}/field-mapping${query ? `?${query}` : ''}`
  )
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const json = await res.json()
  return json.data ?? json
}

// ---- AI Logs ----

export async function fetchQualityAiLogs(params: {
  entity_type: 'deviation' | 'capa' | 'change'
  entity_id: string
  page?: number
  page_size?: number
}): Promise<{ items: any[]; total: number }> {
  const searchParams = new URLSearchParams()
  searchParams.set('entity_type', params.entity_type)
  searchParams.set('entity_id', params.entity_id)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  const res = await fetch(`/api/v1/quality/ai/logs?${searchParams.toString()}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return { items: json.data || [], total: json.meta?.total || 0 }
}

// ---- Feishu Native APIs ----

export async function fetchFeishuCapas(params?: {
  keyword?: string
  page?: number
  page_size?: number
}): Promise<FeishuListResponse<FeishuCapaLedgerItem>> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/feishu/capas${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return { items: json.data ?? [], total: json.meta?.total ?? 0 }
}

export async function fetchFeishuCapaPlanTracks(params?: {
  keyword?: string
  page?: number
  page_size?: number
}): Promise<FeishuListResponse<FeishuCapaPlanTrackItem>> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/feishu/capa-plan-tracks${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return { items: json.data ?? [], total: json.meta?.total ?? 0 }
}

// ---- Department Contacts ----

export async function fetchDepartmentContacts(): Promise<DepartmentContact[]> {
  const res = await fetch('/api/v1/quality/department-contacts/feishu?page=1&page_size=1000')
  if (!res.ok) throw new Error(`获取部门联系人失败: ${res.statusText}`)
  const json = await res.json()
  return json.data?.items ?? []
}

// ---- OOS/OOT APIs ----

const OOS_OOT_API_BASE = '/api/v1/quality/oos-oot'

export async function fetchOosOotReportRecords(params?: Record<string, string | number>): Promise<{ data: OosOotReportRecordItem[]; meta?: { total?: number; page?: number; page_size?: number } }> {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/report-records${query}`)
  if (!res.ok) throw new Error(`获取OOSOOT报告记录失败: ${res.statusText}`)
  return res.json()
}

export async function fetchOosOotInvestigationPushRecords(params?: Record<string, string | number>): Promise<{ data: OosOotInvestigationPushRecordItem[]; meta?: { total?: number; page?: number; page_size?: number } }> {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/investigation-push-records${query}`)
  if (!res.ok) throw new Error(`获取OOSOOT调查推送记录失败: ${res.statusText}`)
  return res.json()
}

export async function fetchOosLedgerRecords(params?: Record<string, string | number>) {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/oos-ledger${query}`)
  if (!res.ok) throw new Error(`获取OOS台账失败: ${res.statusText}`)
  return res.json()
}

export async function fetchOotLedgerRecords(params?: Record<string, string | number>) {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/oot-ledger${query}`)
  if (!res.ok) throw new Error(`获取OOT台账失败: ${res.statusText}`)
  return res.json()
}

export async function fetchOotLimitProducts(params?: Record<string, string | number>) {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/oot-limit-products${query}`)
  if (!res.ok) throw new Error(`获取OOT限度产品失败: ${res.statusText}`)
  return res.json()
}

export async function fetchOotLimitItems(params?: Record<string, string | number>) {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/oot-limit-items${query}`)
  if (!res.ok) throw new Error(`获取OOT限度明细失败: ${res.statusText}`)
  return res.json()
}

export async function fetchProductDepartmentRecords(params?: Record<string, string | number>) {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${OOS_OOT_API_BASE}/product-departments${query}`)
  if (!res.ok) throw new Error(`获取产品涉及部门失败: ${res.statusText}`)
  return res.json()
}

// ---- Complaint & Return/Recall ----

const COMPLAINT_RETURN_API_BASE = '/api/v1/quality'

export async function fetchComplaintLedgerRecords(
  params?: Record<string, string | number>
): Promise<{ data: ComplaintLedgerItem[]; meta?: { total?: number; page?: number; page_size?: number } }> {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${COMPLAINT_RETURN_API_BASE}/complaint-ledger${query}`)
  if (!res.ok) throw new Error(`获取投诉台账失败: ${res.statusText}`)
  return res.json()
}

export async function fetchReturnApplicationRecords(
  params?: Record<string, string | number>
): Promise<{ data: ReturnApplicationItem[]; meta?: { total?: number; page?: number; page_size?: number } }> {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${COMPLAINT_RETURN_API_BASE}/return-application${query}`)
  if (!res.ok) throw new Error(`获取退货申请失败: ${res.statusText}`)
  return res.json()
}

export async function fetchReturnLedgerRecords(
  params?: Record<string, string | number>
): Promise<{ data: ReturnLedgerItem[]; meta?: { total?: number; page?: number; page_size?: number } }> {
  const queryParts: string[] = []
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) queryParts.push(`${key}=${encodeURIComponent(String(value))}`)
    }
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`${COMPLAINT_RETURN_API_BASE}/return-ledger${query}`)
  if (!res.ok) throw new Error(`获取退回台账失败: ${res.statusText}`)
  return res.json()
}

// ---- Formatting helpers（已迁至 lib/format/quality.ts，此处保留兼容重导出）----

export { formatQualitySyncSummary, formatQualityFeishuTestSummary } from '@/lib/format/quality'

/**
 * 文件管理（各部门文件目录）- 客户端只读 API (GET)
 */

export async function fetchDocumentDepartments(): Promise<DocumentDepartmentItem[]> {
  const res = await fetch('/api/v1/quality/document-departments')
  if (!res.ok) throw new Error(`获取文件目录部门失败: ${res.statusText}`)
  const json = await res.json()
  return json.data ?? []
}

export async function fetchDocumentEntries(params?: {
  department_id?: string
  keyword?: string
  page?: number
  page_size?: number
}): Promise<{ items: DocumentEntryItem[]; total: number }> {
  const queryParts: string[] = []
  if (params) {
    if (params.department_id) queryParts.push(`department_id=${encodeURIComponent(params.department_id)}`)
    if (params.keyword) queryParts.push(`keyword=${encodeURIComponent(params.keyword)}`)
    if (params.page) queryParts.push(`page=${params.page}`)
    if (params.page_size) queryParts.push(`page_size=${params.page_size}`)
  }
  const query = queryParts.length ? `?${queryParts.join('&')}` : ''
  const res = await fetch(`/api/v1/quality/document-entries${query}`)
  if (!res.ok) throw new Error(`获取文件目录条目失败: ${res.statusText}`)
  const json = await res.json()
  return { items: json.data ?? [], total: json.meta?.total ?? 0 }
}

/** 按文件名称查询最新版文件编号（培训签到表录入《文件名》（编号）用） */
export async function lookupLatestDocument(
  name: string
): Promise<{ name: string; code: string | null; effective_date: string | null } | null> {
  const res = await fetch(
    `/api/v1/quality/document-entries/lookup-latest?name=${encodeURIComponent(name)}`,
    { cache: 'no-store' }
  )
  if (!res.ok) return null
  const json = await res.json()
  return json.data ?? null
}

/** 导出文件目录 docx（后端复用留存标准模板生成） */
export async function fetchDocumentCatalogExport(
  departmentId?: string,
  departmentName?: string
): Promise<{ blob: Blob; filename: string }> {
  const searchParams = new URLSearchParams()
  if (departmentId) searchParams.set('department_id', departmentId)
  if (departmentName) searchParams.set('department_name', departmentName)
  const query = searchParams.toString()
  const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const fallback = departmentName
    ? `${departmentName}文件目录_${dateStr}.docx`
    : `文件目录_${dateStr}.docx`
  return fetchQualityFile(
    `/api/v1/quality/document-catalog/export${query ? `?${query}` : ''}`,
    fallback
  )
}

/** 附件预览内容：word 附件返回标准 MD 文本；图片/PDF 返回文件 blob */
export async function fetchDocumentEntryAttachmentContent(
  entryId: string,
  storageKey: string
): Promise<{ text: string; blobUrl: string; contentType: string }> {
  const encodedKey = storageKey.split('/').map(encodeURIComponent).join('/')
  const res = await fetch(
    `/api/v1/quality/document-entries/${entryId}/attachments/${encodedKey}/content`
  )
  if (!res.ok) throw new Error(`获取附件内容失败: ${res.statusText}`)
  const contentType = res.headers.get('content-type') || ''
  if (!contentType || contentType.includes('markdown') || contentType.startsWith('text/')) {
    return { text: await res.text(), blobUrl: '', contentType }
  }
  const blob = await res.blob()
  return { text: '', blobUrl: URL.createObjectURL(blob), contentType }
}

/** 获取检验实体字段元数据（供动态表单渲染）。 */
export async function fetchInspectionFeishuFields(
  entityCode: string
): Promise<InspectionFeishuFieldsResult | null> {
  const res = await fetch(`/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/fields`)
  if (!res.ok) return null
  const json = await res.json()
  return json.data as InspectionFeishuFieldsResult
}

// ---- 历史偏差 ----

export async function fetchHistoricalDeviations(params?: {
  keyword?: string
  page?: number
  page_size?: number
}): Promise<{ items: HistoricalDeviationListItem[]; total: number; page?: number; page_size?: number }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/historical-deviations${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return {
    items: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page,
    page_size: json.meta?.page_size,
  }
}

export async function fetchHistoricalDeviation(id: string): Promise<HistoricalDeviationDetail | null> {
  const res = await fetch(`/api/v1/quality/historical-deviations/${id}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data ?? null
}

/** 历史偏差附件预览内容：word 返回标准 MD；图片/PDF 返回原文件 */
export async function fetchHistoricalDeviationAttachmentContent(
  recordId: string,
  storageKey: string
): Promise<{ text: string; blobUrl: string; contentType: string }> {
  const encodedKey = storageKey.split('/').map(encodeURIComponent).join('/')
  const res = await fetch(
    `/api/v1/quality/historical-deviations/${recordId}/attachments/${encodedKey}/content`
  )
  if (!res.ok) throw new Error(`获取附件内容失败: ${res.statusText}`)
  const contentType = res.headers.get('content-type') || ''
  if (!contentType || contentType.includes('markdown') || contentType.startsWith('text/')) {
    return { text: await res.text(), blobUrl: '', contentType }
  }
  const blob = await res.blob()
  return { text: '', blobUrl: URL.createObjectURL(blob), contentType }
}

// ---- 偏差工作台 ----

export async function fetchDeviationWorkbenchSettings(): Promise<DeviationWorkbenchSettings | null> {
  const res = await fetch('/api/v1/quality/deviation-workbench/settings')
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data ?? null
}

export async function fetchDeviationWorkbenchReports(params?: {
  keyword?: string
  source_type?: string
  status?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}): Promise<{ items: DeviationWorkbenchReportListItem[]; total: number; page?: number; page_size?: number }> {
  const searchParams = new URLSearchParams()
  if (params?.keyword) searchParams.set('keyword', params.keyword)
  if (params?.source_type) searchParams.set('source_type', params.source_type)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.date_from) searchParams.set('date_from', params.date_from)
  if (params?.date_to) searchParams.set('date_to', params.date_to)
  if (params?.page) searchParams.set('page', String(params.page))
  if (params?.page_size) searchParams.set('page_size', String(params.page_size))
  const query = searchParams.toString()
  const res = await fetch(`/api/v1/quality/deviation-workbench/reports${query ? `?${query}` : ''}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return {
    items: json.data || [],
    total: json.meta?.total || 0,
    page: json.meta?.page,
    page_size: json.meta?.page_size,
  }
}

export async function fetchDeviationWorkbenchReport(id: string): Promise<DeviationWorkbenchReportDetail | null> {
  const res = await fetch(`/api/v1/quality/deviation-workbench/reports/${id}`)
  if (!res.ok) throw await parseError(res)
  const json = await res.json()
  return json.data ?? null
}

/** 偏差工作台附件预览内容 */
export async function fetchDeviationWorkbenchAttachmentContent(
  url: string
): Promise<{ text: string; blobUrl: string; contentType: string }> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`获取附件内容失败: ${res.statusText}`)
  const contentType = res.headers.get('content-type') || ''
  if (!contentType || contentType.includes('markdown') || contentType.startsWith('text/')) {
    return { text: await res.text(), blobUrl: '', contentType }
  }
  const blob = await res.blob()
  return { text: '', blobUrl: URL.createObjectURL(blob), contentType }
}
