export interface InspectionDashboardLatestRecord {
  id: string
  resource_code: string
  resource_name: string
  inspection_no?: string | null
  subject?: string | null
  batch_no?: string | null
  inspection_item?: string | null
  test_result?: string | null
  specification?: string | null
  conclusion?: string | null
  inspection_date?: string | null
  created_at: string
}

export interface InspectionDashboardResponse {
  resource_summaries: Array<{
    resource_code: string; resource_name: string; total: number; qualified: number; attention_required: number
  }>
  latest_records: InspectionDashboardLatestRecord[]
}

export interface InspectionTrendResponse {
  resource_code: string
  resource_name: string
  subject?: string | null
  inspection_item?: string | null
  points: Array<{ record_id: string; label: string; value: number; inspection_date?: string | null; is_alert?: boolean }>
  alerts: Array<{ record_id: string; label: string; actual_value: number; alert_type: string; message: string }>
  summary: { sample_count: number; mean?: number | null; alert_count: number }
}

export interface InspectionTrendParams {
  resource_code: string
  subject?: string
  inspection_item?: string
  limit?: number
}

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
