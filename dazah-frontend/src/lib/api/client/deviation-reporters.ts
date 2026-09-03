import type { components } from '@/types/generated/schema'

export async function fetchDeviationReporters(keyword: string, signal?: AbortSignal): Promise<components['schemas']['ApiResponseEnvelope_list_DeviationReporterOption__']> {
  const params = new URLSearchParams({ page: '1', page_size: '50' })
  if (keyword.trim()) params.set('keyword', keyword.trim())
  const response = await fetch(`/api/v1/quality/deviations/reporter-options?${params}`, { signal })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null
    throw new Error(typeof detail === 'string' ? detail : '报告人列表加载失败，请重试')
  }
  return response.json()
}
