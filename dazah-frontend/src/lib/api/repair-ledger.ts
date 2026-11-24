'use client'

const BASE = '/api/v1/equipment/repair'

/** 检修记录（飞书镜像原文展示，不关联设备台账） */
export interface RepairRecord {
  id: string
  workshop_code: string
  record_id: string
  workshop_text: string | null
  equipment_text: string | null
  repaired_at: string | null
  person_text: string | null
  fault_desc: string | null
  spare_parts: string | null
  result: string | null
  remark: string | null
  last_modified_at: string | null
}

export interface RepairRecordFilters {
  workshop?: string
  date_from?: string
  date_to?: string
  keyword?: string
  /** 设备名称原文（频次榜点入） */
  equipment?: string
  /** 维修后状态原文 */
  result?: string
  page?: number
  page_size?: number
}

export interface RepairRecordPage {
  items: RepairRecord[]
  total: number
  page: number
  page_size: number
}

export interface RepairFrequencyItem {
  equipment_text: string
  times: number
  last_repaired_at: string | null
}

export interface RepairSyncState {
  workshop_code: string
  total_rows: number
  last_synced_at: string | null
  last_run_at: string | null
  last_status: string | null
  last_message: string | null
  enabled: boolean
}

export interface RepairConfigDetail {
  workshop_code: string
  feishu_app_id: string | null
  app_name: string
  app_id: string
  app_secret_masked: string
  app_secret_configured: boolean
  app_token: string
  table_id: string
  base_url: string
  is_enabled: boolean
  enabled: boolean
  last_test_status: string | null
  last_test_error: string | null
  last_tested_at: string | null
}

export interface RepairConfigUpdateRequest {
  feishu_app_id?: string
  app_id?: string
  app_secret?: string | null
  app_name?: string
  app_token: string
  table_id: string
  base_url: string
  is_enabled: boolean
}

export interface RepairConfigTestResult {
  success: boolean
  message: string
}

interface ApiResponse<T> {
  code: number
  message?: string
  data: T
  meta?: { total?: number; page?: number; page_size?: number }
}

async function getJson<T>(url: string): Promise<ApiResponse<T>> {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message || `请求失败: ${response.status}`)
  }
  return response.json()
}

async function sendJson<T>(url: string, method: 'POST' | 'PUT', body?: unknown): Promise<ApiResponse<T>> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  // 服务端异常可能返回纯文本（如 500 Internal Server Error），不能盲当 JSON 解析
  const json = await response.json().catch(() => null)
  if (!response.ok || !json || json.code !== 200) {
    throw new Error(json?.message || `请求失败: ${response.status}`)
  }
  return json
}

function workshopQuery(workshop: string): string {
  return `workshop=${encodeURIComponent(workshop)}`
}

export async function fetchRepairRecords(
  filters: RepairRecordFilters = {},
): Promise<RepairRecordPage> {
  const params = new URLSearchParams()
  if (filters.workshop) params.append('workshop', filters.workshop)
  if (filters.date_from) params.append('date_from', filters.date_from)
  if (filters.date_to) params.append('date_to', filters.date_to)
  if (filters.keyword) params.append('keyword', filters.keyword)
  if (filters.equipment) params.append('equipment', filters.equipment)
  if (filters.result) params.append('result_status', filters.result)
  params.append('page', String(filters.page || 1))
  params.append('page_size', String(filters.page_size || 20))
  const json = await getJson<RepairRecord[]>(`${BASE}/records?${params.toString()}`)
  return {
    items: (json.data || []) as RepairRecord[],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchRepairFrequency(
  workshop: string,
  dateFrom?: string,
): Promise<RepairFrequencyItem[]> {
  const params = new URLSearchParams({ workshop, limit: '10' })
  if (dateFrom) params.append('date_from', dateFrom)
  const json = await getJson<RepairFrequencyItem[]>(`${BASE}/frequency?${params.toString()}`)
  return json.data ?? []
}

export async function fetchRepairResults(workshop: string): Promise<string[]> {
  const json = await getJson<string[]>(`${BASE}/results?${workshopQuery(workshop)}`)
  return json.data ?? []
}

export async function fetchRepairSyncStatus(workshop: string): Promise<RepairSyncState> {
  const json = await getJson<RepairSyncState>(`${BASE}/sync-status?${workshopQuery(workshop)}`)
  return json.data
}

/** 手动触发飞书同步，返回各车间的同步结果 */
export async function triggerRepairSync(
  workshop: string,
): Promise<Record<string, { synced?: number; total?: number; error?: string }>> {
  const json = await sendJson<Record<string, { synced?: number; total?: number; error?: string }>>(
    `${BASE}/sync?${workshopQuery(workshop)}`,
    'POST',
  )
  return json.data
}

export async function fetchRepairConfig(workshop: string): Promise<RepairConfigDetail> {
  const json = await getJson<RepairConfigDetail>(`${BASE}/config?${workshopQuery(workshop)}`)
  return json.data
}

export async function updateRepairConfig(
  workshop: string,
  values: RepairConfigUpdateRequest,
): Promise<RepairConfigDetail> {
  const json = await sendJson<RepairConfigDetail>(
    `${BASE}/config?${workshopQuery(workshop)}`,
    'PUT',
    values,
  )
  return json.data
}

export async function testRepairConfig(workshop: string): Promise<RepairConfigTestResult> {
  const json = await sendJson<RepairConfigTestResult>(
    `${BASE}/config/test?${workshopQuery(workshop)}`,
    'POST',
  )
  return json.data
}
