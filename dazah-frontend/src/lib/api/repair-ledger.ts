'use client'

const BASE = '/api/v1/equipment/repair'

/** 检修记录（飞书镜像原文展示，不关联设备台账） */
export interface RepairPerson {
  name: string
  open_id: string | null
  avatar_url: string | null
}

export interface RepairRecord {
  id: string
  workshop_code: string
  record_id: string
  workshop_text: string | null
  equipment_text: string | null
  repaired_at: string | null
  person_text: string | null
  /** 同步时经通讯录解析的维修人员；解析不到（无权限/未匹配）时为空，展示回退 person_text */
  persons?: RepairPerson[] | null
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
  /** 维修人员姓名（结构化或原文） */
  person?: string
  /** 故障描述（模糊匹配） */
  fault?: string
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
  if (filters.person) params.append('person', filters.person)
  if (filters.fault) params.append('fault', filters.fault)
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

/** 筛选下拉的去重选项（人员 / 故障 / 设备，按出现次数降序） */
export interface RepairFilterOptions {
  persons: string[]
  faults: string[]
  equipments: string[]
}

export async function fetchRepairFilterOptions(
  workshop: string,
): Promise<RepairFilterOptions> {
  const json = await getJson<RepairFilterOptions>(
    `${BASE}/filter-options?${workshopQuery(workshop)}`,
  )
  return json.data ?? { persons: [], faults: [], equipments: [] }
}

/** 按当前筛选条件导出全部命中记录为 Excel 并触发浏览器下载 */
export async function exportRepairRecords(
  filters: RepairRecordFilters,
): Promise<void> {
  const params = new URLSearchParams()
  if (filters.workshop) params.append('workshop', filters.workshop)
  if (filters.date_from) params.append('date_from', filters.date_from)
  if (filters.date_to) params.append('date_to', filters.date_to)
  if (filters.keyword) params.append('keyword', filters.keyword)
  if (filters.equipment) params.append('equipment', filters.equipment)
  if (filters.person) params.append('person', filters.person)
  if (filters.fault) params.append('fault', filters.fault)
  if (filters.result) params.append('result_status', filters.result)
  const response = await fetch(`${BASE}/export?${params.toString()}`)
  if (!response.ok) {
    // 业务失败（如超上限）返回统一 JSON 封装；文件流响应不能先读 JSON
    const json = await response.json().catch(() => null)
    throw new Error(json?.message || `导出失败: ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  const disposition = response.headers.get('Content-Disposition') || ''
  const starred = disposition.match(/filename\*=UTF-8''([^;]+)/)
  anchor.download = starred
    ? decodeURIComponent(starred[1])
    : `设备检修_${filters.workshop ?? '全部车间'}_${new Date().toISOString().slice(0, 10).replaceAll('-', '')}.xlsx`
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
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
