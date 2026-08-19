/** 生产模块飞书配置（前端类型） */

export interface ProductionFeishuConfig {
  id: string | null
  name: string
  product_name: string
  app_id: string
  bitable_app_token: string
  table_id: string
  sync_target: string
  is_active: boolean
  remark: string | null
  app_secret_configured: boolean
  app_secret_masked: string
  created_at: string | null
  updated_at: string | null
}

export interface ProductionFeishuConfigUpsert {
  name: string
  product_name: string
  app_id: string
  app_secret?: string
  bitable_app_token: string
  table_id: string
  sync_target: string
  is_active: boolean
  remark?: string
}

export interface ProductionFeishuTable {
  id: string | null
  app_token: string
  table_id: string
  name: string
  is_enabled: boolean
  field_count: number
  record_count: number
  sync_status: string | null
  sync_error: string | null
  last_synced_at: string | null
}

export interface ProductionFeishuConnectivityResult {
  ok: boolean
  steps: Array<{
    name: string
    status: 'ok' | 'warning' | 'error'
    message: string
  }>
}

export interface ProductionFeishuTableSyncResult {
  table: ProductionFeishuTable
  record_count: number
}

export interface ProductionFeishuWsStatus {
  connected: boolean
  last_error: string | null
}
