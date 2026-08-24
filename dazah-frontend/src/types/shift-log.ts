// 生产日志与交接班类型

export interface ShiftLogRecord {
  id: string
  log_date: string
  shift: string
  workshop: string
  handover_from: string
  handover_to: string
  production_summary?: string | null
  equipment_status?: string | null
  abnormal_events?: string | null
  pending_tasks?: string | null
  remarks?: string | null
  created_at: string
  updated_at: string
}

export interface ShiftLogCreate {
  log_date: string
  shift: string
  workshop: string
  handover_from: string
  handover_to: string
  production_summary?: string | null
  equipment_status?: string | null
  abnormal_events?: string | null
  pending_tasks?: string | null
  remarks?: string | null
}

export interface ShiftLogUpdate {
  log_date?: string
  shift?: string
  workshop?: string
  handover_from?: string
  handover_to?: string
  production_summary?: string | null
  equipment_status?: string | null
  abnormal_events?: string | null
  pending_tasks?: string | null
  remarks?: string | null
}

export const SHIFT_OPTIONS = [
  { value: 'morning', label: '早班', color: '#faad14' },
  { value: 'afternoon', label: '中班', color: '#1677ff' },
  { value: 'night', label: '晚班', color: '#722ed1' },
]
