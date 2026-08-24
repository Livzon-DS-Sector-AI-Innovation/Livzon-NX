import type { components } from '@/types/generated/schema'

export interface RawMaterial {
  id: string
  sourceId: string | null
  code: string
  name: string
  spec: string
  unit: string
  available: number
  safety: number
  lastMonth: number
  twoMonthsAgo: number
  todayBalance: number
  frontStock: number
  thisMonthUse: number
  warning: string
  product: string
  erp: string | null
  delivery: string
  remark: string
}

export interface PackagingMaterial {
  id: string
  sourceId: string | null
  code: string
  name: string
  spec: string
  batch: string
  available: number
  safety: number
  lastMonth: number
  twoMonthsAgo: number
  todayBalance: number
  frontStock: number
  thisMonthUse: number
  warning: string
  product: string
  erp: string | null
  delivery: string
  remark: string
}

export interface ProductInventory {
  id: string
  sourceId: string | null
  name: string
  spec: string
  orderQty: number
  pending: number
  qualified: number
  subtotal: number
  remaining: number
  unit: string
  remark: string
}

export type WarehouseFeishuCellValue = string | number | boolean | null

export interface WarehouseFeishuColumn {
  key: string
  title: string
  field_type?: number | null
  readonly?: boolean
  view_only?: boolean
  editable?: boolean
}

export interface WarehouseFeishuRow {
  __record_id?: string
  [key: string]: WarehouseFeishuCellValue | string | undefined
}

export interface WarehouseRecordFieldOption {
  id?: string
  name: string
}

export interface WarehouseRecordFieldValue {
  field_name: string
  field_type?: number | null
  readonly?: boolean
  view_only?: boolean
  editable?: boolean
  options?: WarehouseRecordFieldOption[] | null
  value?: unknown
}

export interface WarehouseRecordDetail {
  record_id: string
  fields: WarehouseRecordFieldValue[]
}

export interface WarehousePageStats {
  total?: number
  warning_count?: number
  low_stock_count?: number
  severe_low_stock_count?: number
  quality_counts?: Record<string, number>
  qualified_count?: number
  pending_count?: number
  failed_count?: number
  stock_count?: number
  amount_total?: number
  today_count?: number
  month_count?: number
}

// ── 仪表盘 UI 类型（展示用 ViewModel）──────────────────────────
export interface WarehouseDashboardTrendPoint {
  date: string
  value: number
}

export interface WarehouseDashboardNameValue {
  name: string
  value: number
}

export interface WarehouseDashboardDeptValue {
  dept: string
  value: number
}

export interface WarehouseLowStockItem {
  name: string
  balance: number
  safety: number
  warning: string
}

export interface WarehouseRawDashboard {
  safety: { total: number; ok: number; low: number }
  quality: { 合格: number; 待验: number; 不合格: number }
  material_outbound_30d: WarehouseDashboardTrendPoint[]
  packaging_outbound_30d_total: number
  month_inbound_total: number
  low_stock_top: WarehouseLowStockItem[]
  detail?: WarehouseRawDashboardDetail
}

export interface WarehouseRawDashboardDetail {
  safety_ok: Array<{ name: string; balance: number; effective_balance: number; safety: number }>
  safety_low: Array<{
    name: string
    balance: number
    effective_balance: number
    safety: number
    warning: string
  }>
  pending: Array<{
    name: string
    batch: string
    balance: number
    quality_status: string
    area: string
  }>
  month_inbound: Array<{
    date: string
    category: string
    name: string
    spec: string
    batch: string
    quantity: number
    supplier: string
  }>
}

export interface WarehouseHardwareDashboard {
  stock_amount: number
  dept_stock: WarehouseDashboardDeptValue[]
  inbound_30d_total: number
  outbound_30d_total: number
  outbound_30d_trend: WarehouseDashboardTrendPoint[]
  dept_outbound_30d: WarehouseDashboardDeptValue[]
  detail?: WarehouseHardwareDashboardDetail
}

export interface WarehouseHardwareDashboardDetail {
  dept_stock: Array<{ dept: string; value: number }>
  inbound_30d: Array<{
    date: string
    name: string
    spec: string
    quantity: number
    price: number
    amount: number
  }>
  outbound_30d: Array<{ date: string; name: string; spec: string; dept: string; amount: number }>
}

export interface WarehouseProductDashboard {
  qualified: number
  pending: number
  pending_batches: number
  product_stock: WarehouseDashboardNameValue[]
  product_outbound: WarehouseDashboardNameValue[]
  shipping_30d_trend: WarehouseDashboardTrendPoint[]
  detail?: WarehouseProductDashboardDetail
}

export interface WarehouseProductDashboardDetail {
  qualified: Array<{ name: string; value: number }>
  pending: Array<{ name: string; value: number }>
  product_stock: Array<{ name: string; value: number }>
}

export type WarehouseDashboardGroup = 'raw' | 'hardware' | 'product'

export type WarehouseDashboardData =
  | WarehouseRawDashboard
  | WarehouseHardwareDashboard
  | WarehouseProductDashboard

export interface WarehouseAdvancedFilter {
  field: string
  operator:
    | 'contains'
    | 'not_contains'
    | 'eq'
    | 'neq'
    | 'empty'
    | 'not_empty'
    | 'gt'
    | 'gte'
    | 'lt'
    | 'lte'
    | 'between'
  value?: string
  value_to?: string
}

export interface WarehouseMaterialPageQueryParams {
  page?: number
  page_size?: number
  source?: string
  force?: boolean
  keyword?: string
  start_date?: string
  end_date?: string
  date_field?: string
  product?: string
  area?: string
  quality_status?: string
  warning_status?: string
  material_category?: string
  filters?: WarehouseAdvancedFilter[]
}

export type WarehouseFeishuMaterialPageData = Omit<
  components['schemas']['WarehouseFeishuMaterialPageResponse'],
  'rows' | 'stats' | 'base_name'
> & {
  columns: WarehouseFeishuColumn[]
  rows: WarehouseFeishuRow[]
  base_name?: string
  stats?: WarehousePageStats
}

export interface WarehouseTrendSummary {
  total: number
  high_risk: number
  medium_risk: number
  raw_count: number
  packaging_count: number
}

export interface WarehouseTrendAnomalyItem {
  material_name: string
  material_type: 'raw' | 'packaging'
  product_line: string
  current_week_usage: number
  history_week_avg_usage: number
  usage_delta_ratio: number | null
  current_inventory: number
  safety_inventory: number
  estimated_cover_days: number | null
  risk_level: 'high' | 'medium' | 'low'
  reason: string
  suggestion: string
}

export interface WarehouseTrendProductLineItem {
  product_line: string
  current_week_usage: number
  history_week_avg_usage: number
  usage_delta_ratio: number | null
  high_risk_count: number
  medium_risk_count: number
  material_count: number
}

export interface WarehouseHardwareCostAnomalyItem {
  workshop_name: string
  current_month_cost: number
  history_month_avg_cost: number
  cost_delta_ratio: number | null
  risk_level: 'high' | 'medium'
  reason: string
  suggestion: string
}

export interface WarehouseHardwareCostSummary {
  total_workshops: number
  anomaly_workshops: number
  high_risk_count: number
  medium_risk_count: number
  current_month_total_cost: number
  history_month_avg_total_cost: number
}

// ── 页面飞书配置 ────────────────────────────────────────────────

export type WarehousePageFeishuConfig = components['schemas']['WarehousePageFeishuConfig']

// ── 成品每月出入库数据 ────────────────────────────────────────────────

export interface WarehouseProductMonthlyData {
  [productName: string]: Array<{
    month: string
    quantity: number
  }>
}

// Generic local Feishu mirror used by warehouse/production/energy mapped pages.
export interface WarehouseFeishuField {
  field_id: string
  field_name: string
  field_type?: string | number | null
}

export interface WarehouseDatasetRecord {
  record_id: string
  fields: Record<string, unknown>
  created_at?: string | null
  updated_at?: string | null
}

export interface WarehouseDataset {
  fields: WarehouseFeishuField[]
  records: WarehouseDatasetRecord[]
  pagination: { page: number; page_size: number; total: number }
}

export interface WarehouseFeishuPageBinding {
  id: string
  tab_label: string
  is_default?: boolean
  visible_field_ids?: string[] | null
  table: {
    app_token: string
    source_path?: Array<{ title?: string | null }> | null
    sync_status?: string | null
    sync_error?: string | null
    last_synced_at?: string | null
  }
}

export interface WarehouseFeishuPageData {
  page_key?: string
  bindings: WarehouseFeishuPageBinding[]
}
