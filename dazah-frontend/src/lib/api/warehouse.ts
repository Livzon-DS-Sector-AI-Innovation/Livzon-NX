import type {
  PackagingMaterial,
  PackagingMaterialListResponse,
  ProductInventory,
  ProductInventoryListResponse,
  RawMaterial,
  RawMaterialListResponse,
  WarehouseFeishuBusinessDomain,
  WarehouseFeishuConfig,
  WarehouseFeishuRawRecordData,
  WarehouseFeishuTable,
  WarehouseFeishuWsStatus,
  WarehouseDataset,
  WarehouseFeishuPageData,
  WarehouseFeishuSourceRoot,
} from '@/types/warehouse'
import { serverApiUrl } from '@/lib/server-api'

function buildWarehouseUrl(path: string): string {
  const normalizedPath = `/api/v1/warehouse${path.startsWith('/') ? path : `/${path}`}`

  if (typeof window !== 'undefined') {
    return normalizedPath
  }

  return serverApiUrl(normalizedPath)
}

async function apiFetch<T>(
  path: string,
  fallbackMessage: string,
  requestHeaders?: HeadersInit,
): Promise<T> {
  const response = await fetch(buildWarehouseUrl(path), {
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...requestHeaders,
    },
  })
  const body = await response.json().catch(() => null)

  if (!response.ok || !body) {
    throw new Error(body?.message || fallbackMessage)
  }

  return body as T
}

export async function fetchModuleInfo(): Promise<{
  code: string
  name: string
  description: string
}> {
  const body = await apiFetch<{
    data: { code: string; name: string; description: string }
  }>('/', '获取仓储模块信息失败')
  return body.data
}

export async function fetchRawMaterials(): Promise<RawMaterial[]> {
  const body = await apiFetch<RawMaterialListResponse>(
    '/raw-materials',
    '获取原辅料库存失败',
  )
  return body.data || []
}

export async function fetchPackagingMaterials(): Promise<PackagingMaterial[]> {
  const body = await apiFetch<PackagingMaterialListResponse>(
    '/packaging-materials',
    '获取包材库存失败',
  )
  return body.data || []
}

export async function fetchProducts(): Promise<ProductInventory[]> {
  const body = await apiFetch<ProductInventoryListResponse>(
    '/products',
    '获取成品库存失败',
  )
  return body.data || []
}

export async function fetchWarehouseFeishuConfig(
  requestHeaders?: HeadersInit,
): Promise<WarehouseFeishuConfig> {
  const body = await apiFetch<{ data: WarehouseFeishuConfig }>(
    '/feishu-config',
    '获取仓储飞书配置失败',
    requestHeaders,
  )
  return body.data
}

export async function fetchWarehouseFeishuTables(
  requestHeaders?: HeadersInit,
): Promise<WarehouseFeishuTable[]> {
  return fetchWarehouseFeishuTablesByParams(undefined, requestHeaders)
}

export async function fetchWarehouseFeishuTablesByParams(
  params?: {
    business_domain?: WarehouseFeishuBusinessDomain
    keyword?: string
    enabled?: boolean
  },
  requestHeaders?: HeadersInit,
): Promise<WarehouseFeishuTable[]> {
  const search = new URLSearchParams()
  if (params?.business_domain) {
    search.set('business_domain', params.business_domain)
  }
  if (params?.keyword) {
    search.set('keyword', params.keyword)
  }
  if (params?.enabled !== undefined) {
    search.set('enabled', String(params.enabled))
  }
  const suffix = search.toString() ? `?${search.toString()}` : ''
  const body = await apiFetch<{ data: WarehouseFeishuTable[] }>(
    `/feishu/tables${suffix}`,
    '获取仓储飞书表目录失败',
    requestHeaders,
  )
  return body.data || []
}

export async function fetchWarehouseFeishuDomainRecords(
  businessDomain: WarehouseFeishuBusinessDomain,
  params?: {
    table_id?: string
    keyword?: string
    field?: string
    field_operator?: string
    field_value?: string
    page?: number
    page_size?: number
  },
  requestHeaders?: HeadersInit,
): Promise<WarehouseFeishuRawRecordData> {
  const search = new URLSearchParams()
  if (params?.table_id) search.set('table_id', params.table_id)
  if (params?.keyword) search.set('keyword', params.keyword)
  if (params?.field) search.set('field', params.field)
  if (params?.field_operator) search.set('field_operator', params.field_operator)
  if (params?.field_value) search.set('field_value', params.field_value)
  if (params?.page) search.set('page', String(params.page))
  if (params?.page_size) search.set('page_size', String(params.page_size))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  const body = await apiFetch<{ data: WarehouseFeishuRawRecordData }>(
    `/feishu/domains/${businessDomain}/records${suffix}`,
    '获取仓储飞书原始记录失败',
    requestHeaders,
  )
  return body.data
}

export function warehouseAttachmentUrl(
  pageKey: string,
  bindingId: string,
  recordId: string,
  fieldId: string,
  fileToken: string,
): string {
  return buildWarehouseUrl(
    `/page-data/${encodeURIComponent(pageKey)}/${bindingId}/record/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fieldId)}/${encodeURIComponent(fileToken)}`,
  )
}

export async function fetchWarehouseFeishuTableRecords(
  tableId: string,
  params?: {
    keyword?: string
    field?: string
    field_operator?: string
    field_value?: string
    page?: number
    page_size?: number
  },
): Promise<WarehouseFeishuRawRecordData> {
  const search = new URLSearchParams()
  if (params?.keyword) search.set('keyword', params.keyword)
  if (params?.field) search.set('field', params.field)
  if (params?.field_operator) search.set('field_operator', params.field_operator)
  if (params?.field_value) search.set('field_value', params.field_value)
  if (params?.page) search.set('page', String(params.page))
  if (params?.page_size) search.set('page_size', String(params.page_size))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  const body = await apiFetch<{ data: WarehouseFeishuRawRecordData }>(
    `/feishu/tables/${tableId}/records${suffix}`,
    '获取仓储飞书原始记录失败',
  )
  return body.data
}

export async function fetchWarehouseFeishuWsStatus(): Promise<WarehouseFeishuWsStatus> {
  const body = await apiFetch<{ data: WarehouseFeishuWsStatus }>(
    '/feishu/ws/status',
    '获取仓储飞书长连接状态失败',
  )
  return body.data
}

export async function fetchWarehouseFeishuSourceRoots(
  requestHeaders?: HeadersInit,
): Promise<WarehouseFeishuSourceRoot[]> {
  const body = await apiFetch<{ data: WarehouseFeishuSourceRoot[] }>(
    '/feishu/roots',
    '获取仓储飞书数据入口失败',
    requestHeaders,
  )
  return body.data || []
}

export async function fetchWarehousePageData(
  pageKey: string,
  requestHeaders?: HeadersInit,
): Promise<WarehouseFeishuPageData> {
  const body = await apiFetch<{ data: WarehouseFeishuPageData }>(
    `/page-data/${encodeURIComponent(pageKey)}`,
    '获取页面数据表绑定失败',
    requestHeaders,
  )
  return body.data
}

export async function fetchWarehousePageDataset(
  pageKey: string,
  bindingId: string,
  params?: {
    keyword?: string
    field?: string
    field_operator?: string
    field_value?: string
    page?: number
    page_size?: number
    filters?: Array<{ field_id: string; operator: string; value: string }>
    sort_field?: string
    sort_direction?: 'asc' | 'desc'
  },
): Promise<WarehouseDataset> {
  const search = new URLSearchParams()
  if (params?.keyword) search.set('keyword', params.keyword)
  if (params?.field) search.set('field', params.field)
  if (params?.field_operator) search.set('field_operator', params.field_operator)
  if (params?.field_value) search.set('field_value', params.field_value)
  if (params?.page) search.set('page', String(params.page))
  if (params?.page_size) search.set('page_size', String(params.page_size))
  for (const filter of params?.filters || []) {
    search.append('filter_field', filter.field_id)
    search.append('filter_operator', filter.operator)
    search.append('filter_value', filter.value)
  }
  if (params?.sort_field) search.set('sort_field', params.sort_field)
  if (params?.sort_direction) search.set('sort_direction', params.sort_direction)
  const suffix = search.size ? `?${search.toString()}` : ''
  const body = await apiFetch<{ data: WarehouseDataset }>(
    `/page-data/${encodeURIComponent(pageKey)}/${bindingId}/records${suffix}`,
    '读取页面数据失败',
  )
  return body.data
}
