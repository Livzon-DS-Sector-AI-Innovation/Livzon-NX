/**
 * 仓储模块 - 客户端 API（浏览器只读 GET，使用相对路径 /api/v1/...）
 * 缓存由 React Query 管理，不在此层设置 fetch cache。
 */

import type {
  WarehouseDashboardData,
  WarehouseDashboardGroup,
  WarehouseFeishuMaterialPageData,
  WarehouseHardwareCostAnomalyItem,
  WarehouseHardwareCostSummary,
  WarehouseMaterialPageQueryParams,
  WarehousePageFeishuConfig,
  WarehouseRecordDetail,
  WarehouseTrendAnomalyItem,
  WarehouseTrendProductLineItem,
  WarehouseTrendSummary,
} from '@/types/warehouse'
import { normalizeWarehouseDashboard } from '@/lib/warehouse-dashboard'

export async function fetchWarehouseDashboard(
  group: WarehouseDashboardGroup,
  force = false,
  detail = false
): Promise<WarehouseDashboardData> {
  const query = `group=${group}${force ? '&force=1' : ''}${detail ? '&detail=1' : ''}`
  const res = await fetch(`/api/v1/warehouse/dashboard?${query}`)
  if (!res.ok) {
    throw new Error('获取仓储仪表盘数据失败')
  }
  const body = await res.json()
  return normalizeWarehouseDashboard(group, body.data)
}

export async function fetchWarehousePageFeishuConfigs(): Promise<WarehousePageFeishuConfig[]> {
  const res = await fetch('/api/v1/warehouse/page-feishu-configs')
  if (!res.ok) throw new Error('获取页面飞书配置失败')
  const body = await res.json()
  return body.data
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
    `/api/v1/warehouse/material-pages/${pageKey}?${searchParams.toString()}`,
    {
      ...(timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {}),
    }
  )
  if (!res.ok) {
    throw new Error('获取仓储页面数据失败')
  }
  const body = await res.json()
  return body.data as WarehouseFeishuMaterialPageData
}

export async function fetchWarehouseRecordDetail(
  pageKey: string,
  recordId: string,
  timeoutMs?: number
): Promise<WarehouseRecordDetail> {
  const res = await fetch(
    `/api/v1/warehouse/material-pages/${pageKey}/records/${recordId}`,
    {
      ...(timeoutMs ? { signal: AbortSignal.timeout(timeoutMs) } : {}),
    }
  )
  if (!res.ok) {
    throw new Error('获取仓储记录详情失败')
  }
  const body = await res.json()
  return body.data as WarehouseRecordDetail
}

export async function fetchWarehouseTrendSummary(): Promise<WarehouseTrendSummary> {
  const res = await fetch('/api/v1/warehouse/ai/trend-summary')
  if (!res.ok) {
    throw new Error('获取仓储趋势概览失败')
  }
  const body = await res.json()
  return body.data as WarehouseTrendSummary
}

export async function fetchWarehouseTrendAnomalies(): Promise<WarehouseTrendAnomalyItem[]> {
  const res = await fetch('/api/v1/warehouse/ai/trend-anomalies')
  if (!res.ok) {
    throw new Error('获取仓储趋势异常失败')
  }
  const body = await res.json()
  return (body.data || []) as WarehouseTrendAnomalyItem[]
}

export async function fetchWarehouseTrendProductLines(): Promise<WarehouseTrendProductLineItem[]> {
  const res = await fetch('/api/v1/warehouse/ai/trend-product-lines')
  if (!res.ok) {
    throw new Error('获取产品线趋势失败')
  }
  const body = await res.json()
  return (body.data || []) as WarehouseTrendProductLineItem[]
}

export async function fetchWarehouseHardwareCostAnomalies(): Promise<WarehouseHardwareCostAnomalyItem[]> {
  const res = await fetch('/api/v1/warehouse/ai/hardware-cost-anomalies')
  if (!res.ok) {
    throw new Error('获取五金费用异常失败')
  }
  const body = await res.json()
  return (body.data || []) as WarehouseHardwareCostAnomalyItem[]
}

export async function fetchWarehouseHardwareCostSummary(): Promise<WarehouseHardwareCostSummary> {
  const res = await fetch('/api/v1/warehouse/ai/hardware-cost-summary')
  if (!res.ok) {
    throw new Error('获取五金费用概览失败')
  }
  const body = await res.json()
  return body.data as WarehouseHardwareCostSummary
}
