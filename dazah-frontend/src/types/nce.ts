// 非密事件与运行偏差类型

export interface NCERecord {
  id: string
  event_time: string
  restore_time?: string | null
  impact_duration?: string | null
  event_type: string
  workshop: string
  description?: string | null
  impact_scope?: string | null
  action_taken?: string | null
  remarks?: string | null
  created_at: string
  updated_at: string
}

export interface NCECreate {
  event_time: string
  restore_time?: string | null
  impact_duration?: string | null
  event_type: string
  workshop: string
  description?: string | null
  impact_scope?: string | null
  action_taken?: string | null
  remarks?: string | null
}

export type NCEUpdate = Partial<NCECreate>

export const EVENT_TYPES = ['设备微调', '公用工程波动', '其他']

export const WORKSHOP_OPTIONS = [
  '101一车间', '101二车间', '102一车间', '102二车间',
  '103车间', '201一车间', '201二车间', '201三车间',
  '202车间', '203车间', '203三车间', '动力车间',
]
