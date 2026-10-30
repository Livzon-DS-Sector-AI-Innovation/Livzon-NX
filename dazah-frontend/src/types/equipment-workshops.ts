// ==================== 设备车间注册表 ====================

/** 车间摘要（工作台车间块与飞书配置页清单数据源） */
export interface WorkshopSummary {
  code: string
  name: string
  is_enabled: boolean
}

/** 车间管理页条目（含停用车间的完整清单） */
export interface WorkshopAdminSummary extends WorkshopSummary {
  /** 车间维修群 chat_id；派单卡按此路由，空则回落全局默认群 */
  feishu_chat_id?: string | null
  created_at: string
}

export interface WorkshopCreateRequest {
  /** 三位数字，可选 -序号（如 204 / 204-1），创建后不可改 */
  code: string
  name: string
  /** 车间维修群 chat_id（oc_ 开头，可后补） */
  feishu_chat_id?: string | null
}

export interface WorkshopUpdateRequest {
  /** 留空/ null 表示不改 */
  name?: string | null
  is_enabled?: boolean | null
  /** 车间维修群 chat_id；传空字符串清除 */
  feishu_chat_id?: string | null
}
