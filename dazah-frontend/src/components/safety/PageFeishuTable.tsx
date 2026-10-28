'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { CloudUploadOutlined, PlusOutlined, ReloadOutlined, SaveOutlined, SearchOutlined } from '@ant-design/icons'
import {
  App,
  Avatar,
  Button,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'

const { RangePicker } = DatePicker
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

import {
  createSafetyPageTableRecord,
  getSafetyPageTableFieldValues,
  getSafetyPageTableRecords,
  getSafetyPageTableStats,
  updateSafetyPageTableRecord,
  uploadSafetyPageTableAttachment,
} from '@/actions/safety'
import { renderFeishuValue } from '@/components/quality/inspection/renderFeishuValue'
import PageDueReminderCard from '@/components/safety/PageDueReminderCard'
import PageFeishuStatsBar from '@/components/safety/PageFeishuStatsBar'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import {
  asAttachmentList,
  asPersonList,
  asUrlValue,
  columnOptions,
  displayFieldText,
  pageTableAttachmentUrl,
  pickConditionSelectColumns,
  pickDefaultDateColumn,
  toPageTableStats,
  toRecordRows,
  type PageTableColumn,
  type PageTableFieldKind,
  type PageTableRecordRow,
  type PageTableStats,
  type PageTableTab,
} from '@/lib/safety-page-tables'

const PAGE_SIZE_OPTIONS = ['20', '50', '100']

/** 表格最多展示的摘要列数；其余字段点击行后在详情抽屉里查看。 */
const MAX_SUMMARY_COLUMNS = 10
/** 文本列超过该长度视为长文本（措施说明等），只在详情中查看。 */
const LONG_TEXT_THRESHOLD = 80
/** 单选/多选列的选项超过该长度（防护、措施类长句）时按长文本换行渲染。 */
const LONG_OPTION_THRESHOLD = 20
/** 换行列的固定宽度（约每行 10 个汉字，超长内容折行而不是撑宽表格）。 */
const WRAPPED_COLUMN_WIDTH = 150

/**
 * 窄内容列的基准宽度（日期/状态/人员等）：不设宽度的列会被表格均分剩余
 * 空间拉得很宽，固定紧凑宽度后剩余空间留给名称/长文本等主要内容列。
 */
const KIND_BASE_WIDTHS: Partial<Record<PageTableFieldKind, number>> = {
  date: 112,
  select: 110,
  multi_select: 140,
  person: 110,
  number: 90,
  checkbox: 80,
  phone: 120,
  url: 130,
}

/** 状态列（申请状态/巡查状态等）：始终保留在摘要列，方便一眼看到结果。 */
function isStatusColumn(column: PageTableColumn): boolean {
  return (
    (column.kind === 'select' || column.kind === 'multi_select') &&
    column.name.includes('状态')
  )
}

/** 全列模式下需要定宽换行的列：文本列一律换行（短值也不撑宽表格）；
 * 单/多选列按「选项为长句」判定。 */
function buildWrappedColumnNames(columns: PageTableColumn[]): Set<string> {
  const names = new Set<string>()
  for (const column of columns) {
    if (column.kind === 'text' || column.kind === 'readonly') {
      names.add(column.name)
    } else if (
      column.kind === 'select' ||
      column.kind === 'multi_select'
    ) {
      if (
        columnOptions(column).some(
          (option) => option.length > LONG_OPTION_THRESHOLD
        )
      ) {
        names.add(column.name)
      }
    }
  }
  return names
}

/** 计算表格摘要列：剔除勾选清单与长文本列后，状态列保底保留。 */
function buildSummaryColumns(
  columns: PageTableColumn[],
  rows: PageTableRecordRow[]
): PageTableColumn[] {
  const longTextNames = new Set(
    columns
      .filter((column) => column.kind === 'text')
      .map((column) => column.name)
      .filter((name) =>
        rows.some(
          (row) =>
            displayFieldText(row.fields[name]).length > LONG_TEXT_THRESHOLD
        )
      )
  )
  const eligible = columns.filter(
    (column) => column.kind !== 'checkbox' && !longTextNames.has(column.name)
  )
  const statusColumns = eligible.filter(isStatusColumn)
  const others = eligible.filter((column) => !isStatusColumn(column))
  return [
    ...others.slice(0, Math.max(0, MAX_SUMMARY_COLUMNS - statusColumns.length)),
    ...statusColumns,
  ]
}

/**
 * 关键列模式：按页面声明的关键列名取实际存在的列（保持声明顺序），
 * 未命中的字段一律收进详情抽屉。实际字段与声明基本对不上（换绑子表
 * 或飞书字段改名）时返回 null，回退自动摘要，避免表格只剩零星列。
 */
function buildPreferredSummaryColumns(
  columns: PageTableColumn[],
  preferredNames: readonly string[]
): PageTableColumn[] | null {
  const byName = new Map(columns.map((column) => [column.name, column]))
  const matched = preferredNames
    .map((name) => byName.get(name))
    .filter((column): column is PageTableColumn => Boolean(column))
  return matched.length >= Math.min(3, preferredNames.length) ? matched : null
}

function attachmentUrl(
  pageKey: string,
  recordId: string,
  fieldName: string,
  fileToken: string,
  tableId?: string | null
): string {
  // 以 /content 结尾：共享渲染器会把 /content 重写为 /thumbnail 取小图
  return pageTableAttachmentUrl(pageKey, recordId, fieldName, fileToken, {
    tableId: tableId || undefined,
  })
}

/** 附件/人员单元格与详情统一走 QC 验证的共享渲染器（缩略图、头像）。 */
function renderFeishuColumnValue(
  column: PageTableColumn,
  value: unknown,
  row: PageTableRecordRow,
  pageKey: string,
  message: ReturnType<typeof App.useApp>['message'],
  tableId?: string | null
) {
  if (column.kind === 'attachment') {
    const items = asAttachmentList(value)
    if (!items.length) return <Typography.Text type="secondary">—</Typography.Text>
    return renderFeishuValue(items, { record_id: row.record_id }, undefined, message, {
      attachmentUrlBuilder: (_entity, recordId, fileToken) =>
        attachmentUrl(pageKey, recordId, column.name, fileToken, tableId),
    })
  }
  if (column.kind === 'person') {
    const people = asPersonList(value)
    if (!people.length) return <Typography.Text type="secondary">—</Typography.Text>
    return renderFeishuValue(people, { record_id: row.record_id }, undefined, message)
  }
  return undefined
}

/** 表格列里的只读展示（非附件/人员字段）。 */
function renderPlainCellValue(column: PageTableColumn, value: unknown) {
  if (column.kind === 'checkbox') {
    return value ? <Tag color="success">是</Tag> : <Tag>否</Tag>
  }
  if (column.kind === 'select' && value) {
    return <Tag color="processing">{String(value)}</Tag>
  }
  if (column.kind === 'url') {
    const url = asUrlValue(value)
    return url ? (
      <a href={url.link} target="_blank" rel="noreferrer">
        {url.text || '链接'}
      </a>
    ) : (
      <Typography.Text type="secondary">—</Typography.Text>
    )
  }
  const text = displayFieldText(value)
  if (!text) return <Typography.Text type="secondary">—</Typography.Text>
  return text
}

/** 内容较长的文本类列：单元格自动换行（保留换行符），不做省略号截断。 */
function isWrappableColumn(column: PageTableColumn): boolean {
  if (column.kind === 'text' || column.kind === 'readonly') return true
  if (column.kind === 'select' || column.kind === 'multi_select') {
    // 防护/措施类字段的选项本身是长句，按长文本换行渲染而不是 Tag 截断
    return columnOptions(column).some(
      (option) => option.length > LONG_OPTION_THRESHOLD
    )
  }
  return false
}

/** 查询表单的多条件（字段间 AND）。 */
type RecordCondition = { field: string; value: string }

/** 由筛选状态构造查询条件（仅主要列模式使用）。 */
function buildConditions(
  summarize: boolean,
  dateColumn: PageTableColumn | null,
  date: dayjs.Dayjs | null,
  selects: Record<string, string>
): RecordCondition[] {
  if (!summarize) return []
  const conditions: RecordCondition[] = []
  if (dateColumn && date) {
    conditions.push({ field: dateColumn.name, value: date.format('YYYY-MM-DD') })
  }
  for (const [field, value] of Object.entries(selects)) {
    if (value) conditions.push({ field, value })
  }
  return conditions
}

/** 高级筛选栏（下拉字段 + 时间范围）的条件（字段间 AND）。 */
function buildAdvancedConditions(
  fieldFilters: Record<string, string>,
  dateRange: [dayjs.Dayjs | null, dayjs.Dayjs | null] | null,
  dateField: string | null
): Array<{ field: string; value: string; op: 'eq' | 'gte' | 'lte' }> {
  const conditions: Array<{ field: string; value: string; op: 'eq' | 'gte' | 'lte' }> = []
  for (const [field, value] of Object.entries(fieldFilters)) {
    if (value) conditions.push({ field, value, op: 'eq' })
  }
  if (dateField && dateRange) {
    const [from, to] = dateRange
    if (from) conditions.push({ field: dateField, value: from.format('YYYY-MM-DD'), op: 'gte' })
    if (to) conditions.push({ field: dateField, value: to.format('YYYY-MM-DD'), op: 'lte' })
  }
  return conditions
}

/** 把详情抽屉表单值编码为提交给后端的字段负载（日期转字符串、人员取 id）。 */
function buildFormPayload(
  values: Record<string, unknown>,
  editableColumns: PageTableColumn[]
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const column of editableColumns) {
    if (column.kind === 'attachment') continue
    const current = values[column.name]
    if (column.kind === 'date') {
      payload[column.name] = current ? dayjs(current as never).format('YYYY-MM-DD') : null
    } else if (column.kind === 'person') {
      payload[column.name] = ((current as string[]) ?? []).map((id) => ({ id }))
    } else {
      payload[column.name] = current ?? null
    }
  }
  return payload
}

export default function PageFeishuTable({
  pageKey,
  pageName,
  initialData = null,
  initialStats = null,
  initialError = null,
  showStats = true,
  summarizeColumns = false,
  initialDateFilter = null,
  statsGroupBy,
  tabs,
  defaultSortField = null,
  filterFields,
  filterDateField,
  dueField,
  closeField = '关闭状态',
  allowCreate = false,
  preferredColumnNames,
  createUrl,
}: {
  pageKey: string
  pageName: string
  initialData?: {
    columns: PageTableColumn[]
    records: PageTableRecordRow[]
    total: number
    page: number
    page_size: number
    truncated: boolean
  } | null
  initialStats?: PageTableStats | null
  initialError?: string | null
  /** 是否展示顶部统计仪表盘（下钻筛选依赖它；仅仪表盘所属页面开启）。 */
  showStats?: boolean
  /**
   * 表格是否只显示主要列（勾选清单/长文本收进详情，最多 10 列）。
   * 仅作业安全镜像页启用；不传保持全列展示的原有行为。
   */
  summarizeColumns?: boolean
  /**
   * 关键列模式：按名称声明表格优先展示的列（配合 summarizeColumns），
   * 如变更审批页的申请编号/发起时间/变更级别等。声明列按序全量展示
   * （长文本列换行），其余字段只在详情抽屉查看；对不上时回退自动摘要。
   */
  preferredColumnNames?: readonly string[]
  /** 服务端首屏已应用的日期条件（默认当天），客户端以此初始化日期筛选。 */
  initialDateFilter?: RecordCondition | null
  /**
   * 统计分组字段（服务端口径）。表里有多个日期字段时必须显式指定，
   * 否则自动挑选会取 schema 顺序的第一个日期字段（可能是错误的那一个）。
   */
  statsGroupBy?: string[]
  /**
   * 子表清单（多子表页面）。传入后工具栏渲染「数据表」筛选下拉框，切换时
   * 按 table_id 重查记录；不传保持单表页面的原有行为。
   */
  tabs?: PageTableTab[]
  /**
   * 默认排序列（如台账页按「部门/车间」归组）。服务端排序；表格无该字段
   * 的子表由后端自动回退默认顺序。表头点击排序仍可覆盖。
   */
  defaultSortField?: string | null
  /**
   * 筛选栏下拉字段（如 ['部门/车间', '负责人', '关闭状态']）。选项来自
   * /values 接口（按出现次数排序），选择后立即生效并同步到仪表盘。
   */
  filterFields?: string[]
  /** 时间范围筛选字段（日期列），与筛选下拉一起构成列表与仪表盘的过滤。 */
  filterDateField?: string
  /** 到期统计字段（日期列，如 目标完成日期）；传入后仪表盘渲染到期提醒卡。 */
  dueField?: string
  /** 关闭状态字段（默认 关闭状态；值为「已关闭」视为已闭环，不计入到期）。 */
  closeField?: string
  /** 是否允许新建记录（写入当前选中的子表并回写飞书），需操作权限。 */
  allowCreate?: boolean
  /**
   * 「新增」按钮的跳转链接（飞书审批填单页等）：传入后按钮变为新开该链接，
   * 不再使用站内新建抽屉；数据仍来自页面绑定的多维表格。
   */
  createUrl?: string
}) {
  const { message } = App.useApp()
  const { canOperate } = usePagePermissions(pageKey)
  // 当前激活子表（table_id；主表页签用 undefined 走主绑定）
  const primaryTab = tabs?.find((tab) => tab.is_primary)
  const [activeTableId, setActiveTableId] = useState<string | undefined>(
    primaryTab?.table_id
  )
  const activeTableIdRef = useRef<string | undefined>(primaryTab?.table_id)
  const [columns, setColumns] = useState<PageTableColumn[]>(initialData?.columns ?? [])
  const [rows, setRows] = useState<PageTableRecordRow[]>(initialData?.records ?? [])
  const [total, setTotal] = useState(initialData?.total ?? 0)
  const [page, setPage] = useState(initialData?.page ?? 1)
  const [pageSize, setPageSize] = useState(initialData?.page_size ?? 20)
  const [stats, setStats] = useState<PageTableStats | null>(initialStats)
  const [keyword, setKeyword] = useState('')
  const [sortField, setSortField] = useState<string | null>(defaultSortField)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [loading, setLoading] = useState(false)
  const [truncated, setTruncated] = useState(initialData?.truncated ?? false)
  const [loadError, setLoadError] = useState<string | null>(initialError)
  const [dimensionFilter, setDimensionFilter] = useState<{
    field: string
    value: string
  } | null>(null)
  const [detail, setDetail] = useState<PageTableRecordRow | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [uploadingField, setUploadingField] = useState<string | null>(null)
  const requestSeq = useRef(0)

  const editableColumns = useMemo(
    () => columns.filter((column) => column.editable),
    [columns]
  )
  const attachmentColumns = useMemo(
    () => columns.filter((column) => column.kind === 'attachment'),
    [columns]
  )
  // 主要列模式（仅作业安全镜像页开启）：勾选清单与长文本收进详情，截前 N 列；
  // 有关键列声明时按声明列展示（如变更审批页），对不上再回退自动摘要
  const summaryColumns = useMemo(() => {
    if (!summarizeColumns) return columns
    if (preferredColumnNames?.length) {
      const preferred = buildPreferredSummaryColumns(
        columns,
        preferredColumnNames
      )
      if (preferred) return preferred
    }
    return buildSummaryColumns(columns, rows)
  }, [summarizeColumns, preferredColumnNames, columns, rows])
  // 全列模式：长内容列（隐患内容/改善行动/措施等）定宽换行，避免撑宽表格
  const wrappedColumnNames = useMemo(
    () => buildWrappedColumnNames(columns),
    [columns]
  )
  const detailOnlyCount = summarizeColumns
    ? Math.max(0, columns.length - summaryColumns.length)
    : 0
  const dateColumn = useMemo(
    () => pickDefaultDateColumn(columns),
    [columns]
  )
  const conditionSelects = useMemo(
    () =>
      summarizeColumns ? pickConditionSelectColumns(summaryColumns) : [],
    [summarizeColumns, summaryColumns]
  )
  const [dateFilter, setDateFilter] = useState<dayjs.Dayjs | null>(() =>
    initialDateFilter ? dayjs(initialDateFilter.value) : null
  )
  const [selectFilters, setSelectFilters] = useState<Record<string, string>>({})
  // 高级筛选栏：字段下拉 + 时间范围（选项来自 /values，条件同步到仪表盘）
  const [fieldFilters, setFieldFilters] = useState<Record<string, string>>({})
  const [dateRange, setDateRange] = useState<
    [dayjs.Dayjs | null, dayjs.Dayjs | null]
  >([null, null])
  const [filterOptions, setFilterOptions] = useState<
    Record<string, Array<{ value: string; count: number }>>
  >({})
  // 到期提醒卡：时间窗（7/15/30 天）与下钻开关（下钻只作用于列表）
  const [dueWindow, setDueWindow] = useState(7)
  const [dueDrill, setDueDrill] = useState(false)
  // 仅启用高级筛选栏的页面让仪表盘跟随数据表/筛选联动
  const advancedFilterEnabled = Boolean(filterFields?.length || filterDateField)
  // 时间范围筛选只在目标字段确实是日期列的子表展示（如 2024 表的检查内容是文本）
  const filterDateColumn = useMemo(
    () =>
      filterDateField
        ? columns.find(
            (column) => column.name === filterDateField && column.kind === 'date'
          ) ?? null
        : null,
    [columns, filterDateField]
  )

  /**
   * 人员字段的候选项来自当前表格已出现过的人员（含 open_id 与头像）。
   * 这样无需引入飞书通讯录接口即可维护值班人员；新增人员仍在飞书端完成。
   */
  const personOptions = useMemo(() => {
    const byId = new Map<string, { label: string; avatar?: string | null }>()
    for (const column of columns) {
      if (column.kind !== 'person') continue
      for (const row of rows) {
        for (const person of asPersonList(row.fields[column.name])) {
          if (person.id) {
            byId.set(person.id, { label: person.name || person.id, avatar: person.avatar_url })
          }
        }
      }
    }
    return [...byId.entries()].map(([value, meta]) => ({ value, ...meta }))
  }, [columns, rows])

  const load = useCallback(
    async (override?: {
      page?: number
      pageSize?: number
      keyword?: string
      sortField?: string | null
      sortDirection?: 'asc' | 'desc'
      filter?: { field: string; value: string } | null
      conditions?: RecordCondition[]
      tableId?: string | null
      fieldFilters?: Record<string, string>
      dateRange?: [dayjs.Dayjs | null, dayjs.Dayjs | null] | null
      dueDrill?: boolean
      dueWindow?: number
    }) => {
      const nextFieldFilters = override?.fieldFilters ?? fieldFilters
      const nextDateRange =
        override?.dateRange !== undefined ? override.dateRange : dateRange
      const nextDueDrill = override?.dueDrill ?? dueDrill
      const nextDueWindow = override?.dueWindow ?? dueWindow
      const advancedConditions = buildAdvancedConditions(
        nextFieldFilters,
        nextDateRange,
        filterDateField ?? null
      )
      const baseConditions =
        override?.conditions !== undefined
          ? override.conditions
          : buildConditions(
              summarizeColumns,
              dateColumn,
              dateFilter,
              selectFilters
            )
      // 到期下钻只过滤列表：目标完成日期 ≤ 今天+N（含逾期）且未关闭
      const dueDrillConditions =
        nextDueDrill && dueField
          ? [
              {
                field: dueField,
                value: dayjs().add(nextDueWindow, 'day').format('YYYY-MM-DD'),
                op: 'lte' as const,
              },
              { field: closeField, value: '已关闭', op: 'neq' as const },
            ]
          : []
      const next = {
        page: override?.page ?? page,
        pageSize: override?.pageSize ?? pageSize,
        keyword: override?.keyword ?? keyword,
        sortField: override?.sortField !== undefined ? override.sortField : sortField,
        sortDirection: override?.sortDirection ?? sortDirection,
        filter:
          override?.filter !== undefined ? override.filter : dimensionFilter,
        conditions: [...baseConditions, ...advancedConditions, ...dueDrillConditions],
        tableId:
          override?.tableId !== undefined
            ? override.tableId ?? undefined
            : activeTableIdRef.current,
      }
      const seq = requestSeq.current + 1
      requestSeq.current = seq
      setLoading(true)
      const [res, statsRes] = await Promise.all([
        getSafetyPageTableRecords({
          pageKey,
          page: next.page,
          pageSize: next.pageSize,
          keyword: next.keyword || undefined,
          sortField: next.sortField || undefined,
          sortDirection: next.sortDirection,
          filterField: next.filter?.field || undefined,
          filterValue: next.filter?.value || undefined,
          conditions: next.conditions.length ? next.conditions : undefined,
          tableId: next.tableId,
        }),
        showStats
          ? getSafetyPageTableStats({
              pageKey,
              groupBy: statsGroupBy,
              // 仪表盘跟随所选数据表与筛选条件联动（图表下钻除外）
              tableId: advancedFilterEnabled ? next.tableId : undefined,
              keyword: advancedFilterEnabled ? next.keyword || undefined : undefined,
              conditions: advancedFilterEnabled &&
                (baseConditions.length || advancedConditions.length)
                ? [...baseConditions, ...advancedConditions]
                : undefined,
              dueField,
              closeField: dueField ? closeField : undefined,
            })
          : Promise.resolve({ code: 200 as const, data: null }),
      ])
      if (seq !== requestSeq.current) return
      setLoading(false)
      if (showStats && statsRes.code === 200) {
        setStats(toPageTableStats(statsRes.data))
      }
      if (res.code === 200 && res.data) {
        const nextColumns = res.data.columns ?? []
        setColumns(nextColumns)
        setRows(toRecordRows(res.data.records))
        setTotal(res.data.total)
        setPage(res.data.page)
        setPageSize(res.data.page_size)
        setTruncated(res.data.truncated)
        setLoadError(null)
        // 结构不同的子表（不符合项/观察项）没有统计维度字段，首轮 stats
        // 会 400：按该表实际存在的维度回退重查；一个都没有时清空仪表盘
        const columnNames = new Set(nextColumns.map((column) => column.name))
        const missingDimension = statsGroupBy?.some((name) => !columnNames.has(name))
        if (showStats && statsGroupBy?.length && (statsRes.code !== 200 || missingDimension)) {
          const present = statsGroupBy.filter((name) => columnNames.has(name))
          if (!present.length) {
            setStats(null)
          } else {
            const retry = await getSafetyPageTableStats({
              pageKey,
              groupBy: present,
              tableId: advancedFilterEnabled ? next.tableId : undefined,
              keyword: advancedFilterEnabled ? next.keyword || undefined : undefined,
              conditions:
                advancedFilterEnabled &&
                next.conditions.every((condition) => present.includes(condition.field))
                  ? next.conditions
                  : undefined,
            })
            if (seq === requestSeq.current && retry.code === 200) {
              setStats(toPageTableStats(retry.data))
            }
          }
        }
      } else {
        setLoadError(res.message || '读取多维表格数据失败')
      }
    },
    [
      advancedFilterEnabled,
      closeField,
      dateColumn,
      dateFilter,
      dateRange,
      dimensionFilter,
      dueDrill,
      dueField,
      dueWindow,
      fieldFilters,
      filterDateField,
      keyword,
      page,
      pageSize,
      pageKey,
      selectFilters,
      showStats,
      sortDirection,
      sortField,
      statsGroupBy,
      summarizeColumns,
    ]
  )

  const openDetail = useCallback(
    (row: PageTableRecordRow) => {
      setDetail(row)
      const initial: Record<string, unknown> = {}
      for (const column of editableColumns) {
        const value = row.fields[column.name]
        if (column.kind === 'date') {
          initial[column.name] = value ? dayjs(String(value)) : null
        } else if (column.kind === 'person') {
          initial[column.name] = asPersonList(value).map((person) => person.id)
        } else if (column.kind === 'attachment') {
          continue
        } else {
          initial[column.name] = value ?? undefined
        }
      }
      form.setFieldsValue(initial)
    },
    [editableColumns, form]
  )

  const handleSave = useCallback(async () => {
    if (!detail) return
    const values = (await form.validateFields()) as Record<string, unknown>
    const payload = buildFormPayload(values, editableColumns)
    setSaving(true)
    const res = await updateSafetyPageTableRecord({
      pageKey,
      recordId: detail.record_id,
      fields: payload,
      tableId: activeTableId ?? null,
    })
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('已保存到飞书多维表格')
      const updated = res.data as PageTableRecordRow
      setRows((prev) =>
        prev.map((row) => (row.record_id === updated.record_id ? updated : row))
      )
      setDetail(updated)
      openDetail(updated)
    } else {
      message.error(res.message || '保存失败')
    }
  }, [activeTableId, detail, editableColumns, form, message, openDetail, pageKey])

  /** 新建记录：写入当前选中的子表并回写飞书，成功后刷新列表与仪表盘。 */
  const handleCreate = useCallback(async () => {
    const values = (await form.validateFields()) as Record<string, unknown>
    const payload = buildFormPayload(values, editableColumns)
    // 新建时空值不提交（清空字段是更新语义），避免把一串 null 写进飞书
    const cleaned = Object.fromEntries(
      Object.entries(payload).filter(
        ([, value]) =>
          value !== null &&
          value !== '' &&
          !(Array.isArray(value) && value.length === 0)
      )
    )
    setSaving(true)
    const res = await createSafetyPageTableRecord({
      pageKey,
      fields: cleaned,
      tableId: activeTableId ?? null,
    })
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('已新建记录并写入飞书多维表格')
      setCreateOpen(false)
      form.resetFields()
      await load({ page: 1 })
    } else {
      message.error(res.message || '新建失败')
    }
  }, [activeTableId, editableColumns, form, load, message, pageKey])

  const handleUpload = useCallback(
    async (column: PageTableColumn, file: File) => {
      if (!detail) return
      setUploadingField(column.name)
      const res = await uploadSafetyPageTableAttachment({
        pageKey,
        recordId: detail.record_id,
        fieldName: column.name,
        file,
        tableId: activeTableId ?? null,
      })
      setUploadingField(null)
      if (res.code === 200 && res.data) {
        message.success('附件已上传到飞书多维表格')
        const attachments = res.data.attachments
        setRows((prev) =>
          prev.map((row) =>
            row.record_id === detail.record_id
              ? { ...row, fields: { ...row.fields, [column.name]: attachments } }
              : row
          )
        )
        setDetail((prev) =>
          prev
            ? { ...prev, fields: { ...prev.fields, [column.name]: attachments } }
            : prev
        )
      } else {
        message.error(res.message || '附件上传失败')
      }
    },
    [activeTableId, detail, message, pageKey]
  )

  /** 图表下钻：再次点击同一分类取消筛选。 */
  const handleSelectDimension = useCallback(
    (field: string, value: string) => {
      const next =
        dimensionFilter?.field === field && dimensionFilter?.value === value
          ? null
          : { field, value }
      setDimensionFilter(next)
      setPage(1)
      void load({ page: 1, filter: next })
    },
    [dimensionFilter, load]
  )

  /** 切换子表：重置筛选/分页后按该子表重查；仪表盘跟随所选数据表。 */
  const handleTabChange = useCallback(
    (tableId: string) => {
      setActiveTableId(tableId)
      activeTableIdRef.current = tableId
      setKeyword('')
      setSortField(defaultSortField)
      setDimensionFilter(null)
      setFieldFilters({})
      setDateRange([null, null])
      setDueDrill(false)
      setDetail(null)
      setCreateOpen(false)
      form.resetFields()
      setPage(1)
      void load({
        page: 1,
        tableId,
        filter: null,
        sortField: defaultSortField,
        sortDirection: 'asc',
        fieldFilters: {},
        dateRange: null,
      })
    },
    [defaultSortField, form, load]
  )

  // 筛选下拉的选项：随数据表切换重新拉取（各子表字段值不同）
  useEffect(() => {
    if (!filterFields?.length) return
    let cancelled = false
    void (async () => {
      const entries = await Promise.all(
        filterFields.map(async (name) => {
          const res = await getSafetyPageTableFieldValues({
            pageKey,
            field: name,
            tableId: activeTableIdRef.current,
          })
          return [
            name,
            res.code === 200 && res.data ? (res.data.values ?? []) : [],
          ] as const
        })
      )
      if (!cancelled) setFilterOptions(Object.fromEntries(entries))
    })()
    return () => {
      cancelled = true
    }
  }, [filterFields, pageKey, activeTableId])

  useEffect(() => {
    // 首屏数据由服务端注入；仅在缺失时兜底拉取
    if (!initialData) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const tableColumns: ColumnsType<PageTableRecordRow> = summaryColumns.map((column) => {
    const wrappable = summarizeColumns
      ? isWrappableColumn(column)
      : wrappedColumnNames.has(column.name)
    return {
      title: column.name,
      dataIndex: ['fields', column.name],
      key: column.field_id || column.name,
      ellipsis: column.kind !== 'attachment' && !wrappable,
      width:
        column.kind === 'attachment'
          ? 220
          : wrappable && !summarizeColumns
            ? WRAPPED_COLUMN_WIDTH
            : KIND_BASE_WIDTHS[column.kind as PageTableFieldKind],
      sorter: true,
      sortOrder:
        sortField === column.name
          ? sortDirection === 'desc'
            ? 'descend'
            : 'ascend'
          : null,
      render: (_: unknown, row: PageTableRecordRow) => {
        if (column.kind === 'attachment') {
          // 图片点击是放大预览，不能冒泡到行上误开详情抽屉
          return (
            <div onClick={(event) => event.stopPropagation()}>
              {renderFeishuColumnValue(
                column,
                row.fields[column.name],
                row,
                pageKey,
                message,
                activeTableId
              )}
            </div>
          )
        }
        const rendered = renderFeishuColumnValue(
          column,
          row.fields[column.name],
          row,
          pageKey,
          message,
          activeTableId
        )
        if (rendered !== undefined) return rendered
        if (wrappable) {
          // td 的 max-width 在表格布局里不可靠，用单元格内 div 限宽自动换行；
          // 超长文本按 4 行截断保持行高紧凑，完整内容点击行后在详情中查看
          const text = displayFieldText(row.fields[column.name])
          if (!text) return <Typography.Text type="secondary">—</Typography.Text>
          return (
            <div
              style={{
                maxWidth: WRAPPED_COLUMN_WIDTH,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                display: '-webkit-box',
                WebkitLineClamp: 4,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {text}
            </div>
          )
        }
        return renderPlainCellValue(column, row.fields[column.name])
      },
    }
  })

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {showStats ? (
        <div style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
          <div style={{ display: 'flex', gap: 12, flex: 1, overflowX: 'auto' }}>
            <PageFeishuStatsBar stats={stats} onSelect={handleSelectDimension} />
          </div>
          {dueField && stats?.due_summary ? (
            <PageDueReminderCard
              summary={stats.due_summary}
              window={dueWindow}
              drilling={dueDrill}
              onWindowChange={(days) => {
                setDueWindow(days)
                // 切窗即时生效（drilling 中带上新窗口重查）
                if (dueDrill) void load({ page: 1, dueWindow: days, dueDrill: true })
              }}
              onToggleDrill={() => {
                const next = !dueDrill
                setDueDrill(next)
                setPage(1)
                void load({ page: 1, dueDrill: next })
              }}
            />
          ) : null}
        </div>
      ) : null}
      {dueDrill && dueField ? (
        <Space size={8} wrap>
          <Typography.Text type="secondary">当前筛选：</Typography.Text>
          <Tag
            closable
            color="warning"
            onClose={() => {
              setDueDrill(false)
              setPage(1)
              void load({ page: 1, dueDrill: false })
            }}
          >
            {dueWindow} 天内到期（含逾期）· 未关闭
          </Tag>
        </Space>
      ) : null}
      {dimensionFilter ? (
        <Space size={8} wrap>
          <Typography.Text type="secondary">当前筛选：</Typography.Text>
          <Tag
            closable
            color="processing"
            onClose={() => {
              setDimensionFilter(null)
              setPage(1)
              void load({ page: 1, filter: null })
            }}
          >
            {dimensionFilter.field} = {dimensionFilter.value}
          </Tag>
        </Space>
      ) : null}
      {loadError ? (
        <PlatformNotice
          type="warning"
          title="无法读取多维表格数据"
          description={`${loadError}（若提示未配置，请到 安全管理 → 系统配置 → 飞书设置 的「页面数据表映射」中绑定表格）`}
        />
      ) : null}
      {truncated ? (
        <PlatformNotice
          type="info"
          title="记录较多，仅加载最近 2000 条"
          description="列表按日期优先加载最新记录，更早的历史记录请到飞书多维表格中查看。"
        />
      ) : null}
      {summarizeColumns ? (
        <Space size={12} wrap>
          {dateColumn ? (
            <DatePicker
              allowClear
              value={dateFilter}
              placeholder={
                initialDateFilter
                  ? `${dateColumn.name}（默认当天，清空看全部）`
                  : `${dateColumn.name}（可选）`
              }
              onChange={(value) => {
                setDateFilter(value)
                void load({
                  page: 1,
                  conditions: buildConditions(
                    summarizeColumns,
                    dateColumn,
                    value,
                    selectFilters
                  ),
                })
              }}
            />
          ) : null}
          {conditionSelects.map((column) => (
            <Select
              key={column.name}
              allowClear
              placeholder={column.name}
              style={{ minWidth: 150 }}
              value={selectFilters[column.name] || undefined}
              options={columnOptions(column).map((option) => ({
                value: option,
                label: option,
              }))}
              onChange={(value) => {
                const next = { ...selectFilters, [column.name]: value ?? '' }
                setSelectFilters(next)
                void load({
                  page: 1,
                  conditions: buildConditions(
                    summarizeColumns,
                    dateColumn,
                    dateFilter,
                    next
                  ),
                })
              }}
            />
          ))}
          <Button
            onClick={() => {
              const resetDate = initialDateFilter
                ? dayjs(initialDateFilter.value)
                : null
              setDateFilter(resetDate)
              setSelectFilters({})
              void load({
                page: 1,
                conditions: buildConditions(
                  summarizeColumns,
                  dateColumn,
                  resetDate,
                  {}
                ),
              })
            }}
          >
            重置
          </Button>
        </Space>
      ) : null}
      {advancedFilterEnabled ? (
        <Space size={12} wrap>
          {filterFields?.map((name) => (
            <Select
              key={name}
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={`${name}筛选`}
              style={{ minWidth: 170 }}
              value={fieldFilters[name] || undefined}
              options={(filterOptions[name] ?? []).map((option) => ({
                value: option.value,
                label: `${option.value}（${option.count}）`,
              }))}
              onChange={(value) => {
                const next = { ...fieldFilters, [name]: value ?? '' }
                setFieldFilters(next)
                setPage(1)
                void load({ page: 1, fieldFilters: next })
              }}
            />
          ))}
          {filterDateColumn ? (
            <RangePicker
              allowEmpty={[true, true]}
              placeholder={['开始日期', '结束日期']}
              value={[dateRange[0], dateRange[1]]}
              onChange={(value) => {
                const next: [dayjs.Dayjs | null, dayjs.Dayjs | null] = [
                  value?.[0] ?? null,
                  value?.[1] ?? null,
                ]
                setDateRange(next)
                setPage(1)
                void load({ page: 1, dateRange: next })
              }}
            />
          ) : null}
          <Button
            onClick={() => {
              setFieldFilters({})
              setDateRange([null, null])
              setDueDrill(false)
              setPage(1)
              void load({
                page: 1,
                fieldFilters: {},
                dateRange: null,
                dueDrill: false,
              })
            }}
          >
            重置筛选
          </Button>
        </Space>
      ) : null}
      <Space size={12} wrap>
        {tabs && tabs.length > 0 ? (
          <>
            <Typography.Text type="secondary">数据表</Typography.Text>
            <Select
              style={{ minWidth: 240 }}
              placeholder="选择数据表"
              value={activeTableId ?? primaryTab?.table_id ?? tabs[0].table_id}
              options={tabs.map((tab) => ({
                value: tab.table_id,
                label: `${tab.tab_name}（${tab.record_count}）`,
              }))}
              onChange={(key) => handleTabChange(key)}
            />
          </>
        ) : null}
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="按关键字筛选"
          style={{ width: 260 }}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onPressEnter={() => void load({ page: 1, keyword })}
        />
        <Button onClick={() => void load({ page: 1, keyword })} loading={loading}>
          查询
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
        {createUrl ? (
          <a href={createUrl} target="_blank" rel="noreferrer">
            <Button type="primary" icon={<PlusOutlined />}>新增</Button>
          </a>
        ) : allowCreate ? (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!canOperate}
            onClick={() => {
              form.resetFields()
              setCreateOpen(true)
            }}
          >
            新建记录
          </Button>
        ) : null}
        <Typography.Text type="secondary">
          共 {total} 条；列与数据来自飞书多维表格，修改会直接写回飞书。
          {detailOnlyCount > 0
            ? ` 表格仅显示主要列，其余 ${detailOnlyCount} 个字段点击行后在详情中查看。`
            : ''}
        </Typography.Text>
      </Space>
      <Table<PageTableRecordRow>
        rowKey="record_id"
        size="middle"
        loading={loading}
        columns={tableColumns}
        dataSource={rows}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showTotal: (count) => `共 ${count} 条`,
        }}
        onChange={(pagination, _filters, sorter) => {
          const single = Array.isArray(sorter) ? sorter[0] : sorter
          const nextField =
            single?.order && typeof single.field === 'string' ? single.field : null
          const nextDirection: 'asc' | 'desc' = single?.order === 'descend' ? 'desc' : 'asc'
          setSortField(nextField)
          setSortDirection(nextDirection)
          void load({
            page: pagination.current ?? 1,
            pageSize: pagination.pageSize ?? pageSize,
            sortField: nextField,
            sortDirection: nextDirection,
          })
        }}
        onRow={(row) => ({
          onClick: () => openDetail(row),
          style: { cursor: 'pointer' },
        })}
      />
      <Drawer
        title={createOpen ? `${pageName} · 新建记录` : `${pageName} · 记录详情`}
        size={720}
        open={detail !== null || createOpen}
        onClose={() => {
          setDetail(null)
          setCreateOpen(false)
        }}
        destroyOnHidden
        extra={
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!canOperate}
            onClick={() => void (createOpen ? handleCreate() : handleSave())}
          >
            保存
          </Button>
        }
      >
        {detail || createOpen ? (
          <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
            {!canOperate ? (
              <PlatformNotice
                type="info"
                title="当前账号只有查看权限"
                description="保存与上传附件需要该页面的操作权限。"
              />
            ) : null}
            {createOpen ? (
              <Typography.Text type="secondary">
                新记录将写入当前选中的数据表
                {tabs && tabs.length > 0
                  ? `「${
                      tabs.find((tab) => tab.table_id === activeTableId)?.tab_name ??
                      primaryTab?.tab_name ??
                      ''
                    }」`
                  : ''}
                ，保存后立即写回飞书多维表格。
              </Typography.Text>
            ) : null}
            <Form form={form} layout="vertical" disabled={!canOperate}>
              {editableColumns
                .filter((column) => column.kind !== 'attachment')
                .map((column) => (
                  <Form.Item key={column.name} name={column.name} label={column.name}>
                    {column.kind === 'number' ? (
                      <InputNumber style={{ width: '100%' }} />
                    ) : column.kind === 'select' ? (
                      <Select
                        allowClear
                        options={columnOptions(column).map((option) => ({
                          value: option,
                          label: option,
                        }))}
                      />
                    ) : column.kind === 'multi_select' ? (
                      <Select
                        allowClear
                        mode="multiple"
                        options={columnOptions(column).map((option) => ({
                          value: option,
                          label: option,
                        }))}
                      />
                    ) : column.kind === 'date' ? (
                      <DatePicker style={{ width: '100%' }} />
                    ) : column.kind === 'checkbox' ? (
                      <Switch />
                    ) : column.kind === 'person' ? (
                      <Select
                        allowClear
                        mode="multiple"
                        options={personOptions.map((option) => ({
                          value: option.value,
                          label: (
                            <span
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                            >
                              <Avatar size={20} src={option.avatar || undefined}>
                                {option.label.slice(0, 1) || '?'}
                              </Avatar>
                              {option.label}
                            </span>
                          ),
                        }))}
                        placeholder={
                          personOptions.length
                            ? '从当前表格出现过的值班人员中选择'
                            : '当前表格还没有可选的飞书用户'
                        }
                      />
                    ) : (
                      <Input.TextArea autoSize={{ minRows: 1, maxRows: 6 }} />
                    )}
                  </Form.Item>
                ))}
            </Form>

            {/* 附件区只在编辑已有记录时展示（新建记录先保存后再传附件） */}
            {!createOpen
              ? attachmentColumns.map((column) => {
              const items = asAttachmentList(detail?.fields[column.name])
              return (
                <div key={column.name}>
                  <Typography.Text strong>{column.name}</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    {items.length ? (
                      renderFeishuValue(
                        items,
                        { record_id: detail?.record_id ?? '' },
                        undefined,
                        message,
                        {
                          attachmentUrlBuilder: (_entity, recordId, fileToken) =>
                            attachmentUrl(
                              pageKey,
                              recordId,
                              column.name,
                              fileToken,
                              activeTableId
                            ),
                        }
                      )
                    ) : (
                      <Typography.Text type="secondary">暂无附件</Typography.Text>
                    )}
                  </div>
                  <Upload
                    showUploadList={false}
                    disabled={!canOperate}
                    beforeUpload={(file) => {
                      void handleUpload(column, file as File)
                      return false
                    }}
                  >
                    <Button
                      size="small"
                      icon={<CloudUploadOutlined />}
                      loading={uploadingField === column.name}
                      disabled={!canOperate}
                      style={{ marginTop: 8 }}
                    >
                      上传附件
                    </Button>
                  </Upload>
                </div>
              )
            })
              : null}
          </Space>
        ) : null}
      </Drawer>
    </Space>
  )
}
