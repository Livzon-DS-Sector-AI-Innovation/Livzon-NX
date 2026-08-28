// production module TypeScript types

export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
  meta?: {
    page?: number
    page_size?: number
    total?: number
  }
}

// ============ Enums ============

export enum BatchStatus {
  DRAFT = 'draft',
  RELEASED = 'released',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  CANCELLED = 'cancelled',
}

export enum ProcessSpecStatus {
  DRAFT = 'draft',
  APPROVED = 'approved',
  EFFECTIVE = 'effective',
  ARCHIVED = 'archived',
}

export enum OperationType {
  MATERIAL_ADD = 'material_add',
  TRANSFER = 'transfer',
  SAMPLING = 'sampling',
  EQUIPMENT_CHECK = 'equipment_check',
  PARAMETER_RECORD = 'parameter_record',
  PACKAGING = 'packaging',
}

export const BATCH_STATUS_OPTIONS = [
  { value: BatchStatus.DRAFT, label: '草稿', color: 'default' },
  { value: BatchStatus.RELEASED, label: '已下达', color: 'blue' },
  { value: BatchStatus.IN_PROGRESS, label: '执行中', color: 'processing' },
  { value: BatchStatus.COMPLETED, label: '已完成', color: 'success' },
  { value: BatchStatus.CANCELLED, label: '已取消', color: 'error' },
]

export const PROCESS_SPEC_STATUS_OPTIONS = [
  { value: ProcessSpecStatus.DRAFT, label: '草稿', color: 'default' },
  { value: ProcessSpecStatus.APPROVED, label: '已批准', color: 'blue' },
  { value: ProcessSpecStatus.EFFECTIVE, label: '已生效', color: 'success' },
  { value: ProcessSpecStatus.ARCHIVED, label: '已归档', color: 'warning' },
]

export const OPERATION_TYPE_OPTIONS = [
  { value: OperationType.MATERIAL_ADD, label: '投料' },
  { value: OperationType.TRANSFER, label: '转序' },
  { value: OperationType.SAMPLING, label: '取样' },
  { value: OperationType.EQUIPMENT_CHECK, label: '设备检查' },
  { value: OperationType.PARAMETER_RECORD, label: '参数记录' },
  { value: OperationType.PACKAGING, label: '包装' },
]

// ============ Fermentation Types ============

export enum FermentationStatus {
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  ABNORMAL = 'abnormal',
}

export const FERMENTATION_STATUS_OPTIONS = [
  { value: FermentationStatus.IN_PROGRESS, label: '发酵中', color: 'processing' },
  { value: FermentationStatus.COMPLETED, label: '已完成', color: 'success' },
  { value: FermentationStatus.ABNORMAL, label: '异常', color: 'error' },
]

// ============ Batch Types ============

export interface Batch {
  id: string
  batch_no: string
  product_code: string
  product_name?: string
  specification?: string
  unit?: string
  status: BatchStatus
  planned_qty?: number
  actual_qty?: number
  input_qty?: number
  process_spec_id?: string
  production_line?: string
  start_time?: string
  end_time?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface BatchMaterial {
  id: string
  batch_id: string
  material_code: string
  material_name?: string
  material_type?: string
  unit?: string
  planned_qty?: number
  actual_qty?: number
  lot_no?: string
  stage?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface BatchFormData {
  batch_no: string
  product_code: string
  product_name?: string
  specification?: string
  unit?: string
  planned_qty?: number
  process_spec_id?: string
  production_line?: string
  notes?: string
}

export interface BatchMaterialFormData {
  material_code: string
  material_name?: string
  material_type?: string
  unit?: string
  planned_qty?: number
  lot_no?: string
  stage?: string
  notes?: string
}

// ============ ProductionPlan Types ============

export interface ProductionPlan {
  id: string
  workshop?: string | null
  product_name: string
  plan_date?: string | null
  planned_yield?: number | null
  unit?: string | null
  actual_completion?: number | null
  completion_rate?: number | null
  safety_status?: string | null
  quality_status?: string | null
  remarks?: string | null
  source?: string | null
  created_at: string
  updated_at: string
}

export interface ProductionPlanFormData {
  workshop?: string
  product_name: string
  plan_date?: string
  planned_yield?: number
  unit?: string | null
  actual_completion?: number
  completion_rate?: number
  safety_status?: string
  quality_status?: string
  remarks?: string
}

export interface PlanTask {
  id: string
  plan_id?: string
  task_name: string
  assignee?: string
  status?: string
  start_date?: string
  due_date?: string
  completed_at?: string
  remarks?: string
  created_at?: string
  updated_at?: string
}

// ============ SalesPlanDetail Types ============

export interface SalesPlanDetail {
  id: string
  product_name: string
  unit?: string | null
  last_month_delivered_uninvoiced?: number | null
  current_year_delivered?: number | null
  month_planned_delivery?: number | null
  month_delivered_qty?: number | null
  undelivered_qty?: number | null
  month_planned_invoice?: number | null
  invoiced_qty?: number | null
  delivery_completion_rate?: number | null
  last_month_end_inventory?: number | null
  month_planned_capacity?: number | null
  month_end_inventory?: number | null
  remarks?: string | null
  source?: string | null
  created_at: string
  updated_at: string
}

export interface SalesPlanDetailFormData {
  product_name: string
  unit?: string
  last_month_delivered_uninvoiced?: number
  current_year_delivered?: number
  month_planned_delivery?: number
  month_delivered_qty?: number
  undelivered_qty?: number
  month_planned_invoice?: number
  invoiced_qty?: number
  delivery_completion_rate?: number
  last_month_end_inventory?: number
  month_planned_capacity?: number
  month_end_inventory?: number
  remarks?: string
}

// ============ ProcessSpec Types ============

export interface ProcessSpec {
  id: string
  spec_code: string
  spec_name?: string
  product_code: string
  product_name?: string
  version: string
  status: ProcessSpecStatus
  effective_date?: string
  approved_by?: string
  approved_by_name?: string
  approved_at?: string
  supersedes_version?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface ProcessStep {
  id: string
  spec_id: string
  step_no: number
  step_name: string
  description?: string
  equipment_type?: string
  equipment_spec?: string
  duration_minutes?: number
  sequence_order?: number
  notes?: string
  created_at: string
  updated_at: string
  parameters?: ProcessParameter[]
}

export interface ProcessParameter {
  id: string
  step_id: string
  param_name: string
  param_code?: string
  unit?: string
  min_value?: number
  max_value?: number
  target_value?: number
  is_critical: boolean
  data_type?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface ProcessSpecFormData {
  spec_code: string
  spec_name?: string
  product_code: string
  product_name?: string
  version?: string
  notes?: string
}

export interface ProcessStepFormData {
  step_no: number
  step_name: string
  description?: string
  equipment_type?: string
  equipment_spec?: string
  duration_minutes?: number
  sequence_order?: number
  notes?: string
}

export interface ProcessParameterFormData {
  param_name: string
  param_code?: string
  unit?: string
  min_value?: number
  max_value?: number
  target_value?: number
  is_critical?: boolean
  data_type?: string
  notes?: string
}

// ============ ProductionRecord Types ============

export interface ProductionRecord {
  id: string
  batch_id: string
  record_no: string
  step_no?: number
  step_name?: string
  operator?: string
  operator_name?: string
  operation_time: string
  operation_type: OperationType
  parameters?: string
  result?: string
  remarks?: string
  created_at: string
  updated_at: string
}

export interface ProductionRecordFormData {
  record_no: string
  step_no?: number
  step_name?: string
  operation_type: OperationType
  parameters?: string
  result?: string
  remarks?: string
}

// ============ MaterialBalance Types ============

export interface MaterialBalance {
  id: string
  batch_id: string
  input_qty?: number
  output_qty?: number
  loss_qty?: number
  balance_rate?: number
  min_balance_rate: number
  is_balanced: boolean
  deviation_rate?: number
  calculated_at?: string
  notes?: string
  created_at: string
  updated_at: string
}

// ============ Query Parameters ============

export interface BatchQueryParams {
  page?: number
  page_size?: number
  status?: BatchStatus
  product_code?: string
  batch_no?: string
  exclude_cancelled?: boolean
}

export interface PlanQueryParams {
  page?: number
  page_size?: number
  product_name?: string
  workshop?: string
}

export interface ProcessSpecQueryParams {
  page?: number
  page_size?: number
  status?: ProcessSpecStatus
  product_code?: string
}

// ============ Fermentation Types ============

export interface FermentationRecord {
  id: string
  batch_no: string
  product_name: string
  fermenter: string
  entry_date: string
  discharge_date?: string
  cycle_1?: number
  cycle_2?: number
  cycle_3?: number
  cycle_4?: number
  cycle_5?: number
  cycle_6?: number
  tank_yield?: number
  status: string
  remarks?: string
  attachment?: string
  created_at: string
  updated_at: string
}

export interface FermentationFormData {
  batch_no: string
  product_name?: string
  fermenter: string
  entry_date: string
  discharge_date?: string
  cycle_1?: number
  cycle_2?: number
  cycle_3?: number
  cycle_4?: number
  cycle_5?: number
  cycle_6?: number
  tank_yield?: number
  status?: string
  remarks?: string
  attachment?: string
}

export interface FermentationQueryParams {
  page?: number
  page_size?: number
  product_name?: string
  batch_no?: string
  status?: string
  fermenter?: string
}