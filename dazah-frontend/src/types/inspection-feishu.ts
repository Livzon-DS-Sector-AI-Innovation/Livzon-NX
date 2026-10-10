// ==================== 设备巡检飞书镜像（只读展示） ====================
export type InspectionFeishuSource = 'today' | 'history'

export type InspectionFeishuTodayStatus = 'inspected' | 'abnormal' | 'pending'

export interface InspectionFeishuRecord {
  id: string
  source: InspectionFeishuSource
  record_id: string
  record_date: string | null
  equipment_name: string | null
  equipment_no: string | null
  am_clean: string | null
  am_lubrication: string | null
  am_fastening: string | null
  am_sealing: string | null
  am_vibration: string | null
  am_sound: string | null
  am_surface: string | null
  pm_clean: string | null
  pm_lubrication: string | null
  pm_fastening: string | null
  pm_sealing: string | null
  pm_vibration: string | null
  pm_sound: string | null
  pm_surface: string | null
  anomaly_note: string | null
  process_status: string | null
  has_abnormal: boolean
  raw_fields?: Record<string, unknown> | null
  last_modified_at: string | null
}

export interface InspectionFeishuDevice {
  record_id: string
  equipment_name: string | null
  equipment_no: string | null
  model: string | null
  location_name: string | null
  in_ledger: boolean
  today_status: InspectionFeishuTodayStatus
}

export interface InspectionFeishuSyncState {
  table_key: string
  total_rows: number
  last_synced_at: string | null
  last_run_at: string | null
  last_status: string | null
  last_message: string | null
}

export interface InspectionFeishuSyncStatus {
  enabled: boolean
  tables: InspectionFeishuSyncState[]
}

export interface InspectionFeishuTodaySummary {
  date: string
  total_devices: number
  inspected: number
  abnormal: number
}

export interface InspectionFeishuRecordFilters {
  source?: InspectionFeishuSource
  date_from?: string
  date_to?: string
  keyword?: string
  abnormal_only?: boolean
  process_status?: string
  page?: number
  page_size?: number
}

export interface InspectionFeishuRecordListResponse {
  items: InspectionFeishuRecord[]
  total: number
  page: number
  page_size: number
}

export interface InspectionFeishuConfigDetail {
  app_id: string
  app_secret_masked: string
  app_secret_configured: boolean
  app_token: string
  today_table_id: string
  history_table_id: string
  device_table_id: string
  is_enabled: boolean
  source: 'database' | 'environment'
  enabled: boolean
  last_test_status: string | null
  last_test_error: string | null
  last_tested_at: string | null
}

export interface InspectionFeishuConfigUpdateRequest {
  app_id: string
  app_secret?: string | null
  app_token: string
  today_table_id: string
  history_table_id: string
  device_table_id: string
  is_enabled: boolean
}

export interface InspectionFeishuConfigTestResult {
  success: boolean
  table_count: number
  message: string
}
