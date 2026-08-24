// 班组交接确认类型

export interface ShiftHandoverRecord {
  id: string
  position: string
  workshop: string
  shift: string
  handover_time: string
  handover_from: string
  handover_to: string
  production_status?: string | null
  equipment_status?: string | null
  equipment_inspection?: string | null
  tools_handover?: string | null
  fire_emergency?: string | null
  ppe_status?: string | null
  remarks?: string | null
  status: string
  confirmed_at?: string | null
  created_at: string
  updated_at: string
}

export interface ShiftHandoverCreate {
  position: string
  workshop: string
  shift: string
  handover_time: string
  handover_from: string
  handover_to: string
  production_status?: string | null
  equipment_status?: string | null
  equipment_inspection?: string | null
  tools_handover?: string | null
  fire_emergency?: string | null
  ppe_status?: string | null
  remarks?: string | null
}

export interface ShiftHandoverUpdate {
  position?: string
  workshop?: string
  shift?: string
  handover_time?: string
  handover_from?: string
  handover_to?: string
  production_status?: string | null
  equipment_status?: string | null
  equipment_inspection?: string | null
  tools_handover?: string | null
  fire_emergency?: string | null
  ppe_status?: string | null
  remarks?: string | null
}

// 预设岗位选项（用户可手动添加）
export const DEFAULT_POSITIONS = [
  '发酵操作工',
  '化验员',
  '工艺员',
  '班组长',
  '车间主任',
  '设备员',
  '安全员',
]

// 车间列表
export const WORKSHOP_OPTIONS = [
  '101一车间', '101二车间', '102一车间', '102二车间',
  '103车间', '201一车间', '201二车间', '201三车间',
  '202车间', '203车间', '203三车间',
]

// 排班模式
export type ScheduleMode = '4-3' | '3-2'

export const SCHEDULE_MODES: { value: ScheduleMode; label: string }[] = [
  { value: '4-3', label: '四班三倒' },
  { value: '3-2', label: '三班两倒' },
]

// 根据排班模式返回班次选项
export function getShiftOptions(mode: ScheduleMode) {
  if (mode === '4-3') {
    return [
      { value: 'morning', label: '早班' },
      { value: 'afternoon', label: '中班' },
      { value: 'night', label: '夜班' },
    ]
  }
  return [
    { value: 'day', label: '白班' },
    { value: 'night', label: '夜班' },
  ]
}

export const SHIFT_LABELS: Record<string, string> = {
  morning: '早班', afternoon: '中班', night: '夜班',
  day: '白班',
}

