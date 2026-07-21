export interface LabelVerification {
  id: string
  batch_number: string
  product_name: string
  production_date: string
  expiry_date: string
  total_barrels: number
  standard_barrels: number
  remainder_barrel: number
  standard_weight: number
  remainder_weight: number
  total_weight: number
  check_batch_number: boolean
  check_production_date: boolean
  check_expiry_date: boolean
  check_standard_barrels: boolean
  check_remainder_barrel: boolean
  check_total_weight: boolean
  check_all_barrels_identified: boolean
  check_exception_handled: boolean
  result_status: string
  result_summary: string
  video_file_key: string
  video_file_name?: string
  video_frame_count?: number
  video_fps?: number
  verification_date: string
  verification_time: string
  remarks?: string
  created_at: string
  updated_at: string
}

export interface LabelVerificationCreateInput {
  batch_number: string
  product_name: string
  production_date: string
  expiry_date: string
  total_barrels: number
  standard_barrels: number
  remainder_barrel: number
  standard_weight: number
  remainder_weight: number
  total_weight: number
  check_batch_number: boolean
  check_production_date: boolean
  check_expiry_date: boolean
  check_standard_barrels: boolean
  check_remainder_barrel: boolean
  check_total_weight: boolean
  check_all_barrels_identified: boolean
  check_exception_handled: boolean
  result_status: string
  result_summary: string
  video_file_key: string
  video_file_name?: string
  video_frame_count?: number
  video_fps?: number
  verification_date: string
  verification_time: string
  remarks?: string
}

export interface LabelVerificationUpdateInput {
  product_name?: string
  production_date?: string
  expiry_date?: string
  total_barrels?: number
  standard_barrels?: number
  remainder_barrel?: number
  standard_weight?: number
  remainder_weight?: number
  total_weight?: number
  check_batch_number?: boolean
  check_production_date?: boolean
  check_expiry_date?: boolean
  check_standard_barrels?: boolean
  check_remainder_barrel?: boolean
  check_total_weight?: boolean
  check_all_barrels_identified?: boolean
  check_exception_handled?: boolean
  result_status?: string
  result_summary?: string
  video_file_name?: string
  video_frame_count?: number
  video_fps?: number
  remarks?: string
}

export interface LabelVerificationListResponse {
  code: number
  message: string
  data: LabelVerification[]
  meta?: {
    page: number
    page_size: number
    total: number
  }
}

export interface LabelVerificationResponse {
  code: number
  message: string
  data: LabelVerification
}

export interface LabelVerificationStatistics {
  total: number
  all_match: number
  has_difference: number
  match_rate: number
  today_count: number
  this_week_count: number
  this_month_count: number
  by_batch: Record<string, number>
}

export interface LabelVerificationStatisticsResponse {
  code: number
  message: string
  data: LabelVerificationStatistics
}

export interface LabelVerificationListParams {
  batch_number?: string
  product_name?: string
  result_status?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}
