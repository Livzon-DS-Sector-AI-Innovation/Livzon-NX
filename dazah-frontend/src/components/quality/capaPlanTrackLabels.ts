// CAPA 计划跟踪：进度/提醒状态的中文显示映射。
// 存量数据可能来自飞书同步（中文原文）或本地新建（英文枚举），
// 这里统一映射为平台展示文案，未知值原样透传。

const PROGRESS_LABELS: Record<string, string> = {
  pending: '未开始',
  in_progress: '正在进行',
  completed: '已完成',
  // 存量别名：飞书同步与历史数据
  未开始: '未开始',
  待开始: '未开始',
  进行中: '正在进行',
  正在进行: '正在进行',
  完成: '已完成',
  已完成: '已完成',
}

const REMINDER_LABELS: Record<string, string> = {
  pending: '待提醒',
  reminded: '已提醒',
  confirmed: '已确认',
  // 存量别名：飞书同步与历史数据
  待提醒: '待提醒',
  未提醒: '待提醒',
  已提醒: '已提醒',
  已确认: '已确认',
}

export function progressLabel(value: string | null | undefined): string {
  if (!value) return '-'
  return PROGRESS_LABELS[value] ?? value
}

export function reminderLabel(value: string | null | undefined): string {
  if (!value) return '-'
  return REMINDER_LABELS[value] ?? value
}

export function progressMeta(value: string | null | undefined): { label: string; color: string } {
  const label = progressLabel(value)
  let color = 'default'
  if (label === '已完成') color = 'green'
  else if (label === '正在进行') color = 'processing'
  return { label, color }
}

export function reminderMeta(value: string | null | undefined): { label: string; color: string } {
  const label = reminderLabel(value)
  let color = 'default'
  if (label === '已确认') color = 'green'
  else if (label === '已提醒') color = 'gold'
  return { label, color }
}

// 编辑表单里补上存量中文值，便于编辑从飞书同步过来的旧记录
export const PROGRESS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'pending', label: '未开始' },
  { value: 'in_progress', label: '正在进行' },
  { value: 'completed', label: '已完成' },
  { value: '未开始', label: '未开始' },
  { value: '待开始', label: '未开始' },
  { value: '进行中', label: '正在进行' },
  { value: '正在进行', label: '正在进行' },
  { value: '完成', label: '已完成' },
  { value: '已完成', label: '已完成' },
]

export const REMINDER_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'pending', label: '待提醒' },
  { value: 'reminded', label: '已提醒' },
  { value: 'confirmed', label: '已确认' },
  { value: '待提醒', label: '待提醒' },
  { value: '未提醒', label: '待提醒' },
  { value: '已提醒', label: '已提醒' },
  { value: '已确认', label: '已确认' },
]
