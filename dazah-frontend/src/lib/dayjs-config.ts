import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

// 全局设置 dayjs 为中文
dayjs.locale('zh-cn')

export const HR_DISPLAY_DATE_FORMAT = 'YYYY.MM.DD'

export function fmtTrainingDatetime(value?: string | null): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY.MM.DD HH:mm') : value
}
