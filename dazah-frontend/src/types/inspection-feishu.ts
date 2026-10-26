// ==================== 设备巡检飞书镜像（只读展示） ====================
export type InspectionFeishuSource = 'today' | 'history'

export type InspectionFeishuTodayStatus = 'inspected' | 'abnormal' | 'pending'

export interface InspectionFeishuRecord {
  id: string
  workshop_code: string
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
  /** 镜像里最近一次巡检日期；从未巡检为 null */
  last_inspected_date: string | null
}

export interface InspectionFeishuDeviceList {
  /** “今日状态”的口径日期（北京时间） */
  date: string
  items: InspectionFeishuDevice[]
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
  /** 上午/下午任一检查项有值的设备数（有效记录行口径） */
  am_inspected: number
  pm_inspected: number
}

export interface InspectionFeishuWorkshopSummary extends InspectionFeishuTodaySummary {
  workshop_code: string
}

export interface InspectionFeishuRecordFilters {
  /** 车间代码；缺省跨车间查询（设备详情抽屉按设备编号聚合） */
  workshop?: string
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

/** 飞书自建应用（登记一次、多车间复用；Secret 只存不显） */
export interface FeishuAppSummary {
  id: string
  name: string
  app_id: string
  app_secret_masked: string
  app_secret_configured: boolean
  /** 引用该应用的未删除车间配置 */
  in_use_workshops: string[]
  created_at: string
}

export interface FeishuAppCreateRequest {
  name: string
  app_id: string
  app_secret: string
}

export interface FeishuAppUpdateRequest {
  /** 应用备注名；null 表示不改 */
  name?: string | null
  /** 新 App Secret；留空/ null 表示保持已保存值 */
  app_secret?: string | null
}

export interface InspectionFeishuConfigDetail {
  workshop_code: string
  /** 关联的飞书自建应用 ID（环境变量回退时为 null） */
  feishu_app_id: string | null
  /** 关联应用备注名（环境变量回退时为空） */
  app_name: string
  app_id: string
  app_secret_masked: string
  app_secret_configured: boolean
  app_token: string
  base_url: string
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

/** 凭据两选一：feishu_app_id 选择已登记应用（优先）；或手输 app_id/app_secret（已登记则自动关联） */
export interface InspectionFeishuConfigUpdateRequest {
  feishu_app_id?: string | null
  app_id?: string
  app_secret?: string | null
  /** 手输新建应用时的备注名（缺省取 App ID） */
  app_name?: string
  app_token: string
  base_url?: string
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
