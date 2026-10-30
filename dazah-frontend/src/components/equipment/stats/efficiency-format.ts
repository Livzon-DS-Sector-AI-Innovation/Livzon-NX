// 维修效能卡组共用的分钟格式化
export function fmtMinutes(v: number): string {
  if (v >= 60) {
    const h = Math.floor(v / 60)
    const m = Math.round(v % 60)
    return m > 0 ? `${h}小时${m}分` : `${h}小时`
  }
  return `${Math.round(v)}分钟`
}
