// 设备模块类型：契约类型统一从 @/types/generated/schema 别名导出，
// 仅业务枚举、筛选与列表包装等前端专属类型在本文件维护。
import type { components } from '@/types/generated/schema'

type Schemas = components['schemas']

// ==================== 业务枚举（与后端 Literal 保持一致） ====================
export type EquipmentStatus = '在用' | '备用' | '维修中' | '停用' | '报废'
export type EquipmentImportance = '高' | '中' | '低'
export type FailureCodeType = 'symptom' | 'cause' | 'action'
export type WorkOrderType = '故障维修' | '计划维护' | '巡检' | '校准' | '异常处理' | '日常维护'
export type WorkOrderPriority = '紧急' | '高' | '中' | '低'
export type WorkOrderStatus = '待处理' | '执行中' | '待验收' | '已完成' | '已关闭'
export type VerificationResult = '合格' | '不合格'
export type CalibrationType = '内部校准' | '外部检定'
export type CalibrationResult = '合格' | '不合格'
export type CalibrationPlanStatus = '启用' | '停用'
export type MaintenancePlanType = '预防性维护' | '预测性维护'
export type MaintenancePlanStatus = '启用' | '停用' | '已完成'
export type FrequencyUnit = '天' | '周' | '月' | '年'

// ==================== 响应契约（生成类型别名） ====================
export type EquipmentCategory = Schemas['EquipmentCategoryResponse'] & {
  children?: EquipmentCategoryTree[]
}
export type EquipmentCategoryTree = Schemas['EquipmentCategoryTree']

export type Location = Schemas['LocationResponse'] & {
  children?: LocationTree[]
}
export type LocationTree = Schemas['LocationTree']

export type Equipment = Schemas['EquipmentResponse']

export type FailureCode = Schemas['FailureCodeResponse']

export type WorkOrder = Schemas['WorkOrderResponse']
export type WorkOrderImage = Schemas['WorkOrderImageResponse']

export type CalibrationPlan = Schemas['CalibrationPlanResponse']
export type CalibrationRecord = Schemas['CalibrationRecordResponse']

export type SparePart = Schemas['SparePartListItem']
export type StockWarning = Schemas['StockWarningResponse']

export type MaintenancePlan = Schemas['MaintenancePlanResponse']

export type MaterialRecord = Schemas['MaterialConsumeResponse']

// 检查项模板暂无独立查询端点（未进入 OpenAPI），保留手写契约
export interface InspectionTemplateItem {
  id: string
  template_id: string
  item_name: string
  item_description: string | null
  expected_result: string | null
  check_method: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export type ClaimTimeoutConfig = Schemas['ClaimTimeoutConfig']

export type Maintainer = Schemas['MaintainerOption']

export type DepartmentOption = Schemas['DepartmentOption']

// ==================== 台账 Excel 导入 ====================
export type EquipmentImportFailure = Schemas['EquipmentImportFailure']
export type EquipmentImportResult = Schemas['EquipmentImportResult']

// ==================== 台账上传存档（回看历次上传） ====================
export type EquipmentImportArchiveSummary = Omit<
  Schemas['EquipmentLedgerArchiveSummary'],
  'import_summary'
> & {
  import_summary: Partial<EquipmentImportResult> | null
}

export type EquipmentImportArchive = Omit<
  Schemas['EquipmentLedgerArchiveDetail'],
  'import_summary' | 'merges'
> & {
  import_summary: Partial<EquipmentImportResult> | null
  /** 合并单元格（0-based 行列坐标） */
  merges: Array<{ s: { r: number; c: number }; e: { r: number; c: number } }>
}

// ==================== 统计（by_status 前端按状态枚举收窄） ====================
export type EquipmentStatistics = Omit<Schemas['EquipmentStatistics'], 'by_status'> & {
  by_status: Record<EquipmentStatus, number>
}

export type WorkOrderStatistics = Omit<Schemas['WorkOrderStatistics'], 'by_status'> & {
  by_status: Record<WorkOrderStatus, number>
}

// ==================== 请求契约（生成类型别名） ====================
export type CreateCategoryInput = Schemas['EquipmentCategoryCreate']
export type UpdateCategoryInput = Schemas['EquipmentCategoryUpdate']
export type CreateLocationInput = Schemas['LocationCreate']
export type UpdateLocationInput = Schemas['LocationUpdate']
export type CreateEquipmentInput = Schemas['EquipmentCreate']
export type UpdateEquipmentInput = Schemas['EquipmentUpdate']
export type CreateFailureCodeInput = Schemas['FailureCodeCreate']
export type UpdateFailureCodeInput = Schemas['FailureCodeUpdate']
export type CreateWorkOrderInput = Schemas['WorkOrderCreate']
export type UpdateWorkOrderInput = Schemas['WorkOrderUpdate']
export type AssignWorkOrderInput = Schemas['WorkOrderAssign']
export type CompleteWorkOrderInput = Schemas['WorkOrderComplete']
export type VerifyWorkOrderInput = Schemas['WorkOrderVerify']
export type CreateCalibrationPlanInput = Schemas['CalibrationPlanCreate']
export type UpdateCalibrationPlanInput = Schemas['CalibrationPlanUpdate']
export type CreateCalibrationRecordInput = Schemas['CalibrationRecordCreate']
export type CreateSparePartInput = Schemas['SparePartCreate']
export type UpdateSparePartInput = Schemas['SparePartUpdate']
export type StockInboundInput = Schemas['StockInboundRequest']
export type CreateMaintenancePlanInput = Schemas['MaintenancePlanCreate']
export type UpdateMaintenancePlanInput = Schemas['MaintenancePlanUpdate']
export type InspectionRecordItem = Schemas['InspectionRecordItem']
export type InspectionCompleteInput = Schemas['InspectionCompleteRequest']
export type MaterialConsumeItem = Schemas['MaterialConsumeItem']
export type MaterialConsumeInput = Schemas['MaterialConsumeRequest']
export type UpdateClaimTimeoutInput = Schemas['ClaimTimeoutUpdateRequest']

// ==================== 前端专属：筛选与列表包装 ====================
export interface EquipmentFilters {
  workshop?: string
  category_id?: string
  location_id?: string
  department_id?: string
  status?: EquipmentStatus
  keyword?: string
  page?: number
  page_size?: number
}

export interface EquipmentListResponse {
  items: Equipment[]
  total: number
  page: number
  page_size: number
}

export interface WorkOrderFilters {
  workshop?: string
  status?: WorkOrderStatus
  equipment_id?: string
  priority?: WorkOrderPriority
  order_type?: WorkOrderType
  page?: number
  page_size?: number
}

export interface WorkOrderListResponse {
  items: WorkOrder[]
  total: number
  page: number
  page_size: number
}

export interface CalibrationPlanFilters {
  workshop?: string
  equipment_id?: string
  status?: CalibrationPlanStatus
  page?: number
  page_size?: number
}

export interface CalibrationPlanListResponse {
  items: CalibrationPlan[]
  total: number
  page: number
  page_size: number
}

export interface CalibrationRecordFilters {
  workshop?: string
  equipment_id?: string
  plan_id?: string
  page?: number
  page_size?: number
}

export interface CalibrationRecordListResponse {
  items: CalibrationRecord[]
  total: number
  page: number
  page_size: number
}

export interface SparePartFilters {
  workshop?: string
  category?: string
  keyword?: string
  is_active?: boolean
  page?: number
  page_size?: number
}

export interface SparePartListResponse {
  items: SparePart[]
  total: number
  page: number
  page_size: number
}

export interface MaintenancePlanFilters {
  workshop?: string
  equipment_id?: string
  status?: MaintenancePlanStatus
  keyword?: string
  page?: number
  page_size?: number
}

export interface MaintenancePlanListResponse {
  items: MaintenancePlan[]
  total: number
  page: number
  page_size: number
}
