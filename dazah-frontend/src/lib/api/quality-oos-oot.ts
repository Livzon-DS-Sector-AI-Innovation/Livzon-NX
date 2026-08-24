import type { components } from '@/types/generated/schema'
import type {
  OosOotRecordListResponse as LocalOosOotRecordListResponse,
  OotLimitProductListResponse as LocalOotLimitProductListResponse,
  OotLimitItemListResponse as LocalOotLimitItemListResponse,
} from '@/types/quality'

export type OosOotRecord = components['schemas']['OosOotRecordOut']
export type OosOotRecordListResponse = LocalOosOotRecordListResponse
export type OotLimitProduct = components['schemas']['OotLimitProductOut']
export type OotLimitProductListResponse = LocalOotLimitProductListResponse
export type OotLimitItem = components['schemas']['OotLimitItemOut']
export type OotLimitItemListResponse = LocalOotLimitItemListResponse

async function oosOotGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`读取 OOS/OOT 数据失败：${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function fetchOosOotRecords(params: {
  recordType?: 'OOS' | 'OOT'
  status?: 'open' | 'investigating' | 'closed'
  keyword?: string
  page?: number
  pageSize?: number
}): Promise<OosOotRecordListResponse> {
  const search = new URLSearchParams()
  if (params.recordType) search.set('record_type', params.recordType)
  if (params.status) search.set('status', params.status)
  if (params.keyword) search.set('keyword', params.keyword)
  search.set('page', String(params.page ?? 1))
  search.set('page_size', String(params.pageSize ?? 20))
  return oosOotGet<OosOotRecordListResponse>(
    `/api/v1/quality/oos-oot/records?${search.toString()}`,
  )
}

export async function fetchOotLimitProducts(): Promise<OotLimitProductListResponse> {
  return oosOotGet<OotLimitProductListResponse>('/api/v1/quality/oos-oot/oot-limits/products')
}

export async function fetchOotLimitItems(productId: string): Promise<OotLimitItemListResponse> {
  return oosOotGet<OotLimitItemListResponse>(
    `/api/v1/quality/oos-oot/oot-limits/products/${productId}/items`,
  )
}
