import { serverApiUrl } from '@/lib/server-api'
import type {
  DormitoryCheckinInput,
  DormitoryCheckinResult,
  DormitoryOccupancyStats,
  DormitoryRoomRecommendation,
} from '@/types/administration'
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

async function mappedPostJson<T>(
  moduleCode: string,
  path: string,
  payload: unknown,
): Promise<T> {
  const response = await fetch(mappedUrl(moduleCode, path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    cache: 'no-store',
  })
  const body = await response.json().catch(() => null)
  if (!response.ok || !body) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    throw new Error(detail || body?.message || `请求失败（${response.status}）`)
  }
  return body.data as T
}

/** 宿舍入住率仪表盘统计（含空房/满人房间列表）。 */
export function fetchDormitoryStats(
  moduleCode: string,
): Promise<DormitoryOccupancyStats> {
  return mappedFetch(moduleCode, '/dormitory/dashboard-stats')
}

/** AI 推荐入住房间（候选已按性别/住宿标准/空床位过滤，LLM 只排序）。 */
export function recommendDormitoryRooms(
  moduleCode: string,
  payload: Partial<DormitoryCheckinInput>,
): Promise<DormitoryRoomRecommendation> {
  return mappedPostJson(moduleCode, '/dormitory/checkin-recommend', payload)
}

/** 确认办理入住：回写飞书员工住宿退宿清单并触发镜像同步。 */
export function submitDormitoryCheckin(
  moduleCode: string,
  payload: DormitoryCheckinInput,
): Promise<DormitoryCheckinResult> {
  return mappedPostJson(moduleCode, '/dormitory/checkin', payload)
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

/** 批量解析镜像人员头像（按企业邮箱），返回 {email: avatar_url}。 */
export async function fetchPersonAvatars(
  moduleCode: string,
  emails: string[],
): Promise<Record<string, string>> {
  if (!emails.length) return {}
  const search = new URLSearchParams()
  for (const email of emails) search.append('emails', email)
  return mappedFetch<Record<string, string>>(
    moduleCode,
    `/feishu-read/person-avatars?${search.toString()}`,
  )
}


export interface MappedExportParams {
  format: 'xlsx' | 'pdf'
  columns?: string[]
  filters?: Array<{ field_id: string; operator: string; value: string }>
  sort_field?: string
  sort_direction?: string
}

/** 按当前筛选/排序导出全量记录（Excel/PDF，含图片与头像）。 */
export async function fetchMappedPageExport(
  moduleCode: string,
  pageKey: string,
  bindingId: string,
  params: MappedExportParams,
): Promise<Blob> {
  const search = new URLSearchParams()
  search.set('format', params.format)
  if (params.columns?.length) search.set('columns', params.columns.join(','))
  if (params.sort_field) search.set('sort_field', params.sort_field)
  if (params.sort_direction) search.set('sort_direction', params.sort_direction)
  for (const filter of params.filters || []) {
    search.append('filter_field', filter.field_id)
    search.append('filter_operator', filter.operator)
    search.append('filter_value', filter.value)
  }
  const response = await fetch(
    mappedUrl(moduleCode, `/page-data/${encodeURIComponent(pageKey)}/${encodeURIComponent(bindingId)}/export?${search.toString()}`),
    { cache: 'no-store' },
  )
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { message?: string } | null
    throw new Error(body?.message || `导出失败（${response.status}）`)
  }
  return response.blob()
}
