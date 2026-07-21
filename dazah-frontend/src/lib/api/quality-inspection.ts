import type { components, operations } from '@/types/generated/schema'

export type InspectionDashboardResponse =
  components['schemas']['InspectionDashboardResponse']
export type InspectionTrendResponse = components['schemas']['InspectionTrendResponse']
export type InspectionTrendParams =
  operations['get_inspection_trend_api_v1_quality_inspection_trends_get']['parameters']['query']

async function inspectionGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`读取检验数据失败：${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export async function fetchInspectionDashboard(): Promise<InspectionDashboardResponse> {
  return inspectionGet<InspectionDashboardResponse>('/api/v1/quality/inspection-dashboard')
}

export async function fetchInspectionTrend(
  params: InspectionTrendParams,
): Promise<InspectionTrendResponse> {
  const searchParams = new URLSearchParams({ resource_code: params.resource_code })
  if (params.subject) searchParams.set('subject', params.subject)
  if (params.inspection_item) {
    searchParams.set('inspection_item', params.inspection_item)
  }
  if (params.limit) searchParams.set('limit', String(params.limit))
  return inspectionGet<InspectionTrendResponse>(
    `/api/v1/quality/inspection-trends?${searchParams.toString()}`,
  )
}
