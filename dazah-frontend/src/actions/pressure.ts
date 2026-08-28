'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type {
  ApiResponse,
  AuditStats,
  BatchManualEntryRequest,
  BatchManualEntryResponse,
  CreateOcrRecordRequest,
  DashboardStats,
  DeleteMergedRowRequest,
  MergedPressureRow,
  NotificationListResponse,
  OcrSubmitResponse,
  OcrTask,
  PointMapping,
  PressureRecord,
  UpdateMergedRowRequest,
} from '@/types/pressure'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

// ============ Helper ============

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  try {
    const authHeaders = await getAuthHeaders()
    const { headers: optHeaders, ...restOptions } = options || {}
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: { ...authHeaders, ...optHeaders },
      ...restOptions,
    })
    
    // Check if response is JSON
    const contentType = response.headers.get('content-type')
    if (!contentType || !contentType.includes('application/json')) {
      const text = await response.text()
      console.error(`API Error: ${response.status} - ${text.substring(0, 200)}`)
      return {
        code: response.status,
        message: `API 错误：${response.status}`,
        data: null as T,
        meta: undefined,
      }
    }
    
    return await response.json()
  } catch (error) {
    console.error(`fetchApi error for ${endpoint}:`, error)
    return {
      code: 500,
      message: `请求失败：${error instanceof Error ? error.message : '未知错误'}`,
      data: null as T,
      meta: undefined,
    }
  }
}

// ============ Dashboard ============

export async function getPressureDashboard() {
  return fetchApi<DashboardStats>('/api/v1/production/pressure/dashboard')
}

// ============ PointMapping ============

export async function getPointMappings(params: {
  area?: string
  keyword?: string
  page?: number
  page_size?: number
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.area) searchParams.set('area', params.area)
  if (params.keyword) searchParams.set('keyword', params.keyword)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  const qs = searchParams.toString()
  return fetchApi<PointMapping[]>(
    `/api/v1/production/pressure/point-mappings${qs ? `?${qs}` : ''}`
  )
}

export async function getPointMapping(id: string) {
  return fetchApi<PointMapping>(
    `/api/v1/production/pressure/point-mappings/${id}`
  )
}

export async function createPointMapping(data: {
  point_id: string
  area: string
  standard_pressure: number
}) {
  const response = await fetchApi<PointMapping>(
    '/api/v1/production/pressure/point-mappings',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function updatePointMapping(
  id: string,
  data: { area?: string; standard_pressure?: number }
) {
  const response = await fetchApi<PointMapping>(
    `/api/v1/production/pressure/point-mappings/${id}`,
    { method: 'PUT', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function deletePointMapping(id: string) {
  const response = await fetchApi<void>(
    `/api/v1/production/pressure/point-mappings/${id}`,
    { method: 'DELETE' }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function checkPointIdUnique(pointId: string) {
  return fetchApi<{ exists: boolean }>(
    `/api/v1/production/pressure/point-mappings/check-unique?point_id=${encodeURIComponent(pointId)}`
  )
}

// ============ PressureRecord ============

export async function getPressureRecords(params: {
  area?: string
  point_id?: string
  input_type?: string
  status?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.area) searchParams.set('area', params.area)
  if (params.point_id) searchParams.set('point_id', params.point_id)
  if (params.input_type) searchParams.set('input_type', params.input_type)
  if (params.status) searchParams.set('status', params.status)
  if (params.start_date) searchParams.set('start_date', params.start_date)
  if (params.end_date) searchParams.set('end_date', params.end_date)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  const qs = searchParams.toString()
  return fetchApi<PressureRecord[]>(
    `/api/v1/production/pressure/records${qs ? `?${qs}` : ''}`
  )
}

export async function getMergedPressureRecords(params: {
  area?: string
  point_id?: string
  input_type?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.area) searchParams.set('area', params.area)
  if (params.point_id) searchParams.set('point_id', params.point_id)
  if (params.input_type) searchParams.set('input_type', params.input_type)
  if (params.start_date) searchParams.set('start_date', params.start_date)
  if (params.end_date) searchParams.set('end_date', params.end_date)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  const qs = searchParams.toString()
  return fetchApi<MergedPressureRow[]>(
    `/api/v1/production/pressure/records/merged${qs ? `?${qs}` : ''}`
  )
}

export async function createManualRecord(data: {
  record_time: string
  point_id: string
  pressure_value: number
  time_slot?: string
  remark?: string
}) {
  const response = await fetchApi<{ id: string; success: boolean }>(
    '/api/v1/production/pressure/records/manual',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function createBatchManualRecord(data: BatchManualEntryRequest) {
  const response = await fetchApi<BatchManualEntryResponse>(
    '/api/v1/production/pressure/records/manual/batch',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function submitOcrRecords(data: CreateOcrRecordRequest) {
  const response = await fetchApi<OcrSubmitResponse>(
    '/api/v1/production/pressure/records/ocr',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function auditPressureRecord(
  id: string,
  data: { status: string; reject_reason?: string }
) {
  const response = await fetchApi<{ success: boolean }>(
    `/api/v1/production/pressure/records/${id}/audit`,
    { method: 'PATCH', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function batchAuditPressureRecords(data: {
  ids: string[]
  status: string
  reject_reason?: string
}) {
  const response = await fetchApi<{ success_count: number; fail_count: number }>(
    '/api/v1/production/pressure/records/batch-audit',
    { method: 'PATCH', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function deletePressureRecord(id: string) {
  const response = await fetchApi<void>(
    `/api/v1/production/pressure/records/${id}`,
    { method: 'DELETE' }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function batchDeletePressureRecords(ids: string[]) {
  const response = await fetchApi<{ success_count: number }>(
    '/api/v1/production/pressure/records/batch-delete',
    { method: 'POST', body: JSON.stringify({ ids }) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function updateMergedRow(data: UpdateMergedRowRequest) {
  const response = await fetchApi<{ success_count: number }>(
    '/api/v1/production/pressure/records/merged/update',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function deleteMergedRow(data: DeleteMergedRowRequest) {
  const response = await fetchApi<{ success_count: number }>(
    '/api/v1/production/pressure/records/merged/delete',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function batchDeleteMergedRows(rows: DeleteMergedRowRequest[]) {
  const response = await fetchApi<{ success_count: number }>(
    '/api/v1/production/pressure/records/merged/batch-delete',
    { method: 'POST', body: JSON.stringify({ rows }) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function exportByArea(params: {
  area?: string
  start_date?: string
  end_date?: string
  point_id?: string
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.area) searchParams.set('area', params.area)
  if (params.start_date) searchParams.set('start_date', params.start_date)
  if (params.end_date) searchParams.set('end_date', params.end_date)
  if (params.point_id) searchParams.set('point_id', params.point_id)
  const qs = searchParams.toString()
  return fetchApi<any[]>(
    `/api/v1/production/pressure/records/export/by-area${qs ? `?${qs}` : ''}`
  )
}

// ============ Audit Stats ============

export async function getAuditStats() {
  return fetchApi<AuditStats>('/api/v1/production/pressure/audit/stats')
}

// ============ OcrTask ============

export async function getOcrTasks(params: {
  status?: string
  page?: number
  page_size?: number
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.status) searchParams.set('status', params.status)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  const qs = searchParams.toString()
  return fetchApi<OcrTask[]>(
    `/api/v1/production/pressure/ocr-tasks${qs ? `?${qs}` : ''}`
  )
}

export async function getOcrTask(id: string) {
  return fetchApi<OcrTask>(`/api/v1/production/pressure/ocr-tasks/${id}`)
}

export async function createOcrTask(data: { image_url: string }) {
  const response = await fetchApi<OcrTask>(
    '/api/v1/production/pressure/ocr-tasks',
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function submitOcrTaskResult(
  taskId: string,
  data: { records: any[] }
) {
  const response = await fetchApi<OcrSubmitResponse>(
    `/api/v1/production/pressure/ocr-tasks/${taskId}/submit`,
    { method: 'POST', body: JSON.stringify(data) }
  )
  revalidatePath('/production/pressure')
  return response
}


export async function getNotifications(params: {
  user_id?: string
  page?: number
  page_size?: number
} = {}) {
  const searchParams = new URLSearchParams()
  if (params.user_id) searchParams.set('user_id', params.user_id)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  const qs = searchParams.toString()
  return fetchApi<NotificationListResponse>(
    `/api/v1/production/pressure/notifications${qs ? `?${qs}` : ''}`
  )
}

export async function markNotificationRead(id: string) {
  const response = await fetchApi<void>(
    `/api/v1/production/pressure/notifications/${id}/read`,
    { method: 'PATCH' }
  )
  revalidatePath('/production/pressure')
  return response
}

export async function markAllNotificationsRead(userId?: string) {
  const qs = userId ? `?user_id=${userId}` : ''
  const response = await fetchApi<void>(
    `/api/v1/production/pressure/notifications/read-all${qs}`,
    { method: 'PATCH' }
  )
  revalidatePath('/production/pressure')
  return response
}
