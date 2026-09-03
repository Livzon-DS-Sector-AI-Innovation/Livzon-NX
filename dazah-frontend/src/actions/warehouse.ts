'use server'

import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import type { WarehousePageFeishuConfig } from '@/types/warehouse'

type WarehouseFeishuConfigInput = {
  id?: string | null
  config_name: string
  app_id: string
  app_secret?: string
  is_active: boolean
  timezone: string
  daily_sync_time: string
  remark?: string | null
}

type WarehouseFeishuConfig = WarehouseFeishuConfigInput & {
  id?: string | null
  app_secret_configured: boolean
  app_secret_masked?: string
}

type WarehouseConnectivityResult = {
  ok: boolean
  steps: Array<{ name: string; status: string; message: string }>
}

type WarehouseRootInput = {
  name: string
  source_type: 'wiki' | 'base'
  source_url: string
}

type WarehouseBinding = {
  resource_id: string
  tab_name: string
  sort_order: number
  is_default: boolean
  is_enabled: boolean
  visible_field_ids: string[]
}

const API_BASE =
  process.env.API_BASE_URL ||
  process.env.INTERNAL_API_BASE_URL ||
  'http://dazah-backend-app-1:8000'

/**
 * 仓储模块 Server Actions（写操作）。
 * 所有写操作必须通过本文件（前端规范：写操作必须用 Server Actions，禁止客户端直接 fetch 写接口）。
 * 认证：读取 auth_token cookie 并携带 Bearer 头转发（与 actions/hr.ts 的 hrActionFetch 一致）；
 * 无 token 时不抛错直接请求——开发环境 DEV_BYPASS_AUTH 后端放行，生产环境后端返回 401 兜底。
 */

async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const authHeaders = await getAuthHeaders()
  if (init?.body instanceof FormData) delete authHeaders['Content-Type']
  const headers: Record<string, string> = {
    ...authHeaders,
    ...(init?.headers as Record<string, string> | undefined),
  }
  return fetch(`${API_BASE}/api/v1${path}`, { ...init, headers, cache: 'no-store' })
}

async function handleResponse(res: Response): Promise<unknown> {
  if (!res.ok) {
    let detail = `请求失败 (${res.status})`
    try {
      const json = await res.json()
      if (json?.message) detail = json.message
      else if (json?.detail) detail = json.detail
    } catch {
      // ignore parse error
    }
    throw new Error(detail)
  }
  try {
    const json = await res.json()
    return json.data
  } catch {
    return null
  }
}

async function handleTypedResponse<T>(res: Response): Promise<T> {
  return (await handleResponse(res)) as T
}

export async function saveWarehouseFeishuConfigAction(
  values: WarehouseFeishuConfigInput,
): Promise<WarehouseFeishuConfig> {
  const result = await handleTypedResponse<WarehouseFeishuConfig>(
    await authedFetch('/warehouse/feishu-config', {
      method: 'PUT',
      body: JSON.stringify(values),
    }),
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath('/warehouse/settings')
  return result
}

export async function testWarehouseFeishuConfigAction(
  values: WarehouseFeishuConfigInput,
): Promise<WarehouseConnectivityResult> {
  return handleTypedResponse<WarehouseConnectivityResult>(
    await authedFetch('/warehouse/feishu-config/test', {
      method: 'POST',
      body: JSON.stringify(values),
    }),
  )
}

export async function createWarehouseFeishuRootAction(
  values: WarehouseRootInput,
): Promise<unknown> {
  const result = await handleResponse(
    await authedFetch('/warehouse/feishu/roots', {
      method: 'POST',
      body: JSON.stringify(values),
    }),
  )
  revalidatePath('/warehouse/feishu-config')
  return result
}

export async function deleteWarehouseFeishuRootAction(rootId: string): Promise<unknown> {
  const result = await handleResponse(
    await authedFetch(`/warehouse/feishu/roots/${encodeURIComponent(rootId)}`, {
      method: 'DELETE',
    }),
  )
  revalidatePath('/warehouse/feishu-config')
  return result
}

export async function discoverWarehouseFeishuRootAction(rootId: string): Promise<unknown> {
  const result = await handleResponse(
    await authedFetch(`/warehouse/feishu/roots/${encodeURIComponent(rootId)}/discover`, {
      method: 'POST',
    }),
  )
  revalidatePath('/warehouse/feishu-config')
  return result
}

export async function syncWarehouseFeishuTableAction(tableId: string): Promise<unknown> {
  const result = await handleResponse(
    await authedFetch(`/warehouse/feishu/tables/${encodeURIComponent(tableId)}/sync`, {
      method: 'POST',
    }),
  )
  revalidatePath('/warehouse/feishu-config')
  return result
}

export async function syncWarehouseFeishuTablesAction(tableIds: string[]): Promise<unknown[]> {
  return Promise.all(tableIds.map((tableId) => syncWarehouseFeishuTableAction(tableId)))
}

export async function saveWarehousePageBindingsAction(
  pageKey: string,
  bindings: WarehouseBinding[],
): Promise<unknown> {
  const result = await handleResponse(
    await authedFetch(`/warehouse/page-data/${encodeURIComponent(pageKey)}`, {
      method: 'PUT',
      body: JSON.stringify({
        bindings: bindings.map((item) => ({
          table_pk: item.resource_id,
          tab_label: item.tab_name,
          display_order: item.sort_order,
          is_default: item.is_default,
          is_enabled: item.is_enabled,
          visible_field_ids: item.visible_field_ids,
          default_sort: [],
          history_mode: 'current_mirror',
        })),
      }),
    }),
  )
  revalidatePath('/warehouse/feishu-config')
  revalidatePath(`/warehouse/${pageKey}`)
  return result
}

export async function chatWarehouseAiAction(question: string): Promise<{ response: string }> {
  return handleTypedResponse<{ response: string }>(
    await authedFetch('/warehouse/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  )
}

/**
 * 编辑仓储记录并写回飞书多维表格（PUT）。
 */
export async function updateWarehouseRecordAction(
  pageKey: string,
  recordId: string,
  fields: Record<string, unknown>
): Promise<unknown> {
  return handleResponse(
    await authedFetch(`/warehouse/material-pages/${pageKey}/records/${recordId}`, {
      method: 'PUT',
      body: JSON.stringify({ fields }),
    })
  )
}

/**
 * 删除仓储记录并同步删除飞书多维表格记录（DELETE）。
 */
export async function deleteWarehouseRecordAction(
  pageKey: string,
  recordId: string
): Promise<unknown> {
  return handleResponse(
    await authedFetch(`/warehouse/material-pages/${pageKey}/records/${recordId}`, {
      method: 'DELETE',
    })
  )
}

/**
 * 更新页面飞书多维表格配置（PUT），保存后立即生效。
 * 后端 schema WarehousePageFeishuConfig 要求 body 含 page_key（必填），URL 路径参数用于路由。
 */
export async function updateWarehousePageFeishuConfigAction(
  pageKey: string,
  config: Omit<WarehousePageFeishuConfig, 'page_key'>
): Promise<unknown> {
  const result = await handleResponse(
    await authedFetch(`/warehouse/page-feishu-configs/${pageKey}`, {
      method: 'PUT',
      body: JSON.stringify({ ...config, page_key: pageKey }),
    })
  )
  revalidatePath('/warehouse/settings')
  return result
}
