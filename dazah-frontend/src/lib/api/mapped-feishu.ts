import { serverApiUrl } from '@/lib/server-api'
import type { WarehouseDataset, WarehouseFeishuPageData } from '@/types/warehouse'

function mappedUrl(moduleCode: string, path: string): string {
  const normalized = `/api/v1/${encodeURIComponent(moduleCode)}${path}`
  return typeof window === 'undefined' ? serverApiUrl(normalized) : normalized
}

async function mappedFetch<T>(moduleCode: string, path: string): Promise<T> {
  const response = await fetch(mappedUrl(moduleCode, path), { cache: 'no-store' })
  const body = await response.json().catch(() => null)
  if (!response.ok || !body) {
    throw new Error(body?.message || `读取${moduleCode}本地飞书镜像失败`)
  }
  return body.data as T
}

export function fetchMappedPageData(
  moduleCode: string,
  pageKey: string,
): Promise<WarehouseFeishuPageData> {
  return mappedFetch(moduleCode, `/page-data/${encodeURIComponent(pageKey)}`)
}

export function fetchMappedPageDataset(
  moduleCode: string,
  pageKey: string,
  bindingId: string,
  params: {
    keyword?: string
    page?: number
    page_size?: number
    filters?: Array<{ field_id: string; operator: string; value: string }>
    sort_field?: string
    sort_direction?: 'asc' | 'desc'
  },
): Promise<WarehouseDataset> {
  const search = new URLSearchParams()
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  for (const filter of params.filters || []) {
    search.append('filter_field', filter.field_id)
    search.append('filter_operator', filter.operator)
    search.append('filter_value', filter.value)
  }
  if (params.sort_field) search.set('sort_field', params.sort_field)
  if (params.sort_direction) search.set('sort_direction', params.sort_direction)
  return mappedFetch(
    moduleCode,
    `/page-data/${encodeURIComponent(pageKey)}/${bindingId}/records?${search.toString()}`,
  )
}

export function mappedAttachmentUrl(
  moduleCode: string,
  pageKey: string,
  bindingId: string,
  recordId: string,
  fieldId: string,
  fileToken: string,
): string {
  return mappedUrl(
    moduleCode,
    `/page-data/${encodeURIComponent(pageKey)}/${bindingId}/record/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fieldId)}/${encodeURIComponent(fileToken)}`,
  )
}
