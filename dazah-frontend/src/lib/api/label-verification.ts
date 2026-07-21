const API_BASE = "/api/v1"
import {
  LabelVerificationListResponse,
  LabelVerificationResponse,
  LabelVerificationCreateInput,
  LabelVerificationUpdateInput,
  LabelVerificationStatisticsResponse,
  LabelVerificationListParams,
} from '@/types/label-verification'

export async function fetchLabelVerifications(
  params?: LabelVerificationListParams
): Promise<LabelVerificationListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.batch_number) searchParams.set('batch_number', params.batch_number)
  if (params?.product_name) searchParams.set('product_name', params.product_name)
  if (params?.result_status) searchParams.set('result_status', params.result_status)
  if (params?.start_date) searchParams.set('start_date', params.start_date)
  if (params?.end_date) searchParams.set('end_date', params.end_date)
  searchParams.set('page', String(params?.page || 1))
  searchParams.set('page_size', String(params?.page_size || 20))

  const res = await fetch(`/api/v1/quality/label-verifications?${searchParams.toString()}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取标签复核列表失败')
  return res.json()
}

export async function fetchLabelVerificationById(id: string): Promise<LabelVerificationResponse> {
  const res = await fetch(`/api/v1/quality/label-verifications/${id}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取标签复核详情失败')
  return res.json()
}

export async function createLabelVerification(
  data: LabelVerificationCreateInput
): Promise<LabelVerificationResponse> {
  const res = await fetch(`/api/v1/quality/label-verifications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('创建标签复核记录失败')
  return res.json()
}

export async function updateLabelVerification(
  id: string,
  data: LabelVerificationUpdateInput
): Promise<LabelVerificationResponse> {
  const res = await fetch(`/api/v1/quality/label-verifications/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('更新标签复核记录失败')
  return res.json()
}

export async function deleteLabelVerification(id: string): Promise<void> {
  const res = await fetch(`/api/v1/quality/label-verifications/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('删除标签复核记录失败')
}

export async function fetchLabelVerificationStatistics(): Promise<LabelVerificationStatisticsResponse> {
  const res = await fetch(`/api/v1/quality/label-verifications/statistics`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取标签复核统计数据失败')
  return res.json()
}

export async function fetchLabelVerificationsByBatch(batchNumber: string): Promise<LabelVerificationListResponse> {
  const res = await fetch(`/api/v1/quality/label-verifications/batch/${batchNumber}`, {
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('获取批号历史记录失败')
  return res.json()
}

export interface AutoCompareRequest {
  video_file_key: string
  batch_number: string
  product_name?: string
  production_date?: string
  expiry_date?: string
  total_barrels?: number
  standard_barrels?: number
  remainder_barrel?: number
  standard_weight?: number
  remainder_weight?: number
  total_weight?: number
}

export interface AutoCompareResult {
  checks: {
    check_batch_number: boolean
    check_production_date: boolean
    check_expiry_date: boolean
    check_standard_barrels: boolean
    check_remainder_barrel: boolean
    check_total_weight: boolean
    check_all_barrels_identified: boolean
    check_exception_handled: boolean
  }
  ai_data: {
    batch_number: string | null
    product_name: string | null
    production_date: string | null
    expiry_date: string | null
    total_barrels: number | null
    standard_barrels: number | null
    remainder_barrel: number | null
    standard_weight: number | null
    remainder_weight: number | null
    total_weight: number | null
    barrels_seen: string[]
  }
  confidence: number
  frames_count: number
  fps_used: number
  retry_count: number
  reasons: Record<string, string>
  notes: string
  result_status: string
  result_summary: string
}

export async function autoCompareVideo(
  data: AutoCompareRequest
): Promise<{ code: number; message: string; data: AutoCompareResult }> {
  const res = await fetch(
    `${API_BASE}/api/v1/quality/label-verifications/auto-compare`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || '自动对比失败')
  }
  return res.json()
}
