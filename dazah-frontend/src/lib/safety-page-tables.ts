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
  hazardQuickReport: 'safety:risk-hazard:hazard-inspection:hazard-quick-report',
  dailyRiskReport: 'safety:ops-safety:daily-risk-report',
  specialDangerWork: 'safety:ops-safety:special-danger-work',
  riskWorkRegistration: 'safety:ops-safety:risk-work-registration',
  feedingInspection: 'safety:ops-safety:feeding-inspection',
  hazchemUnloadingInspection: 'safety:ops-safety:hazchem-unloading-inspection',
  centrifugeDischargeInspection:
    'safety:ops-safety:centrifuge-discharge-inspection',
  fireEquipmentInspection:
    'safety:emergency-accident:fire-equipment-inspection',
  ehsChangeReview: 'safety:risk-hazard:ehs-change:ehs-change-review',
  ehsChangeAcceptance: 'safety:risk-hazard:ehs-change:ehs-change-acceptance',
} as const

/**
 * 镜像页表格优先展示的关键列（按声明顺序，列名与飞书表字段一致）。
 * 命中的字段按此顺序作为表格摘要列，其余字段点击行后在详情抽屉查看；
 * 实际字段与声明基本对不上（换绑子表或字段改名）时回退自动摘要。
 * 不在此列的页面保持自动摘要行为。
 */
export const SAFETY_PAGE_TABLE_PREFERRED_COLUMNS: Record<string, string[]> = {
  [SAFETY_PAGE_TABLE_KEYS.ehsChangeReview]: [
    '申请编号',
    '申请状态',
    '发起时间',
    '完成时间',
    '变更申请人',
    '变更申请部门',
    '变更名称',
    '变更分类',
    '变更级别',
    '申请变更原因',
    '预计效果',
    '变更风险评估及建议措施',
  ],
  [SAFETY_PAGE_TABLE_KEYS.ehsChangeAcceptance]: [
    '申请编号',
    '申请状态',
    '审批流程',
    '发起时间',
    '发起人',
    '部门',
    '变更级别',
    '变更验收日期',
    '变更情况描述',
    '变更审批人验收意见',
    '变更验收人',
  ],
}

/**
 * 镜像页「新增」按钮的跳转链接（飞书审批填单页等新建入口，点击新开飞书）。
 * 数据读取仍走页面绑定的多维表格；链接变更时只改这里。
 */
export const SAFETY_PAGE_TABLE_CREATE_URLS: Record<string, string> = {
  [SAFETY_PAGE_TABLE_KEYS.ehsChangeReview]: 'https://applink.feishu.cn/T9aVmYNY9oKR',
  [SAFETY_PAGE_TABLE_KEYS.ehsChangeAcceptance]: 'https://applink.feishu.cn/T9aVn44berv1',
}

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
export type PageTableTab = components['schemas']['PageTableTab']

/** 多页签页面的子表清单（normalize 后供组件使用）。 */
export function toPageTableTabs(
  tabs: Array<{
    table_id?: string
    tab_name?: string
    is_primary?: boolean
    record_count?: number
  }> | null | undefined,
): PageTableTab[] {
  return (tabs ?? [])
    .filter((tab) => Boolean(tab.table_id))
    .map((tab) => ({
      table_id: String(tab.table_id),
      tab_name: String(tab.tab_name ?? tab.table_id),
      is_primary: Boolean(tab.is_primary),
      record_count: Number(tab.record_count ?? 0),
    }))
}

/** 附件 URL 构造带上 table_id（多页签页面区分附件归属子表）。

 * 以 /content 结尾：共享渲染器会把 /content 重写为 /thumbnail 取小图。 */
export function pageTableAttachmentUrl(
  pageKey: string,
  recordId: string,
  fieldName: string,
  fileToken: string,
  options?: { tableId?: string | null; inline?: boolean },
): string {
  const base = `/api/v1/safety/page-tables/${encodeURIComponent(pageKey)}/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fieldName)}/${encodeURIComponent(fileToken)}/content`
  const params = new URLSearchParams()
  if (options?.tableId) params.set('table_id', options.tableId)
  if (options?.inline) params.set('inline', 'true')
  const query = params.toString()
  return query ? `${base}?${query}` : base
}

type ApiStats = components['schemas']['PageTableStatsResponse']
type ApiGroup = NonNullable<ApiStats['groups']>[number]
type ApiBucket = NonNullable<ApiGroup['buckets']>[number]

/** 未关闭记录按目标完成日期的到期分布（到期提醒卡）。 */
export type PageTableDueSummary = {
  overdue: number
  within_7: number
  within_15: number
  within_30: number
}

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
  due_summary: PageTableDueSummary | null
}

/** 生成类型的数组字段都是可选的，这里统一补默认值。 */
export function toPageTableStats(
  stats: ApiStats | null | undefined
): PageTableStats | null {
  if (!stats) return null
  const groups = stats.groups ?? []
  const due = stats.due_summary
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
    due_summary: due
      ? {
          overdue: due.overdue ?? 0,
          within_7: due.within_7 ?? 0,
          within_15: due.within_15 ?? 0,
          within_30: due.within_30 ?? 0,
        }
      : null,
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
