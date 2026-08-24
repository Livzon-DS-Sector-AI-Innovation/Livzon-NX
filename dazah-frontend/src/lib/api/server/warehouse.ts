/**
 * 仓储模块 - 服务器端 API（Server Component / Server Action 使用 API_BASE_URL）
 */

import { cookies } from 'next/headers'
import type {
  PackagingMaterial,
  ProductInventory,
  RawMaterial,
  WarehouseDashboardData,
  WarehouseDashboardGroup,
  WarehouseFeishuMaterialPageData,
  WarehouseMaterialPageQueryParams,
  WarehousePageFeishuConfig,
} from '@/types/warehouse'
import { normalizeWarehouseDashboard } from '@/lib/warehouse-dashboard'

const API_BASE = process.env.API_BASE_URL || 'http://dazah-backend-app-1:8000'

/** 服务端读取 auth_token cookie，供请求后端时携带 Bearer 认证头 */
async function getAuthHeaders(): Promise<Record<string, string> | undefined> {
  const cookieStore = await cookies()
  const token = cookieStore.get('auth_token')?.value
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

export async function fetchWarehouseDashboard(
  group: WarehouseDashboardGroup,
  force = false,
  detail = false
): Promise<WarehouseDashboardData> {
  const query = `group=${group}${force ? '&force=1' : ''}${detail ? '&detail=1' : ''}`
  const res = await fetch(`${API_BASE}/api/v1/warehouse/dashboard?${query}`, {
    cache: 'no-store',
    headers: await getAuthHeaders(),
    // SSR 限时：冷启动全量拉取可能超 20s，超时降级由客户端组件补拉
    signal: AbortSignal.timeout(20000),
  })
  if (!res.ok) {
    throw new Error('获取仓储仪表盘数据失败')
  }
  const body = await res.json()
  return normalizeWarehouseDashboard(group, body.data)
}

export async function fetchWarehousePageFeishuConfigs(): Promise<WarehousePageFeishuConfig[]> {
  const res = await fetch(`${API_BASE}/api/v1/warehouse/page-feishu-configs`, {
    cache: 'no-store',
    headers: await getAuthHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取页面飞书配置失败')
  }
  const body = await res.json()
  return body.data
}

// ---- 库存映射工具（与后端字段保持一致）----

function toNumber(value: unknown): number {
  return typeof value === 'number' ? value : Number(value || 0)
}

function toText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

function toNullableText(value: unknown): string | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  return String(value)
}

type ApiWarehouseItem = Record<string, unknown>

function mapRawMaterial(item: ApiWarehouseItem): RawMaterial {
  return {
    id: toText(item.id),
    sourceId: toNullableText(item.source_id),
    code: toText(item.code),
    name: toText(item.name),
    spec: toText(item.spec),
    unit: toText(item.unit),
    available: toNumber(item.available),
    safety: toNumber(item.safety),
    lastMonth: toNumber(item.last_month),
    twoMonthsAgo: toNumber(item.two_months_ago),
    todayBalance: toNumber(item.today_balance),
    frontStock: toNumber(item.front_stock),
    thisMonthUse: toNumber(item.this_month_use),
    warning: toText(item.warning),
    product: toText(item.product_line),
    erp: item.erp_no ? String(item.erp_no) : null,
    delivery: toText(item.delivery),
    remark: toText(item.remark),
  }
}

function mapPackagingMaterial(item: ApiWarehouseItem): PackagingMaterial {
  return {
    id: toText(item.id),
    sourceId: toNullableText(item.source_id),
    code: toText(item.code),
    name: toText(item.name),
    spec: toText(item.spec),
    batch: toText(item.batch),
    available: toNumber(item.available),
    safety: toNumber(item.safety),
    lastMonth: toNumber(item.last_month),
    twoMonthsAgo: toNumber(item.two_months_ago),
    todayBalance: toNumber(item.today_balance),
    frontStock: toNumber(item.front_stock),
    thisMonthUse: toNumber(item.this_month_use),
    warning: toText(item.warning),
    product: toText(item.product_line),
    erp: item.erp_no ? String(item.erp_no) : null,
    delivery: toText(item.delivery),
    remark: toText(item.remark),
  }
}

function mapProduct(item: ApiWarehouseItem): ProductInventory {
  return {
    id: toText(item.id),
    sourceId: toNullableText(item.source_id),
    name: toText(item.name),
    spec: toText(item.spec),
    orderQty: toNumber(item.order_quantity),
    pending: toNumber(item.pending_quantity),
    qualified: toNumber(item.qualified_quantity),
    subtotal: toNumber(item.subtotal_quantity),
    remaining: toNumber(item.remaining_quantity),
    unit: toText(item.unit),
    remark: toText(item.remark),
  }
}

export async function fetchRawMaterials(): Promise<RawMaterial[]> {
  const res = await fetch(`${API_BASE}/api/v1/warehouse/raw-materials`, {
    cache: 'no-store',
    headers: await getAuthHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取原辅料库存失败')
  }
  const body = await res.json()
  return (body.data || []).map(mapRawMaterial)
}

export async function fetchPackagingMaterials(): Promise<PackagingMaterial[]> {
  const res = await fetch(`${API_BASE}/api/v1/warehouse/packaging-materials`, {
    cache: 'no-store',
    headers: await getAuthHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取包材库存失败')
  }
  const body = await res.json()
  return (body.data || []).map(mapPackagingMaterial)
}

export async function fetchProducts(): Promise<ProductInventory[]> {
  const res = await fetch(`${API_BASE}/api/v1/warehouse/products`, {
    cache: 'no-store',
    headers: await getAuthHeaders(),
  })
  if (!res.ok) {
    throw new Error('获取成品库存失败')
  }
  const body = await res.json()
  return (body.data || []).map(mapProduct)
}

export async function fetchWarehouseMaterialPage(
  pageKey: string,
  params?: WarehouseMaterialPageQueryParams,
  timeoutMs?: number
): Promise<WarehouseFeishuMaterialPageData> {
  const searchParams = new URLSearchParams()
  searchParams.set('page', String(params?.page ?? 1))
  searchParams.set('page_size', String(params?.page_size ?? 200))

  if (params?.source) {
    searchParams.set('source', params.source)
  }
  if (params?.force) {
    searchParams.set('force', '1')
  }
  if (params?.keyword) {
    searchParams.set('keyword', params.keyword)
  }
  if (params?.start_date) {
    searchParams.set('start_date', params.start_date)
  }
  if (params?.end_date) {
    searchParams.set('end_date', params.end_date)
  }
  if (params?.date_field) {
    searchParams.set('date_field', params.date_field)
  }
  if (params?.product) {
    searchParams.set('product', params.product)
  }
  if (params?.area) {
    searchParams.set('area', params.area)
  }
  if (params?.quality_status) {
    searchParams.set('quality_status', params.quality_status)
  }
  if (params?.warning_status) {
    searchParams.set('warning_status', params.warning_status)
  }
  if (params?.material_category) {
    searchParams.set('material_category', params.material_category)
  }
  if (params?.filters?.length) {
    searchParams.set('filters', JSON.stringify(params.filters))
  }

  const res = await fetch(
    `${API_BASE}/api/v1/warehouse/material-pages/${pageKey}?${searchParams.toString()}`,
    {
      cache: 'no-store',
      headers: await getAuthHeaders(),
      ...(timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {}),
    }
  )
  if (!res.ok) {
    throw new Error('获取仓储页面数据失败')
  }
  const body = await res.json()
  return body.data as WarehouseFeishuMaterialPageData
}
