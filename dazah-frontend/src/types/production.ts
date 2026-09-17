// production module TypeScript types
import type { components } from '@/types/generated/schema'

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
  workshop_code?: components['schemas']['BatchCreate']['workshop_code']
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
  workshop_code?: components['schemas']['BatchCreate']['workshop_code']
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
  /** 按自然月筛选（YYYY-MM）：日期落在哪个月即哪个月的计划 */
  month?: string
}

/** 生产计划月度汇总（按单位分组：KG 与批分开统计） */
export interface PlanMonthlySummary {
  unit: string
  planned_yield: number
  actual_completion: number
  /** 完成率 = Σ实际 ÷ Σ计划；当月无计划产量时为 null */
  completion_rate: number | null
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
// ============ 排产计划 Excel 存档 ============

/** 合并单元格（0-based，与后端解析协议一致） */
export interface ScheduleMergeRange {
  s: { r: number; c: number }
  e: { r: number; c: number }
}

/** 排产 Excel 存档记录（上传/详情返回全量，列表项不含 rows） */
export interface ScheduleExcelArchive {
  id: string
  file_name: string
  sheet_name: string
  original_path?: string
  created_by_name?: string | null
  rows?: string[][]
  merges?: ScheduleMergeRange[]
  col_widths?: number[]
  row_count: number
  col_count: number
  created_at?: string
  updated_at?: string
}

// ============ 发酵车间实时看板 ============

export interface BoardTank {
  tank_no: string
  status: 'running' | 'dumping' | 'idle' | 'maintenance' | 'dumped'
  batch_no: string | null
  inoculate_at: string | null
  cultured_hours: number | null
  cycle_hours: number | null
  dump_at: string | null
  note: string | null
}

/** 生产汇总：单产线发酵指标 */
export interface ProductionSummaryFerment {
  planned_batches: number | null
  planned_capacity_kg: number | null
  done_yield_kg: number | null
  capacity_rate: number | null
}

/** 生产汇总：单产线提炼指标 */
export interface ProductionSummaryExtract {
  planned_yield_kg: number | null
  finished_inbound_kg: number | null
  completion_rate: number | null
}

/** 生产汇总：单产线行 */
export interface ProductionSummaryRow {
  product_code: string
  product_name: string
  covered: boolean
  ferment: ProductionSummaryFerment
  extract: ProductionSummaryExtract
  /** 该产线排产播报（发酵权限） */
  alerts: { level: string; text: string }[]
}

/** 生产汇总响应 */
export interface ProductionSummary {
  period: { start: string; end: string; label: string } | null
  rows: ProductionSummaryRow[]
}

export interface BoardKpis {
  month_planned: number | null
  month_done_planned: number | null
  /** 已放罐且产量已录入的批次数（进度条"已完成"段） */
  done_with_yield: number | null
  /** 已放罐但产量未录入的批次数（进度条灰色"待出产量"段） */
  yield_pending: number | null
  /** 本月已完成产能(kg) = 已录入产量的已放罐批次合计；未录入时为 null */
  month_done_yield_kg: number | null
  running: number | null
  pending: number | null
  plan_capacity: number | string | null
  contam_count: number | null
  contam_rate: number | string | null
  avg_yield_rate: number | string | null
  utilization: number | string | null
  avg_batch_yield: number | string | null
  qualify_rate: number | string | null
}

export interface BoardRecentBatch {
  batch_no: string
  dump_date: string
  tank_no: string
  yield_kg: number | null
  /** 提炼成品产量(kg)，仅持提炼产量权限时返回 */
  extract_kg?: number | null
  /** 单批收率(%) = 提炼成品 ÷ 放罐产量 ×100，仅持提炼产量权限时返回 */
  batch_yield_rate?: number | null
  remark: string | null
  yield_rate: number | null
  result: string
  /** 移种时间（凑数已放罐行展示用） */
  inoculate_at?: string | null
  /** 计划总周期(h)（凑数已放罐行展示用） */
  cycle_hours?: number | null
}

export interface BoardAlert {
  level: 'warn' | 'info'
  text: string
}

export interface BoardMaintenance {
  id: string
  tank_no: string
  reason: string
  started_at: string | null
}

export interface FermentationBatchActual {
  id: string
  batch_no: string
  /** 放罐罐号（由排产存档解析，缺失为 null） */
  tank_no: string | null
  dump_date: string | null
  yield_kg: number | null
  /** 提炼成品产量(kg)，仅持提炼产量权限时返回 */
  extract_kg?: number | null
  remark: string | null
}

export interface FermentationBatchActualFormData {
  batch_no: string
  dump_date?: string | null
  yield_kg?: number | null
  extract_kg?: number | null
  remark?: string | null
}

/** 提炼工段汇总（收率两口径）；无提炼产量权限时为 null */
export interface BoardExtraction {
  /** 当期发酵已放罐产量合计(kg) */
  ferment_total_kg: number | null
  /** 当期提炼已出成品合计(kg) */
  extract_total_kg: number | null
  /** 已录放罐产量的批次数 */
  ferment_batches: number
  /** 已录提炼成品的批次数 */
  extract_batches: number
  /** 实时口径收率(%) = Σ成品 ÷ Σ放罐（含在途批次） */
  rate_realtime: number | null
  /** 配对口径收率(%) = 已出成品批次内 Σ成品 ÷ Σ对应放罐 */
  rate_paired: number | null
}


export interface FermentationBoard {
  now: string
  period: { start: string; end: string; label: string }
  /** 发酵工段 KPI；无发酵产量权限时为 null */
  kpis: BoardKpis | null
  /** 所查看周期是否为当前扎帐月（写操作仅当前月开放） */
  is_current_period: boolean
  /** 当前扎帐月计划产能(kg)，未设置或无发酵产量权限时为 null */
  month_planned_capacity_kg: number | null
  /** 当期仓储成品入库合计(kg)（提炼已出成品卡片，仅接入产品返回；未接入/无提炼权限/仓储异常时为 null） */
  extract_finished_inbound_kg?: number | null
  tanks: BoardTank[]
  recent: BoardRecentBatch[]
  /** 已录入实际产量的最近 12 批（按批次顺序升序），outputs 单位 kg */
  trend: { batches: string[]; outputs: number[] } | null
  /** 当前周期内已放罐（放罐窗口已结束）的批次，供产量录入下拉 */
  dumped_batches: { batch_no: string; dump_date: string }[]
  /** 提炼工段汇总；无提炼产量权限时为 null */
  extraction: BoardExtraction | null
  alerts: BoardAlert[]
  maintenance: BoardMaintenance[]
}
