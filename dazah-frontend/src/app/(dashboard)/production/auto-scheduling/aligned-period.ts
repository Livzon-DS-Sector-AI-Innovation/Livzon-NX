import dayjs, { type Dayjs } from 'dayjs'

/** 任意日期 → 所在扎帐周期（27 日～次月 26 日）的起止 */
export function accountingPeriodOf(day: Dayjs): [Dayjs, Dayjs] {
  const start = day.date() >= 27 ? day.date(27) : day.subtract(1, 'month').date(27)
  const end = start.add(1, 'month').date(26)
  return [start, end]
}

/** 参数周期对齐提示：起始/截止各自归到所在扎帐周期，最多跨两个月 */
export function alignedPeriodHint(
  period: [Dayjs | null, Dayjs | null] | null,
): string | null {
  if (!period?.[0] || !period?.[1]) return null
  const start = accountingPeriodOf(period[0])[0]
  const end = accountingPeriodOf(period[1])[1]
  if (end.diff(start, 'day') > 62) {
    return `对齐后为 ${start.format('YYYY/MM/DD')}～${end.format('YYYY/MM/DD')}，跨度超过两个月，请重新选择`
  }
  return `将生成 ${start.format('YYYY/MM/DD')}～${end.format('YYYY/MM/DD')}（起止各自对齐到所在扎帐周期）`
}

/** 对齐后是否超两个月（超限禁止生成，与后端校验一致） */
export function isPeriodOverlong(period: [Dayjs | null, Dayjs | null] | null): boolean {
  if (!period?.[0] || !period?.[1]) return false
  const start = accountingPeriodOf(period[0])[0]
  const end = accountingPeriodOf(period[1])[1]
  return end.diff(start, 'day') > 62
}

// dayjs 供类型引用方复用（避免各处重复导入差异）
export { dayjs }
