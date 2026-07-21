'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
// warehouse module Server Actions
import { revalidatePath } from 'next/cache'
import { cookies } from 'next/headers'

import type {
  WarehouseFeishuConfig,
  WarehouseFeishuConfigUpsert,
  WarehouseFeishuConnectivityResult,
  WarehouseFeishuTable,
  WarehouseFeishuTableBatchEnablePayload,
  WarehouseFeishuTableSyncResult,
  WarehouseFeishuWsStatus,
  WarehouseFeishuPageBindingInput,
  WarehouseFeishuPageData,
  WarehouseFeishuSourceRoot,
  WarehouseFeishuSourceRootInput,
  WarehouseAnalysisProfile,
  WarehouseAnalysisProfileInput,
  WarehouseAnalysisRun,
} from '@/types/warehouse'

const API_BASE = getServerApiBaseUrl()

interface ApiResponse<T> {
  code: number
  data: T
  message?: string
}

async function fetchWarehouseApi<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<ApiResponse<T>> {
  const cookieStore = await cookies()
  const token = cookieStore.get('auth_token')?.value

  const response = await fetch(`${API_BASE}/api/v1/warehouse${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
    cache: 'no-store',
  })
  const body = await response.json().catch(() => null)

  if (!response.ok || !body) {
    throw new Error(body?.message || `仓储接口请求失败：${response.status}`)
  }

  return body as ApiResponse<T>
}

export async function saveWarehouseFeishuConfig(
  data: WarehouseFeishuConfigUpsert,
) {
  const response = await fetchWarehouseApi<WarehouseFeishuConfig>('/feishu-config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  revalidatePath('/warehouse/feishu-config')
  return response
}

export async function testWarehouseFeishuConfig(
  data: WarehouseFeishuConfigUpsert,
) {
  return fetchWarehouseApi<WarehouseFeishuConnectivityResult>('/feishu-config/test', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function refreshWarehouseFeishuTables() {
  const response = await fetchWarehouseApi<WarehouseFeishuTable[]>(
    '/feishu/tables/refresh',
    { method: 'POST' },
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath('/warehouse/raw-material')
  revalidatePath('/warehouse/packaging')
  revalidatePath('/warehouse/product')
  return response
}

export async function setWarehouseFeishuTableEnabled(
  tableId: string,
  isEnabled: boolean,
) {
  const response = await fetchWarehouseApi<WarehouseFeishuTable>(
    `/feishu/tables/${tableId}/enabled`,
    {
      method: 'PATCH',
      body: JSON.stringify({ is_enabled: isEnabled }),
    },
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath('/warehouse/raw-material')
  revalidatePath('/warehouse/packaging')
  revalidatePath('/warehouse/product')
  return response
}

export async function setWarehouseFeishuTablesEnabled(
  tableIds: string[],
  isEnabled: boolean,
) {
  const body: WarehouseFeishuTableBatchEnablePayload = {
    table_ids: tableIds,
    is_enabled: isEnabled,
  }
  const response = await fetchWarehouseApi<WarehouseFeishuTable[]>(
    '/feishu/tables/enabled/batch',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath('/warehouse/raw-material')
  revalidatePath('/warehouse/packaging')
  revalidatePath('/warehouse/product')
  return response
}

export async function syncWarehouseFeishuTable(tableId: string) {
  const response = await fetchWarehouseApi<WarehouseFeishuTableSyncResult>(
    `/feishu/tables/${tableId}/sync`,
    { method: 'POST' },
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath('/warehouse/raw-material')
  revalidatePath('/warehouse/packaging')
  revalidatePath('/warehouse/product')
  return response
}

export async function restartWarehouseFeishuWs() {
  return fetchWarehouseApi<WarehouseFeishuWsStatus>('/feishu/ws/restart', {
    method: 'POST',
  })
}

export async function createWarehouseFeishuSourceRoot(
  data: WarehouseFeishuSourceRootInput,
) {
  const response = await fetchWarehouseApi<WarehouseFeishuSourceRoot>(
    '/feishu/roots',
    { method: 'POST', body: JSON.stringify(data) },
  )
  revalidatePath('/warehouse/feishu-config')
  return response
}

export async function discoverWarehouseFeishuSourceRoot(rootId: string) {
  const response = await fetchWarehouseApi<WarehouseFeishuTable[]>(
    `/feishu/roots/${rootId}/discover`,
    { method: 'POST' },
  )
  revalidatePath('/warehouse/feishu-config')
  return response
}

export async function deleteWarehouseFeishuSourceRoot(rootId: string) {
  const response = await fetchWarehouseApi<{ id: string }>(
    `/feishu/roots/${rootId}`,
    { method: 'DELETE' },
  )
  revalidatePath('/warehouse/feishu-config')
  return response
}

export async function replaceWarehousePageBindings(
  pageKey: string,
  bindings: WarehouseFeishuPageBindingInput[],
) {
  const response = await fetchWarehouseApi<WarehouseFeishuPageData>(
    `/page-data/${encodeURIComponent(pageKey)}`,
    { method: 'PUT', body: JSON.stringify({ bindings }) },
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath('/warehouse/raw-material')
  revalidatePath('/warehouse/packaging')
  revalidatePath('/warehouse/product')
  return response
}

export async function createWarehouseAnalysisProfile(
  data: WarehouseAnalysisProfileInput,
) {
  const response = await fetchWarehouseApi<WarehouseAnalysisProfile>(
    '/analysis/profiles',
    { method: 'POST', body: JSON.stringify(data) },
  )
  revalidatePath('/warehouse/feishu-config')
  return response
}

export async function runWarehouseAnalysisProfile(profileId: string) {
  return fetchWarehouseApi<WarehouseAnalysisRun>(
    `/analysis/profiles/${profileId}/run`,
    { method: 'POST' },
  )
}
