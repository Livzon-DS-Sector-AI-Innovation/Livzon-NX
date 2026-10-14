/**
 * 质量模块高频语义色收敛（DESIGN.md §2/§11：不散落重复颜色常量）。
 * 颜色值应与 antd 主题 token 语义对齐；一次性特殊色保留在组件内。
 */
export const qualityTokens = {
  /** 品牌紫（登录品牌） */
  brand: '#6f5ef9',
  /** 品牌紫浅底 */
  brandSoft: 'var(--color-primary-soft)',
  /** 主色（antd primary） */
  primary: '#1677ff',
  /** 主色浅底 */
  primarySoft: 'var(--color-info-soft)',
  /** 成功 */
  success: '#1aae39',
  /** 成功浅底 */
  successSoft: 'var(--color-success-soft)',
  /** 警告橙 */
  warning: '#fa8c16',
  /** 警告浅底 */
  warningSoft: 'var(--color-warning-soft)',
  /** 橙色文本（强调） */
  orangeText: '#dd5b00',
  /** 文本一级（近黑） */
  textPrimary: 'var(--color-ink)',
  /** 文本二级 */
  textSecondary: 'var(--color-slate)',
  /** 文本三级 */
  textTertiary: 'var(--color-steel)',
  /** 文本弱化 */
  textMuted: 'var(--color-steel)',
  /** 边框/分隔线 */
  border: 'var(--color-hairline)',
  /** 浅边框 */
  borderLight: 'var(--color-hairline-soft)',
  /** 浅灰底 */
  bgSoft: 'var(--color-surface-soft)',
} as const
