import dayjs from 'dayjs'

/** 最后工作日当天仍在职；缺少有效日期时不推断状态。 */
export function getOffboardingEmploymentStatus(
  lastWorkingDay: string | undefined,
  today = dayjs().format('YYYY-MM-DD'),
): '在职' | '离职' | null {
  if (!lastWorkingDay || !/^\d{4}-\d{2}-\d{2}$/.test(lastWorkingDay)) return null
  const date = dayjs(lastWorkingDay)
  if (!date.isValid() || date.format('YYYY-MM-DD') !== lastWorkingDay) return null
  return today > lastWorkingDay ? '离职' : '在职'
}
