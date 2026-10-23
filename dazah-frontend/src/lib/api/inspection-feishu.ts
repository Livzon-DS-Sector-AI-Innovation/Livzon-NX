'use client'

import type {
  InspectionFeishuConfigDetail,
  InspectionFeishuConfigTestResult,
  InspectionFeishuConfigUpdateRequest,
  InspectionFeishuDevice,
  InspectionFeishuDeviceList,
  InspectionFeishuRecordFilters,
  InspectionFeishuRecordListResponse,
  InspectionFeishuSyncStatus,
  InspectionFeishuTodaySummary,
} from '@/types/inspection-feishu'

const BASE = '/api/v1/equipment/inspection/feishu'

interface PageResult<T> {
  code: number
  message?: string
  data: T
  meta?: { total?: number; page?: number; page_size?: number }
}

async function getJson<T>(url: string): Promise<PageResult<T>> {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message || `请求失败: ${response.status}`)
  }
  return response.json()
}

export async function fetchInspectionFeishuRecords(
  filters: InspectionFeishuRecordFilters = {},
): Promise<InspectionFeishuRecordListResponse> {
  const params = new URLSearchParams()
  if (filters.workshop) params.append('workshop', filters.workshop)
  if (filters.source) params.append('source', filters.source)
  if (filters.date_from) params.append('date_from', filters.date_from)
  if (filters.date_to) params.append('date_to', filters.date_to)
  if (filters.keyword) params.append('keyword', filters.keyword)
  if (filters.abnormal_only) params.append('abnormal_only', 'true')
  if (filters.process_status) params.append('process_status', filters.process_status)
  params.append('page', String(filters.page || 1))
  params.append('page_size', String(filters.page_size || 20))
  const json = await getJson<unknown[]>(`${BASE}/records?${params.toString()}`)
  return {
    items: (json.data || []) as InspectionFeishuRecordListResponse['items'],
    total: json.meta?.total || 0,
    page: json.meta?.page || 1,
    page_size: json.meta?.page_size || 20,
  }
}

export async function fetchInspectionFeishuDevices(
  workshop: string,
  keyword?: string,
): Promise<InspectionFeishuDeviceList> {
  const params = new URLSearchParams({ workshop })
  if (keyword) params.append('keyword', keyword)
  const json = await getJson<InspectionFeishuDeviceList>(
    `${BASE}/devices?${params.toString()}`,
  )
  return {
    date: json.data?.date ?? '',
    items: (json.data?.items || []) as InspectionFeishuDevice[],
  }
}

export async function fetchInspectionFeishuTodaySummary(
  workshop: string,
): Promise<InspectionFeishuTodaySummary> {
  const json = await getJson<InspectionFeishuTodaySummary>(
    `${BASE}/today-summary?workshop=${encodeURIComponent(workshop)}`,
  )
  return json.data
}

export async function fetchInspectionFeishuSyncStatus(
  workshop: string,
): Promise<InspectionFeishuSyncStatus> {
  const json = await getJson<InspectionFeishuSyncStatus>(
    `${BASE}/sync-status?workshop=${encodeURIComponent(workshop)}`,
  )
  return json.data
}

/** 手动触发飞书同步 */
export async function triggerInspectionFeishuSync(
  workshop: string,
): Promise<
  Record<string, { synced?: number; total?: number; error?: string }>
> {
  const response = await fetch(
    `${BASE}/sync?workshop=${encodeURIComponent(workshop)}`,
    { method: 'POST' },
  )
  // 服务端异常可能返回纯文本（如 500 Internal Server Error），不能盲当 JSON 解析
  const json = await response.json().catch(() => null)
  if (!response.ok || !json || json.code !== 200) {
    throw new Error(json?.message || `同步失败（HTTP ${response.status}）`)
  }
  return json.data
}

/** 获取飞书镜像配置（Secret 掩码返回） */
export async function fetchInspectionFeishuConfig(
  workshop: string,
): Promise<InspectionFeishuConfigDetail> {
  const json = await getJson<InspectionFeishuConfigDetail>(
    `${BASE}/config?workshop=${encodeURIComponent(workshop)}`,
  )
  return json.data
}

/** 飞书配置清单：已配置车间 + 默认车间（环境变量回退），Secret 掩码返回 */
export async function fetchInspectionFeishuConfigList(): Promise<InspectionFeishuConfigDetail[]> {
  const json = await getJson<InspectionFeishuConfigDetail[]>(`${BASE}/config-list`)
  return json.data ?? []
}

/** 保存飞书镜像配置（Secret 留空保留已保存值） */
export async function updateInspectionFeishuConfig(
  workshop: string,
  values: InspectionFeishuConfigUpdateRequest,
): Promise<InspectionFeishuConfigDetail> {
  const response = await fetch(
    `${BASE}/config?workshop=${encodeURIComponent(workshop)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    },
  )
  const json = await response.json()
  if (!response.ok || json.code !== 200) {
    throw new Error(json?.message || '保存配置失败')
  }
  return json.data
}

/** 测试飞书镜像连接 */
export async function testInspectionFeishuConfig(
  workshop: string,
): Promise<InspectionFeishuConfigTestResult> {
  const response = await fetch(
    `${BASE}/config/test?workshop=${encodeURIComponent(workshop)}`,
    { method: 'POST' },
  )
  const json = await response.json()
  if (!response.ok || json.code !== 200) {
    throw new Error(json?.message || '连接测试失败')
  }
  return json.data
}
