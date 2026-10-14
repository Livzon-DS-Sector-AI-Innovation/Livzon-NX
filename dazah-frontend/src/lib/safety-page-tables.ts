/**
 * 安全模块「页面 ↔ 飞书多维表格」镜像页的页面标识、列类型与值解析。
 *
 * 页面标识必须与后端 `app/modules/safety/page_tables.py` 的注册表一致：
 * 它同时是页面权限键、请求头 `X-Dazah-Page-Key` 与接口路径参数。
 * 列/记录类型直接复用 OpenAPI 生成类型，避免与后端契约漂移。
 */

import type { components } from '@/types/generated/schema'

export const SAFETY_PAGE_TABLE_KEYS = {
  hazardDuty: 'safety:risk-hazard:hazard-inspection:hazard-duty',
  dailyRiskReport: 'safety:ops-safety:daily-risk-report',
  specialDangerWork: 'safety:ops-safety:special-danger-work',
  riskWorkRegistration: 'safety:ops-safety:risk-work-registration',
  feedingInspection: 'safety:ops-safety:feeding-inspection',
  hazchemUnloadingInspection: 'safety:ops-safety:hazchem-unloading-inspection',
  centrifugeDischargeInspection:
    'safety:ops-safety:centrifuge-discharge-inspection',
} as const

/**
 * 默认按「当天」筛选的镜像页（日报/巡查类，数据量大且只关心当天）。
 * 不在名单内的页面默认显示全部记录（如报备表：数据量小且历史都要看）。
 */
export const SAFETY_PAGE_TABLE_DEFAULT_TODAY = new Set<string>([
  SAFETY_PAGE_TABLE_KEYS.dailyRiskReport,
  SAFETY_PAGE_TABLE_KEYS.specialDangerWork,
  SAFETY_PAGE_TABLE_KEYS.feedingInspection,
  SAFETY_PAGE_TABLE_KEYS.hazchemUnloadingInspection,
  SAFETY_PAGE_TABLE_KEYS.centrifugeDischargeInspection,
])

/** 「安全飞书设置」页（页面表格绑定的配置入口）。 */
export const SAFETY_FEISHU_SETTINGS_PAGE_KEY =
  'safety:system-config:safety-feishu-settings'

export type PageTableColumn = components['schemas']['PageTableColumn']
export type PageTableAttachment = components['schemas']['PageTableAttachmentItem']
export type PageTableStatGroup = components['schemas']['PageTableStatGroup']

type ApiStats = components['schemas']['PageTableStatsResponse']
type ApiGroup = NonNullable<ApiStats['groups']>[number]
type ApiBucket = NonNullable<ApiGroup['buckets']>[number]

/** 仪表盘聚合（字段已补默认值，服务端与客户端共用）。 */
export type PageTableStats = {
  page_key: string
  page_name: string
  total: number
  groups: {
    field: string
    kind: string
    mode: string
    buckets: ApiBucket[]
  }[]
}

/** 生成类型的数组字段都是可选的，这里统一补默认值。 */
export function toPageTableStats(
  stats: ApiStats | null | undefined
): PageTableStats | null {
  if (!stats) return null
  const groups = stats.groups ?? []
  return {
    page_key: stats.page_key,
    page_name: stats.page_name,
    total: stats.total,
    groups: groups.map((group: ApiGroup) => ({
      field: group.field,
      kind: group.kind,
      mode: group.mode,
      buckets: (group.buckets ?? []).map((bucket: ApiBucket) => ({
        key: bucket.key,
        count: bucket.count,
      })),
    })),
  }
}
export type PageTablePerson = {
  id: string
  name: string
  avatar_url?: string | null
}
export type PageTableUrl = { link: string; text: string }

/** 一条记录：字段值由后端按列类型解码，前端只按 kind 做窄化。 */
export type PageTableRecordRow = {
  record_id: string
  fields: Record<string, unknown>
}

/** 后端 field_codec 使用的控件类型（`PageTableColumn.kind` 的取值）。 */
export type PageTableFieldKind =
  | 'text'
  | 'number'
  | 'select'
  | 'multi_select'
  | 'date'
  | 'checkbox'
  | 'person'
  | 'phone'
  | 'url'
  | 'attachment'
  | 'readonly'

/** 生成类型的数组/对象字段都是可选的，这里统一补默认值，避免散落断言。 */
export function toRecordRow(row: {
  record_id: string
  fields?: Record<string, unknown> | null
}): PageTableRecordRow {
  return { record_id: row.record_id, fields: row.fields ?? {} }
}

export function toRecordRows(
  rows: ReadonlyArray<{ record_id: string; fields?: Record<string, unknown> | null }> | undefined
): PageTableRecordRow[] {
  return (rows ?? []).map(toRecordRow)
}

export function columnOptions(column: PageTableColumn): string[] {
  return column.options ?? []
}

export function asAttachmentList(value: unknown): PageTableAttachment[] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (item): item is PageTableAttachment =>
      typeof item === 'object' && item !== null && 'file_token' in item
  )
}

export function asPersonList(value: unknown): PageTablePerson[] {
  if (!Array.isArray(value)) return []
  return value
    .filter(
      (item): item is PageTablePerson =>
        typeof item === 'object' && item !== null && 'id' in item
    )
    .map((item) => ({
      id: String(item.id),
      name: String(item.name ?? ''),
      avatar_url: item.avatar_url ? String(item.avatar_url) : null,
    }))
}

export function asUrlValue(value: unknown): PageTableUrl | null {
  if (typeof value === 'object' && value !== null && 'link' in value) {
    const link = String((value as PageTableUrl).link ?? '')
    if (!link) return null
    return { link, text: String((value as PageTableUrl).text ?? link) }
  }
  return null
}

/** 只读展示文本（表格单元格与详情标题共用）。 */
export function displayFieldText(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    if (!value.length) return ''
    const first = value[0]
    if (typeof first === 'object' && first !== null && 'name' in first) {
      return asPersonList(value)
        .map((person) => person.name || person.id)
        .join('、')
    }
    return value.map((item) => String(item)).join('、')
  }
  const url = asUrlValue(value)
  if (url) return url.text || url.link
  return ''
}

/** 默认日期列：优先名称含「日期」的日期字段，否则第一个日期字段。 */
export function pickDefaultDateColumn(
  columns: PageTableColumn[] | undefined | null
): PageTableColumn | null {
  const dateColumns = (columns ?? []).filter((column) => column.kind === 'date')
  return (
    dateColumns.find((column) => column.name.includes('日期')) ??
    dateColumns[0] ??
    null
  )
}

/** 多条件筛选的候选项：带选项的单选/多选列。 */
export function pickConditionSelectColumns(
  columns: PageTableColumn[] | undefined | null
): PageTableColumn[] {
  return (columns ?? []).filter(
    (column) =>
      (column.kind === 'select' || column.kind === 'multi_select') &&
      columnOptions(column).length > 0
  )
}

/** 可内联预览的附件类型（与后端预览白名单一致）。 */
export const INLINE_PREVIEW_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
]

export function isPreviewableAttachment(attachment: PageTableAttachment): boolean {
  return INLINE_PREVIEW_TYPES.includes(attachment.type || '')
}
