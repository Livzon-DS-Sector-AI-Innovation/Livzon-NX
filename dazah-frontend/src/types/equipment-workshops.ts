// ==================== 设备车间注册表 ====================

/** 车间摘要（工作台车间块与飞书配置页清单数据源） */
export interface WorkshopSummary {
  code: string
  name: string
  is_enabled: boolean
}

/** 车间管理页条目（含停用车间的完整清单） */
export interface WorkshopAdminSummary extends WorkshopSummary {
  created_at: string
}

export interface WorkshopCreateRequest {
  /** 三位数字，可选 -序号（如 204 / 204-1），创建后不可改 */
  code: string
  name: string
}

export interface WorkshopUpdateRequest {
  /** 留空/ null 表示不改 */
  name?: string | null
  is_enabled?: boolean | null
}
