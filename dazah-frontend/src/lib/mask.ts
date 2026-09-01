/**
 * 敏感字段脱敏（DESIGN.md §8：敏感字段默认脱敏）。
 * 空值/短值原样返回，避免渲染出纯星号噪音。
 */

/** 手机号：138****1234（保留前 3 后 4） */
export function maskPhone(v?: string | null): string {
  const s = (v || '').trim()
  if (!s) return '-'
  if (s.length < 8) return s
  return `${s.slice(0, 3)}****${s.slice(-4)}`
}

/** 身份证号：保留前 6 后 4，中间星号 */
export function maskIdCard(v?: string | null): string {
  const s = (v || '').trim()
  if (!s) return '-'
  if (s.length < 11) return s
  return `${s.slice(0, 6)}${'*'.repeat(s.length - 10)}${s.slice(-4)}`
}

/** 银行卡号：仅保留后 4 位 */
export function maskBankAccount(v?: string | null): string {
  const s = (v || '').trim()
  if (!s) return '-'
  if (s.length < 8) return s
  return `****${s.slice(-4)}`
}

/** 通用：保留前 keepHead 后 keepTail，中间星号（地址等长文本可用） */
export function maskMiddle(v?: string | null, keepHead = 4, keepTail = 0): string {
  const s = (v || '').trim()
  if (!s) return '-'
  if (s.length <= keepHead + keepTail) return s
  // keepTail=0 时 slice(-0) 等价 slice(0)，会把原文整体回显，须显式置空
  const tail = keepTail > 0 ? s.slice(-keepTail) : ''
  return `${s.slice(0, keepHead)}${'*'.repeat(Math.min(6, s.length - keepHead - keepTail))}${tail}`
}
