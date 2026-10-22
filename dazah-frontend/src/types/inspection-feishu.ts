// ==================== 设备巡检飞书镜像（只读展示） ====================
// 契约类型统一从 @/types/generated/schema 别名导出；筛选等前端专属类型保留手写。
import type { components } from '@/types/generated/schema'

type Schemas = components['schemas']

export type InspectionFeishuSource = 'today' | 'history'

export type InspectionFeishuTodayStatus = 'inspected' | 'abnormal' | 'pending'

export type InspectionFeishuRecord = Schemas['EquipmentInspectionFeishuRecordItem']

export type InspectionFeishuDevice = Schemas['EquipmentInspectionFeishuDeviceItem']

export type InspectionFeishuDeviceList = Schemas['EquipmentInspectionFeishuDeviceList']

export type InspectionFeishuSyncState = Schemas['EquipmentFeishuSyncStateItem']

export type InspectionFeishuSyncStatus = Schemas['EquipmentFeishuSyncStatus']

export type InspectionFeishuTodaySummary = Schemas['EquipmentInspectionTodaySummary']

export type InspectionFeishuWorkshopSummary =
  Schemas['EquipmentInspectionTodaySummaryEntry']

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

/** 自建应用库条目（Secret 不回显明文） */
export type FeishuAppItem = Schemas['EquipmentFeishuAppItem']

export type FeishuAppCreateRequest = Schemas['EquipmentFeishuAppCreateRequest']

export type FeishuAppUpdateRequest = Schemas['EquipmentFeishuAppUpdateRequest']

export type InspectionFeishuConfigDetail =
  Schemas['EquipmentInspectionFeishuConfigDetail']

export type InspectionFeishuConfigUpdateRequest =
  Schemas['EquipmentInspectionFeishuConfigUpdateRequest']

export type InspectionFeishuConfigTestResult =
  Schemas['EquipmentInspectionFeishuConfigTestResult']
