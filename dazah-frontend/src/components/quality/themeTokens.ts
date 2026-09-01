/**
 * 质量模块高频语义色收敛（DESIGN.md §2/§11：不散落重复颜色常量）。
 * 颜色值应与 antd 主题 token 语义对齐；一次性特殊色保留在组件内。
 */
export const qualityTokens = {
  /** 品牌紫（部门联系人/登录品牌） */
  brand: '#6f5ef9',
  /** 品牌紫浅底 */
  brandSoft: '#f3f0ff',
  /** 主色（antd primary） */
  primary: '#1677ff',
  /** 主色浅底 */
  primarySoft: '#e6f4ff',
  /** 成功 */
  success: '#1aae39',
  /** 成功浅底 */
  successSoft: '#f0faf0',
  /** 警告橙 */
  warning: '#fa8c16',
  /** 警告浅底 */
  warningSoft: '#fff7e6',
  /** 橙色文本（强调） */
  orangeText: '#dd5b00',
  /** 文本一级（近黑） */
  textPrimary: '#0f172a',
  /** 文本二级 */
  textSecondary: '#64748b',
  /** 文本三级 */
  textTertiary: '#94a3b8',
  /** 文本弱化 */
  textMuted: '#787671',
  /** 边框/分隔线 */
  border: '#e2e8f0',
  /** 浅边框 */
  borderLight: '#f0f0f0',
  /** 浅灰底 */
  bgSoft: '#fafafa',
} as const
