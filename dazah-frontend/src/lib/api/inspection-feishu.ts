'use client'

import type {
  FeishuAppCreateRequest,
  FeishuAppItem,
  FeishuAppUpdateRequest,
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

/** 自建应用库清单（Secret 不回显明文） */
export async function fetchFeishuApps(): Promise<FeishuAppItem[]> {
  const json = await getJson<FeishuAppItem[]>(`${BASE}/apps`)
  return json.data ?? []
}

async function mutateFeishuApp(
  url: string,
  method: 'POST' | 'PUT' | 'DELETE',
  errorMessage: string,
  body?: FeishuAppCreateRequest | FeishuAppUpdateRequest,
): Promise<FeishuAppItem | null> {
  const response = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || !json || json.code !== 200) {
    throw new Error(json?.message || errorMessage)
  }
  return json.data ?? null
}

/** 新建自建应用凭据 */
export function createFeishuApp(data: FeishuAppCreateRequest): Promise<FeishuAppItem | null> {
  return mutateFeishuApp(`${BASE}/apps`, 'POST', '新建应用失败', data)
}

/** 更新自建应用凭据（Secret 留空保留已保存值） */
export function updateFeishuApp(
  appId: string,
  data: FeishuAppUpdateRequest,
): Promise<FeishuAppItem | null> {
  return mutateFeishuApp(`${BASE}/apps/${appId}`, 'PUT', '更新应用失败', data)
}

/** 删除自建应用凭据（仍被巡检配置引用时后端拒绝） */
export function deleteFeishuApp(appId: string): Promise<FeishuAppItem | null> {
  return mutateFeishuApp(`${BASE}/apps/${appId}`, 'DELETE', '删除应用失败')
}
