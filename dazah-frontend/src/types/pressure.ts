// Pressure differential inspection module types

import type { ApiResponse } from './production'

// ============ Enums ============

export const AREA_OPTIONS = [
  '无菌区',
  '精洗区',
  '配液区',
  '走廊',
  '更衣室',
  '其他',
] as const
export type AreaType = (typeof AREA_OPTIONS)[number]

export enum InputType {
  MANUAL = 'manual',
  OCR = 'ocr',
}

export enum AuditStatus {
  PENDING = 'pending',
  APPROVED = 'approved',
  REJECTED = 'rejected',
}

export enum OcrTaskStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
  SUBMITTED = 'submitted',
}

export enum DataSource {
  MANUAL = 'manual',
  OCR = 'ocr',
}

export const AUDIT_STATUS_OPTIONS = [
  { value: AuditStatus.PENDING, label: '待审核', color: 'warning' },
  { value: AuditStatus.APPROVED, label: '已通过', color: 'success' },
  { value: AuditStatus.REJECTED, label: '已驳回', color: 'error' },
]

// ============ Interfaces ============

export interface DashboardStats {
  today_count: number
  pending_count: number
  last_record_time: string | null
}

export interface PointMapping {
  id: string
  point_id: string
  area: string
  standard_pressure: number
  created_at?: string
  updated_at?: string
}

export interface PressureRecord {
  id: string
  point_id: string
  area: string
  pressure_value: number
  standard_pressure: number
  record_time: string
  input_type: string
  status: string
  reject_reason: string | null
  creator: string | null
  image_url: string | null
  remark: string | null
  batch_id: string | null
  time_slot: string | null
  created_at?: string
  updated_at?: string
}

export interface MergedPressureRow {
  point_id: string
  area: string
  date: string
  time_slot_values: Record<string, number | null>
  standard_pressure: number
  record_ids: string[]
  status: string
  input_type: string
}

export interface OcrTask {
  id: string
  status: string
  image_url: string
  result: { records: OcrResultRecord[] } | null
  error_message: string | null
  batch_id: string | null
  created_at: string
}

export interface OcrResultRecord {
  point_id: string
  pressure_value: number
  record_time: string
  recorder: string
  time_slot?: string
}


export interface NotificationItem {
  id: string
  type: string
  title: string
  message: string
  is_read: boolean
  related_id: string | null
  related_type: string | null
  created_at: string
}

export interface NotificationListResponse {
  items: NotificationItem[]
  unread_count: number
}

export interface AuditStats {
  pending_count: number
  today_approved_count: number
  rejected_count: number
}

// ============ Request Types ============

export interface BatchManualEntryRow {
  date: string
  values: Record<string, number | null>
}

export interface BatchManualEntryRequest {
  area: string
  rows: BatchManualEntryRow[]
  time_slots?: string[]
  remark?: string
}

export interface BatchManualEntryResponse {
  success_count: number
  fail_count: number
  batch_id: string
}

export interface CreateOcrRecordRequest {
  records: Array<{
    record_time: string
    point_id: string
    pressure_value: number
    area: string
    standard_pressure?: number
    time_slot?: string
    remark?: string
  }>
  image_url: string
  task_id?: string
}

export interface OcrSubmitResponse {
  success_count: number
  fail_count: number
  success: boolean
  batch_id?: string
}

export interface UpdateMergedRowRequest {
  point_id: string
  date: string
  time_slot_values: Record<string, number | null>
}

export interface DeleteMergedRowRequest {
  point_id: string
  date: string
}

// Re-export ApiResponse for convenience
export type { ApiResponse }
