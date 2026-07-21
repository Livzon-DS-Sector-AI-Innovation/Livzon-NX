// CPV 类型定义

// 产品
export interface CpvProduct {
  id: string
  name: string
  specification: string | null
  process_version: string | null
  status: string
  description: string | null
  created_at: string
  updated_at: string
  created_by: string | null
  updated_by: string | null
}

export interface CpvProductWithStats extends CpvProduct {
  cpp_parameter_count: number
  cqa_parameter_count: number
  cpp_batch_count: number
  cqa_batch_count: number
  avg_value: number | null
  cpk_value: number | null
  abnormal_batch_count: number
}

// 参数
export interface CpvParameter {
  id: string
  product_id: string
  parameter_type: "CPP" | "CQA"
  name: string
  code: string | null
  unit: string | null
  lower_limit: number | null
  upper_limit: number | null
  control_lower: number | null
  control_upper: number | null
  target_value: number | null
  is_enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

// 批次
export interface CpvBatch {
  id: string
  product_id: string
  batch_no: string
  production_date: string
  data_type: "CPP" | "CQA"
  source: string
  import_task_id: string | null
  created_at: string
  updated_at: string
}

export interface CpvBatchWide {
  id: string
  batch_no: string
  production_date: string
  data_type: string
  source: string
  parameters: Record<string, {
    value: string | null
    is_abnormal: boolean
    lower_limit: number | null
    upper_limit: number | null
  }>
  has_abnormal: boolean
}

// 统计
export interface CpvStatistics {
  total_batches: number
  min_value: number
  max_value: number
  avg_value: number
  std_dev: number
  cpk_value: number
  abnormal_count: number
  lower_limit: number
  upper_limit: number
}

export interface CpvTrendItem {
  batch_no: string
  production_date: string
  value: number
  lower_limit: number
  upper_limit: number
  is_abnormal: boolean
}

export interface CpvTrendResponse {
  parameter_name: string
  parameter_unit: string | null
  items: CpvTrendItem[]
}

// 导入
export interface CpvImportPreview {
  total_rows: number
  valid_rows: number
  error_rows: Array<{
    row_number: number
    error_message: string
    row_data: Record<string, any>
  }>
  matched_parameters: string[]
  unmatched_columns: string[]
}

export interface CpvImportTask {
  id: string
  file_name: string
  product_id: string
  data_type: string
  import_mode: string
  status: string
  total_rows: number
  success_rows: number
  failed_rows: number
  error_details: any
  created_at: string
  created_by: string | null
}

// 创建/更新输入
export interface CreateCpvProductInput {
  name: string
  specification?: string
  process_version?: string
  status?: string
  description?: string
}

export interface UpdateCpvProductInput {
  name?: string
  specification?: string
  process_version?: string
  status?: string
  description?: string
}

export interface CreateCpvParameterInput {
  parameter_type: "CPP" | "CQA"
  name: string
  code?: string
  unit?: string
  lower_limit?: number
  upper_limit?: number
  control_lower?: number
  control_upper?: number
  target_value?: number
  is_enabled?: boolean
  sort_order?: number
}
