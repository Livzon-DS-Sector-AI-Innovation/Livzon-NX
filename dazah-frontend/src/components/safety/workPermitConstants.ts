'use client'

/**
 * 8 大特殊作业票前端常量（票种/级别/状态中文映射）。
 * 完整票面模板（措施清单/字段）以 /safety/work-permits/meta 接口为准，
 * 这里只放列表与详情渲染所需的稳定文案映射。
 */

export const PERMIT_TYPE_LABELS: Record<string, string> = {
  hot_work: '动火作业',
  confined_space: '受限空间作业',
  blind_plate: '盲板抽堵作业',
  height_work: '高处作业',
  lifting: '吊装作业',
  temporary_electricity: '临时用电作业',
  excavation: '动土作业',
  road_breaking: '断路作业',
}

export const PERMIT_LEVEL_LABELS: Record<string, string> = {
  special: '特级',
  grade1: '一级',
  grade2: '二级',
  grade3: '三级',
  none: '不分级别',
}

export const PERMIT_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  pending_approval: '审批中',
  approved: '已批准',
  active: '作业中',
  completed: '已完工',
  rejected: '已驳回',
  cancelled: '已作废',
}

export const NODE_KIND_LABELS: Record<string, string> = {
  approve: '审批',
  confirm: '确认',
  verify: '作业前验票',
  accept: '完工验收',
}

export function permitStatusLabel(status: string): string {
  return PERMIT_STATUS_LABELS[status] ?? status
}

export function permitTypeLabel(type: string): string {
  return PERMIT_TYPE_LABELS[type] ?? type
}

export function permitLevelLabel(level: string): string {
  return PERMIT_LEVEL_LABELS[level] ?? level
}
