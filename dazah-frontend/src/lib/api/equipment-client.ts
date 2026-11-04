'use client'

import {
  EquipmentCategory,
  Location,
  EquipmentListResponse, EquipmentStatistics,
  FailureCode, WorkOrderFilters, WorkOrderListResponse, WorkOrderStatistics, WorkOrder,
  CalibrationPlanFilters, CalibrationPlanListResponse,
  CalibrationRecordFilters, CalibrationRecordListResponse,
  SparePartFilters, SparePartListResponse, SparePart, StockWarning,
  MaintenancePlanFilters, MaintenancePlanListResponse, MaintenancePlan,
  MaterialRecord,
  ClaimTimeoutConfig, Maintainer, WorkOrderImage,
  EquipmentHealth, RepairProfile, HealthBoard, KnowledgeCaseHit, KnowledgeCase, KnowledgeCaseStatus, MonthlyReport,
  PurchaseSuggestion, PurchaseSuggestionStatus, LaborRate, CostReport,
} from '@/types/equipment'

interface FetchEquipmentsParams {
  workshop?: string
  category_id?: string | null
  location_id?: string | null
  department_id?: string | null
  status?: string
  keyword?: string
  page?: number
  page_size?: number
}

export async function fetchEquipmentsClient(params: FetchEquipmentsParams = {}): Promise<EquipmentListResponse> {
  const searchParams = new URLSearchParams()

  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.category_id) searchParams.append('category_id', params.category_id)
  if (params.location_id) searchParams.append('location_id', params.location_id)
  if (params.department_id) searchParams.append('department_id', params.department_id)
  if (params.status) searchParams.append('status', params.status)
  if (params.keyword) searchParams.append('keyword', params.keyword)
  if (params.page && params.page > 0) searchParams.append('page', params.page.toString())
  if (params.page_size && params.page_size > 0) searchParams.append('page_size', params.page_size.toString())

  const queryString = searchParams.toString()
  const url = queryString
    ? `/api/v1/equipment/equipments?${queryString}`
    : `/api/v1/equipment/equipments`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }

  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

export async function fetchEquipmentStatisticsClient(workshop?: string): Promise<EquipmentStatistics> {
  const qs = workshop ? `?workshop=${encodeURIComponent(workshop)}` : ''
  const response = await fetch(`/api/v1/equipment/equipments/statistics${qs}`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }

  const result = await response.json()
  return result.data || { total: 0, by_status: {}, by_category: {}, by_location: {} }
}

// ==================== 故障代码 ====================
export async function fetchCategoriesClient(): Promise<EquipmentCategory[]> {
  const response = await fetch(`/api/v1/equipment/categories`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || []
}

export async function fetchLocationsClient(): Promise<Location[]> {
  const response = await fetch(`/api/v1/equipment/locations`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || []
}

export async function fetchFailureCodesClient(type: 'symptoms' | 'causes' | 'actions'): Promise<FailureCode[]> {
  const response = await fetch(`/api/v1/equipment/maintenance/failure-codes/${type}`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || []
}

// ==================== 维修工单 ====================
export async function fetchWorkOrdersClient(params: WorkOrderFilters = {}): Promise<WorkOrderListResponse> {
  const searchParams = new URLSearchParams()
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.status) searchParams.append('status', params.status)
  if (params.equipment_id) searchParams.append('equipment_id', params.equipment_id)
  if (params.priority) searchParams.append('priority', params.priority)
  if (params.order_type) searchParams.append('order_type', params.order_type)
  if (params.page && params.page > 0) searchParams.append('page', params.page.toString())
  if (params.page_size && params.page_size > 0) searchParams.append('page_size', params.page_size.toString())

  const queryString = searchParams.toString()
  const url = queryString
    ? `/api/v1/equipment/maintenance/work-orders?${queryString}`
    : `/api/v1/equipment/maintenance/work-orders`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }

  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

export async function fetchWorkOrderStatisticsClient(workshop?: string): Promise<WorkOrderStatistics> {
  const qs = workshop ? `?workshop=${encodeURIComponent(workshop)}` : ''
  const response = await fetch(`/api/v1/equipment/maintenance/work-orders/statistics${qs}`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || { total: 0, by_status: {}, by_type: {}, by_priority: {} }
}

export async function fetchWorkOrderByIdClient(id: string): Promise<WorkOrder> {
  const response = await fetch(`/api/v1/equipment/maintenance/work-orders/${id}`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data
}

// ==================== 校准计划 ====================
export async function fetchCalibrationPlansClient(params: CalibrationPlanFilters = {}): Promise<CalibrationPlanListResponse> {
  const searchParams = new URLSearchParams()
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.equipment_id) searchParams.append('equipment_id', params.equipment_id)
  if (params.status) searchParams.append('status', params.status)
  if (params.page && params.page > 0) searchParams.append('page', params.page.toString())
  if (params.page_size && params.page_size > 0) searchParams.append('page_size', params.page_size.toString())

  const queryString = searchParams.toString()
  const url = queryString
    ? `/api/v1/equipment/maintenance/calibration/plans?${queryString}`
    : `/api/v1/equipment/maintenance/calibration/plans`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }

  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

// ==================== 校准记录 ====================
export async function fetchCalibrationRecordsClient(params: CalibrationRecordFilters = {}): Promise<CalibrationRecordListResponse> {
  const searchParams = new URLSearchParams()
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.equipment_id) searchParams.append('equipment_id', params.equipment_id)
  if (params.plan_id) searchParams.append('plan_id', params.plan_id)
  if (params.page && params.page > 0) searchParams.append('page', params.page.toString())
  if (params.page_size && params.page_size > 0) searchParams.append('page_size', params.page_size.toString())

  const queryString = searchParams.toString()
  const url = queryString
    ? `/api/v1/equipment/maintenance/calibration/records?${queryString}`
    : `/api/v1/equipment/maintenance/calibration/records`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }

  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

// ==================== 备件管理 ====================
export async function fetchSparePartsClient(params: SparePartFilters = {}): Promise<SparePartListResponse> {
  const searchParams = new URLSearchParams()
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.category) searchParams.append('category', params.category)
  if (params.keyword) searchParams.append('keyword', params.keyword)
  if (params.is_active !== undefined) searchParams.append('is_active', params.is_active.toString())
  if (params.page && params.page > 0) searchParams.append('page', params.page.toString())
  if (params.page_size && params.page_size > 0) searchParams.append('page_size', params.page_size.toString())

  const queryString = searchParams.toString()
  const url = queryString
    ? `/api/v1/equipment/spare-parts/?${queryString}`
    : `/api/v1/equipment/spare-parts/`

  const response = await fetch(url)
  if (!response.ok) throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

export async function fetchSparePartByIdClient(id: string): Promise<SparePart> {
  const response = await fetch(`/api/v1/equipment/spare-parts/${id}`)
  if (!response.ok) throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  const result = await response.json()
  return result.data
}

export async function fetchStockWarningsClient(workshop?: string): Promise<StockWarning[]> {
  const qs = workshop ? `?workshop=${encodeURIComponent(workshop)}` : ''
  const response = await fetch(`/api/v1/equipment/spare-parts/stock/warnings${qs}`)
  if (!response.ok) throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  const result = await response.json()
  return result.data || []
}

// ==================== 维护计划 ====================
export async function fetchMaintenancePlansClient(params: MaintenancePlanFilters = {}): Promise<MaintenancePlanListResponse> {
  const searchParams = new URLSearchParams()
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.equipment_id) searchParams.append('equipment_id', params.equipment_id)
  if (params.status) searchParams.append('status', params.status)
  if (params.keyword) searchParams.append('keyword', params.keyword)
  if (params.page && params.page > 0) searchParams.append('page', params.page.toString())
  if (params.page_size && params.page_size > 0) searchParams.append('page_size', params.page_size.toString())

  const queryString = searchParams.toString()
  const url = queryString
    ? `/api/v1/equipment/maintenance/plans/?${queryString}`
    : `/api/v1/equipment/maintenance/plans/`

  const response = await fetch(url)
  if (!response.ok) throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  const result = await response.json()
  return {
    items: result.data || [],
    total: result.meta?.total || 0,
    page: result.meta?.page || 1,
    page_size: result.meta?.page_size || 20,
  }
}

export async function fetchOverdueMaintenancePlansClient(days?: number): Promise<MaintenancePlan[]> {
  const params = days ? `?days=${days}` : ''
  const response = await fetch(`/api/v1/equipment/maintenance/plans/overdue${params}`)
  if (!response.ok) throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  const result = await response.json()
  return result.data || []
}

// ==================== 工单物料 ====================
export async function fetchWorkOrderMaterialsClient(workOrderId: string): Promise<MaterialRecord[]> {
  const response = await fetch(`/api/v1/equipment/maintenance/work-orders/${workOrderId}/materials`)
  if (!response.ok) throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  const result = await response.json()
  return result.data || []
}

// ==================== 维修人员 ====================
export async function fetchMaintainersClient(): Promise<Maintainer[]> {
  const response = await fetch(`/api/v1/equipment/maintenance/staff/maintainers`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const result = await response.json()
  return result.data || []
}

export async function fetchAllUsersClient(): Promise<Maintainer[]> {
  const response = await fetch(`/api/v1/equipment/maintenance/staff/all-users`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const result = await response.json()
  return result.data || []
}

// ==================== 工单图片 ====================
export async function fetchWorkOrderImagesClient(workOrderId: string): Promise<WorkOrderImage[]> {
  const response = await fetch(`/api/v1/equipment/maintenance/work-orders${workOrderId}/images`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const result = await response.json()
  return result.data || []
}

// ==================== 超时配置 ====================
export async function fetchClaimTimeoutConfigClient(): Promise<ClaimTimeoutConfig> {
  const response = await fetch(`/api/v1/equipment/maintenance/config/claim-timeout`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const result = await response.json()
  return result.data || { emergency: 15, high: 30, medium: 60, low: 120 }
}

// ==================== 部门列表 ====================
export async function fetchDepartmentsClient(): Promise<import('@/types/equipment').DepartmentOption[]> {
  const response = await fetch(`/api/v1/equipment/departments`)
  if (!response.ok) throw new Error(`请求失败: ${response.status}`)
  const result = await response.json()
  return result.data || []
}

// ==================== 设备健康档案与维修知识库（方案B） ====================
export async function fetchEquipmentHealthClient(
  equipmentId: string,
  days = 30,
): Promise<EquipmentHealth> {
  const response = await fetch(
    `/api/v1/equipment/health/equipment/${equipmentId}?days=${days}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return (
    result.data || { equipment_id: equipmentId, latest: null, snapshots: [] }
  )
}

export async function fetchRepairProfileClient(
  equipmentId: string,
): Promise<RepairProfile | null> {
  const response = await fetch(
    `/api/v1/equipment/health/repair-profile/${equipmentId}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || null
}

export async function fetchHealthBoardClient(
  workshop?: string,
  grade?: 'G' | 'Y' | 'R',
): Promise<HealthBoard> {
  const searchParams = new URLSearchParams()
  if (workshop) searchParams.append('workshop', workshop)
  if (grade) searchParams.append('grade', grade)
  const qs = searchParams.toString()
  const response = await fetch(
    `/api/v1/equipment/health/board${qs ? `?${qs}` : ''}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || { items: [], summary: { total: 0, G: 0, Y: 0, R: 0 } }
}

export async function searchKnowledgeCasesClient(params: {
  q: string
  equipment_id?: string
  symptom_code?: string
  top?: number
}): Promise<KnowledgeCaseHit[]> {
  const searchParams = new URLSearchParams({ q: params.q })
  if (params.equipment_id) searchParams.append('equipment_id', params.equipment_id)
  if (params.symptom_code) searchParams.append('symptom_code', params.symptom_code)
  if (params.top) searchParams.append('top', String(params.top))
  const response = await fetch(
    `/api/v1/equipment/repair-knowledge/search?${searchParams.toString()}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data?.items || []
}

export async function fetchKnowledgeCasesClient(params: {
  status?: KnowledgeCaseStatus
  page?: number
  page_size?: number
}): Promise<{ items: KnowledgeCase[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params.status) searchParams.append('status', params.status)
  if (params.page) searchParams.append('page', String(params.page))
  if (params.page_size) searchParams.append('page_size', String(params.page_size))
  const response = await fetch(
    `/api/v1/equipment/repair-knowledge/cases?${searchParams.toString()}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return { items: result.data || [], total: result.meta?.total || 0 }
}

export async function fetchMonthlyReportsClient(): Promise<MonthlyReport[]> {
  const response = await fetch(`/api/v1/equipment/health/monthly-reports`)
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || []
}

// ==================== 备件采购建议与维修成本（方案C） ====================
export async function fetchPurchaseSuggestionsClient(params: {
  status?: PurchaseSuggestionStatus
  workshop?: string
  page?: number
  page_size?: number
}): Promise<{ items: PurchaseSuggestion[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params.status) searchParams.append('status', params.status)
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.page) searchParams.append('page', String(params.page))
  if (params.page_size) searchParams.append('page_size', String(params.page_size))
  const response = await fetch(
    `/api/v1/equipment/spare-parts/purchase-suggestions?${searchParams.toString()}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return { items: result.data || [], total: result.meta?.total || 0 }
}

export async function fetchLaborRatesClient(): Promise<LaborRate[]> {
  const response = await fetch(
    `/api/v1/equipment/spare-parts/purchase-suggestions/labor-rates`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || []
}

export async function fetchCostReportClient(params: {
  workshop?: string
  month?: string
  group_by?: 'equipment' | 'workshop' | 'fault_type'
}): Promise<CostReport | null> {
  const searchParams = new URLSearchParams()
  if (params.workshop) searchParams.append('workshop', params.workshop)
  if (params.month) searchParams.append('month', params.month)
  if (params.group_by) searchParams.append('group_by', params.group_by)
  const response = await fetch(
    `/api/v1/equipment/maintenance/work-orders/cost-report?${searchParams.toString()}`,
  )
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${response.statusText}`)
  }
  const result = await response.json()
  return result.data || null
}
