'use client'

import dayjs, { type Dayjs } from 'dayjs'
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import {
  App,
  Avatar,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
} from 'antd'
import type { TableColumnsType, TablePaginationConfig } from 'antd'
import {
  ClockCircleOutlined,
  DatabaseOutlined,
  ExportOutlined,
  EyeOutlined,
  ImportOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  WarehouseAdvancedFilter,
  WarehouseFeishuCellValue,
  WarehouseFeishuColumn,
  WarehouseFeishuMaterialPageData,
  WarehouseFeishuRow,
  WarehouseMaterialPageQueryParams,
  WarehouseRecordDetail,
  WarehouseRecordFieldValue,
} from '@/types/warehouse'
import { usePermission } from '@/hooks/usePermission'
import {
  warehouseScopeOf,
  warehouseScopeWritePermission,
} from './warehouseScope'
import {
  fetchWarehouseMaterialPage,
  fetchWarehouseRecordDetail,
} from '@/lib/api/client/warehouse'
import {
  deleteWarehouseRecordAction,
  updateWarehouseRecordAction,
} from '@/actions/warehouse'

// 飞书字段类型（与后端 feishu_fields.py 保持一致）
const FIELD_TYPE_TEXT = 1
const FIELD_TYPE_NUMBER = 2
const FIELD_TYPE_SINGLE_SELECT = 3
const FIELD_TYPE_MULTI_SELECT = 4
const FIELD_TYPE_DATE = 5
const FIELD_TYPE_CHECKBOX = 7
const FIELD_TYPE_PERSON = 11
const FIELD_TYPE_PHONE = 13
const FIELD_TYPE_URL = 15

// 人员字段类型：人员选择、创建人、修改人（新旧版），渲染头像+姓名
const FIELD_PERSON_TYPES = new Set([11, 22, 23, 1003, 1004])

interface WarehouseFeishuTablePageProps {
  data: WarehouseFeishuMaterialPageData
  pageKey?: string
}

interface ColumnDisplayRule {
  sourceKey: string
  title?: string
  aliases?: string[]
}

interface SelectOption {
  label: string
  value: string
}

const PRODUCT_DETAIL_PAGE_KEYS = [
  'product-detail-l-phenylalanine',
  'product-detail-fumaric-acid',
  'product-detail-l-tryptophan',
  'product-detail-mevastatin',
  'product-detail-kitasamycin-hcl',
  'product-detail-doramectin',
  'product-detail-lovastatin',
  'product-detail-florfenicol-premix',
  'product-detail-demeclocycline-hcl',
  'product-detail-fenbendazole-powder',
] as const

const PRODUCT_DETAIL_COLUMN_RULES: ColumnDisplayRule[] = [
  { sourceKey: '产品名称', aliases: ['品名', '产品'] },
  { sourceKey: '包装规格', aliases: ['规格'] },
  { sourceKey: '入库标签批号', aliases: ['标签批号', '批号'] },
  { sourceKey: '入库量', aliases: ['入库数量'] },
  { sourceKey: '累计出库量', aliases: ['累计出库', '出库总量'] },
  { sourceKey: '库存量', aliases: ['库存', '库存数量'] },
  { sourceKey: '件数', aliases: ['库存件数'] },
  { sourceKey: '质量状态' },
  { sourceKey: '客户', aliases: ['客户名称'] },
]

const PAGE_COLUMN_RULES: Partial<Record<string, ColumnDisplayRule[]>> = {
  'raw-summary': [
    { sourceKey: '使用产品/类别' },
    { sourceKey: '物料名称' },
    { sourceKey: 'ERP编号' },
    { sourceKey: '规格' },
    { sourceKey: '单位' },
    { sourceKey: '厂内代码' },
    { sourceKey: '本日结存' },
    { sourceKey: '前台库存' },
    { sourceKey: '可用库存' },
    { sourceKey: '安全库存（30天）' },
    { sourceKey: '预警' },
  ],
  'packaging-summary': [
    { sourceKey: '使用产品', title: '使用产品/类别' },
    { sourceKey: '名称', title: '物料名称' },
    { sourceKey: 'EPR编号', title: 'ERP编号' },
    { sourceKey: '规格' },
    { sourceKey: '单位' },
    { sourceKey: '厂内代码' },
    { sourceKey: '本日结存' },
    { sourceKey: '前台结存', title: '前台库存' },
    { sourceKey: '可用库存' },
    { sourceKey: '安全库存', title: '安全库存（30天）' },
    { sourceKey: '预警' },
  ],
  'raw-detail': [
    { sourceKey: '使用产品/类别' },
    { sourceKey: '物料名称' },
    { sourceKey: 'ERP编号' },
    { sourceKey: '库区' },
    { sourceKey: '规格' },
    { sourceKey: '生产商' },
    { sourceKey: '单位' },
    { sourceKey: '厂内代码' },
    { sourceKey: '厂内批号' },
    { sourceKey: '厂家批号' },
    { sourceKey: '入库总量' },
    { sourceKey: '出库总量' },
    { sourceKey: '本日结存' },
    { sourceKey: '质量状态' },
    { sourceKey: '有效期' },
  ],
  'raw-ledger': [
    { sourceKey: '出库日期' },
    { sourceKey: '物料名称' },
    { sourceKey: '规格' },
    { sourceKey: '领用数量（Kg）' },
    { sourceKey: '领料人' },
    { sourceKey: '生产批号' },
    { sourceKey: '领用车间' },
    { sourceKey: '使用产品' },
    { sourceKey: '厂内代码' },
    { sourceKey: '厂内批号' },
    { sourceKey: '出库数量' },
    { sourceKey: '发料人' },
  ],
  'packaging-detail': [
    { sourceKey: '使用产品', title: '使用产品/类别' },
    { sourceKey: '名称', title: '物料名称' },
    { sourceKey: 'ERP编号' },
    { sourceKey: '库区' },
    { sourceKey: '规  格', title: '规格' },
    { sourceKey: '生产商/供应商', title: '生产商' },
    { sourceKey: '单位' },
    { sourceKey: '厂内代码' },
    { sourceKey: '厂内批号' },
    { sourceKey: '厂家批号' },
    { sourceKey: '入库总量' },
    { sourceKey: '累计出库', title: '出库总量' },
    { sourceKey: '本日结存' },
    { sourceKey: '质量状态' },
    { sourceKey: '有效期' },
  ],
  'packaging-ledger': [
    { sourceKey: '出库日期' },
    { sourceKey: '物料名称' },
    { sourceKey: '规格' },
    { sourceKey: '领用数量（条/个）' },
    { sourceKey: '领用人', title: '领料人' },
    { sourceKey: '生产批号' },
    { sourceKey: '领用车间' },
    { sourceKey: '使用产品' },
    { sourceKey: '厂内代码' },
    { sourceKey: '厂内批号' },
    { sourceKey: '出库数量' },
    { sourceKey: '发料人' },
  ],
  'inbound-ledger': [
    { sourceKey: '入库日期' },
    { sourceKey: '物料类别' },
    { sourceKey: '物料名称' },
    { sourceKey: '使用产品' },
    { sourceKey: '规格' },
    { sourceKey: '厂内代码' },
    { sourceKey: '厂内批号' },
    { sourceKey: '厂家批号' },
    { sourceKey: '生产商' },
    { sourceKey: '计量单位' },
    { sourceKey: '入库数量' },
  ],
  // 成品入库明细：列表只展示「入库日期 → 入库车间」之间的业务列，
  // 其余字段（QC确认人、入库确认、仓库确认人等）在详情弹窗查看
  'product-inbound-detail': [
    { sourceKey: '入库日期' },
    { sourceKey: '产品名称' },
    { sourceKey: '包装规格' },
    { sourceKey: '对应前台批号' },
    { sourceKey: '入库标签批号' },
    { sourceKey: '入库量' },
    { sourceKey: '客户' },
    { sourceKey: '包装桶UN信息' },
    { sourceKey: '备注（填写实物批号）' },
    { sourceKey: '入库车间' },
  ],
  'product-inbound-ledger': [
    { sourceKey: '入库日期' },
    { sourceKey: '产品名称' },
    { sourceKey: '入库数量（KG）' },
    { sourceKey: '入库数量（十亿）' },
  ],
  'product-outbound-ledger': [
    { sourceKey: '出库日期' },
    { sourceKey: '产品名称' },
    { sourceKey: '包装规格' },
    { sourceKey: '入库标签批号' },
    { sourceKey: '出库量' },
    { sourceKey: '出库人' },
    { sourceKey: '客户' },
    { sourceKey: '领出数量' },
    { sourceKey: '领出人' },
    { sourceKey: '月份' },
    { sourceKey: '车间领出原因' },
    { sourceKey: '备注' },
  ],
}

for (const pageKey of PRODUCT_DETAIL_PAGE_KEYS) {
  PAGE_COLUMN_RULES[pageKey] = PRODUCT_DETAIL_COLUMN_RULES
}

// 某些页面默认隐藏的列（如产品汇总不展示序号）
const HIDDEN_COLUMNS_PER_PAGE: Partial<Record<string, string[]>> = {
  'product-summary': ['序号'],
}

// 全局隐藏字段：飞书多维表格层级功能自带的"父记录"列（无业务含义，纯噪音）
const HIDDEN_FIELD_NAMES = new Set(['父记录'])

// 某些页面默认分组键（候选按顺序取第一个存在的列）
const DEFAULT_GROUP_PER_PAGE: Partial<Record<string, string[]>> = {
  'product-summary': ['产品名称'],
}
for (const pageKey of PRODUCT_DETAIL_PAGE_KEYS) {
  DEFAULT_GROUP_PER_PAGE[pageKey] = ['包装规格', '规格']
}

const DATE_SORT_DESC_PAGES: Record<string, string> = {
  'raw-ledger': '出库日期',
  'packaging-ledger': '出库日期',
  'inbound-ledger': '入库日期',
  'hardware-inbound-ledger': '日期',
  'hardware-outbound-ledger': '日期',
  'product-inbound-ledger': '入库日期',
  'product-inbound-detail': '入库日期',
  'product-outbound-ledger': '出库日期',
  'product-shipping': '日期',
  // 五金库存明细页：按业务/入库日期倒序，保证每天最新记录在前。
  // 注意：hardware-summary / hardware-electrical 的「日期」绝大多数为同一
  // 初始化日期且最新行常因结存 0 被隐藏，无排序意义，故不配置。
  'hardware-101-1-workshop': '日期',
  'hardware-101-2-workshop': '日期',
  'hardware-102-workshop': '日期',
  'hardware-103-workshop': '日期',
  'hardware-201-1-workshop': '日期',
  'hardware-201-2-workshop': '日期',
  'hardware-201-3-workshop': '日期',
  'hardware-202-workshop': '日期',
  'hardware-203-workshop': '日期',
  'hardware-203-3-workshop': '日期',
  'hardware-thermal-station': '日期',
  'hardware-power-department': '日期',
  'hardware-wastewater': '日期',
  'hardware-warehouse': '日期',
  'hardware-rd-center': '日期',
  'hardware-others': '日期',
}

// 部分页面列宽覆盖（单位 px）：入库台账规格列收紧、入库日期列放宽
const PAGE_COLUMN_WIDTH_OVERRIDES: Partial<Record<string, Record<string, number>>> = {
  'inbound-ledger': { 规格: 150, 入库日期: 120 },
  // 成品入库明细：包装桶UN信息内容较长，收紧列宽并自动换行展示；
  // 入库日期列加宽，保证日期完整单行显示（配合 NOWRAP_COLUMNS_PER_PAGE）
  'product-inbound-detail': { 包装桶UN信息: 130, 入库日期: 200 },
}

// 指定页面中需单行完整显示、禁止换行的列（如日期列，配合列宽覆盖使用）
const NOWRAP_COLUMNS_PER_PAGE: Partial<Record<string, string[]>> = {
  'product-inbound-detail': ['入库日期'],
}

// 出入库登记入口：仅语义对应的台账页面显示，新窗口打开飞书表单填写（飞书写入后系统刷新可见）。
// outboundLabel/inboundLabel 可定制按钮文案（如发货情况「新增发货」、入库明细「新增」），
// 缺省分别回落「出库登记」「入库登记」。
const WAREHOUSE_INOUT_LINKS: Record<
  string,
  { inbound?: string; outbound?: string; outboundLabel?: string; inboundLabel?: string }
> = {
  // 入库总账（原辅料/包材共用）→ 原辅料入库表单
  'inbound-ledger': {
    inbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnw9CyyTl8PdAvOyQZqK9oie',
  },
  // 原辅料出库总账 → 原辅料入库 + 出库表单
  'raw-ledger': {
    inbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnw9CyyTl8PdAvOyQZqK9oie',
    outbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnHN5pqjlDlKc3iyUi7Fts7b',
  },
  // 包材出库总账 → 包材出库表单
  'packaging-ledger': {
    outbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcneDAUnAAhPs1yFMfOq0Uhkf',
  },
  // 成品入库明细 → 成品入库表单（按钮「新增」）
  'product-inbound-detail': {
    inbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnDSOkJ2pyfcd3azP25WHJ9f',
    inboundLabel: '新增',
  },
  // 成品入库总账 → 成品入库表单
  'product-inbound-ledger': {
    inbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnDSOkJ2pyfcd3azP25WHJ9f',
  },
  // 成品发货情况 → 新增发货表单（按钮「新增发货」）
  'product-shipping': {
    outbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnUrGx4FJwY9zEDAR8NLkWDL',
    outboundLabel: '新增发货',
  },
  // 成品出库台账 → 成品出库表单（按钮「出库登记」）
  'product-outbound-ledger': {
    outbound: 'https://j0eukrlohu.feishu.cn/share/base/form/shrcnnZl0PPBDqISGj02c9h2JBh',
  },
}

// 基础数据表页面：不展示统计仪表卡片
const NO_STAT_CARD_PAGE_KEYS = new Set(['qualified-suppliers', 'material-name-code-map'])

export function resolveInoutLinks(
  pageKey: string
): {
  inbound?: string
  outbound?: string
  outboundLabel?: string
  inboundLabel?: string
} | null {
  return WAREHOUSE_INOUT_LINKS[pageKey] ?? null
}

const ADVANCED_OPERATOR_OPTIONS: Array<{ label: string; value: WarehouseAdvancedFilter['operator'] }> = [
  { label: '包含', value: 'contains' },
  { label: '不包含', value: 'not_contains' },
  { label: '等于', value: 'eq' },
  { label: '不等于', value: 'neq' },
  { label: '为空', value: 'empty' },
  { label: '不为空', value: 'not_empty' },
  { label: '大于', value: 'gt' },
  { label: '大于等于', value: 'gte' },
  { label: '小于', value: 'lt' },
  { label: '小于等于', value: 'lte' },
  { label: '区间', value: 'between' },
]

const DATE_FILTER_TYPE_OPTIONS = [
  { label: '等于某天', value: 'eq' },
  { label: '大于某天', value: 'gt' },
  { label: '小于某天', value: 'lt' },
  { label: '本周', value: 'this_week' },
  { label: '上周', value: 'last_week' },
  { label: '本月', value: 'this_month' },
  { label: '上月', value: 'last_month' },
] as const

type DateFilterType = (typeof DATE_FILTER_TYPE_OPTIONS)[number]['value']

const DATE_FILTER_TYPE_LABELS: Record<DateFilterType, string> = Object.fromEntries(
  DATE_FILTER_TYPE_OPTIONS.map((option) => [option.value, option.label])
) as Record<DateFilterType, string>

export function isDateLikeColumn(columnKey: string) {
  return /(日期|有效期|复验期)$/.test(columnKey)
}

export function formatDateForChina(date: Date) {
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return formatter.format(date).replace(/\//g, '-')
}

export function formatDateValue(value: WarehouseFeishuCellValue | string | undefined) {
  if (value === null || value === undefined || value === '') {
    return value
  }

  if (typeof value === 'number') {
    const date = new Date(value > 1e12 ? value : value * 1000)
    if (!Number.isNaN(date.getTime())) {
      return formatDateForChina(date)
    }
    return value
  }

  if (typeof value === 'string' && /^\d{10,13}$/.test(value)) {
    const numericValue = Number(value)
    if (!Number.isNaN(numericValue)) {
      const date = new Date(value.length === 13 ? numericValue : numericValue * 1000)
      if (!Number.isNaN(date.getTime())) {
        return formatDateForChina(date)
      }
    }
  }

  return value
}

export function resolveWeekRange(baseDate: Dayjs) {
  const weekday = baseDate.day()
  const offset = weekday === 0 ? 6 : weekday - 1
  const start = baseDate.subtract(offset, 'day')
  const end = start.add(6, 'day')
  return { start, end }
}

export function resolveDateFilterRange(filterType: DateFilterType, selectedDate: Dayjs | null) {
  const today = dayjs()

  if (filterType === 'eq' && selectedDate) {
    const dateText = selectedDate.format('YYYY-MM-DD')
    return { startDate: dateText, endDate: dateText }
  }

  if (filterType === 'gt' && selectedDate) {
    return { startDate: selectedDate.format('YYYY-MM-DD'), endDate: '' }
  }

  if (filterType === 'lt' && selectedDate) {
    return { startDate: '', endDate: selectedDate.format('YYYY-MM-DD') }
  }

  if (filterType === 'this_week') {
    const range = resolveWeekRange(today)
    return {
      startDate: range.start.format('YYYY-MM-DD'),
      endDate: range.end.format('YYYY-MM-DD'),
    }
  }

  if (filterType === 'last_week') {
    const range = resolveWeekRange(today.subtract(7, 'day'))
    return {
      startDate: range.start.format('YYYY-MM-DD'),
      endDate: range.end.format('YYYY-MM-DD'),
    }
  }

  if (filterType === 'this_month') {
    return {
      startDate: today.startOf('month').format('YYYY-MM-DD'),
      endDate: today.endOf('month').format('YYYY-MM-DD'),
    }
  }

  if (filterType === 'last_month') {
    const lastMonth = today.subtract(1, 'month')
    return {
      startDate: lastMonth.startOf('month').format('YYYY-MM-DD'),
      endDate: lastMonth.endOf('month').format('YYYY-MM-DD'),
    }
  }

  return { startDate: '', endDate: '' }
}

export function buildDateFilterLabel(filterType: string, startDate: string, endDate: string) {
  if (!filterType) {
    return ''
  }

  if (filterType === 'eq' && startDate) {
    return `日期等于：${startDate}`
  }

  if (filterType === 'gt' && startDate) {
    return `日期大于等于：${startDate}`
  }

  if (filterType === 'lt' && endDate) {
    return `日期小于等于：${endDate}`
  }

  return `日期：${DATE_FILTER_TYPE_LABELS[filterType as DateFilterType] ?? filterType}`
}

export function buildVisiblePageData(
  pageKey: string,
  data: WarehouseFeishuMaterialPageData
): {
  columns: WarehouseFeishuColumn[]
  rows: WarehouseFeishuRow[]
} {
  const rules = PAGE_COLUMN_RULES[pageKey]
  const fieldTypeMap = new Map<string, number | null>(
    data.columns.map((column) => [column.key, column.field_type ?? null])
  )

  let sortedRows = data.rows
  const dateSortField = DATE_SORT_DESC_PAGES[pageKey]
  if (dateSortField) {
    sortedRows = [...data.rows].sort((a, b) => {
      const aVal = Number(a[dateSortField] ?? 0)
      const bVal = Number(b[dateSortField] ?? 0)
      return bVal - aVal
    })
  }

  if (!rules?.length) {
    const hidden = [...(HIDDEN_COLUMNS_PER_PAGE[pageKey] ?? []), ...HIDDEN_FIELD_NAMES]
    const visibleColumns = data.columns.filter((column) => !hidden.includes(column.key))
    return {
      columns: visibleColumns,
      rows: sortedRows.map((row) => {
        const nextRow: WarehouseFeishuRow = { ...row }

        data.columns.forEach((column) => {
          if (isDateLikeColumn(column.key)) {
            nextRow[column.key] = formatDateValue(row[column.key])
          }
        })

        return nextRow
      }),
    }
  }

  const availableKeys = new Set<string>()
  data.columns.forEach((column) => availableKeys.add(column.key))
  data.rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (key !== '__record_id') {
        availableKeys.add(key)
      }
    })
  })

  const resolvedRules = rules
    .map((rule) => {
      const resolvedSourceKey = [rule.sourceKey, ...(rule.aliases ?? [])].find((candidate) =>
        availableKeys.has(candidate)
      )

      if (!resolvedSourceKey) {
        return null
      }

      return {
        resolvedSourceKey,
        title: rule.title ?? rule.sourceKey,
      }
    })
    .filter(
      (
        rule
      ): rule is {
        resolvedSourceKey: string
        title: string
      } => Boolean(rule)
    )

  if (!resolvedRules.length) {
    return {
      columns: [],
      rows: sortedRows.map((row) => ({ __record_id: row.__record_id })),
    }
  }

  const columns: WarehouseFeishuColumn[] = resolvedRules.map((rule) => ({
    key: rule.title,
    title: rule.title,
    field_type: fieldTypeMap.get(rule.resolvedSourceKey) ?? null,
  }))

  const rows = sortedRows.map((row) => {
    const nextRow: WarehouseFeishuRow = {}

    for (const rule of resolvedRules) {
      const targetKey = rule.title
      const sourceValue = row[rule.resolvedSourceKey]
      nextRow[targetKey] = isDateLikeColumn(targetKey) ? formatDateValue(sourceValue) : sourceValue
    }

    nextRow.__record_id = row.__record_id
    return nextRow
  })

  return { columns, rows }
}

export function parseAdvancedFilters(value: string | null): WarehouseAdvancedFilter[] {
  if (!value) {
    return []
  }
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function getUniqueOptions(
  rows: WarehouseFeishuRow[],
  candidateKeys: string[]
): SelectOption[] {
  const values = new Set<string>()
  rows.forEach((row) => {
    candidateKeys.forEach((key) => {
      const rawValue = row[key]
      if (rawValue === null || rawValue === undefined || rawValue === '') {
        return
      }
      values.add(String(rawValue).trim())
    })
  })
  return Array.from(values)
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, 'zh-CN'))
    .map((value) => ({ label: value, value }))
}

export function buildAdvancedFilterLabel(filter: WarehouseAdvancedFilter) {
  const operatorLabel =
    ADVANCED_OPERATOR_OPTIONS.find((option) => option.value === filter.operator)?.label ??
    filter.operator
  if (filter.operator === 'empty' || filter.operator === 'not_empty') {
    return `${filter.field}${operatorLabel}`
  }
  if (filter.operator === 'between') {
    return `${filter.field}${operatorLabel}${filter.value || '-'} ~ ${filter.value_to || '-'}`
  }
  return `${filter.field}${operatorLabel}${filter.value || '-'}`
}

function renderCell(
  value: WarehouseFeishuCellValue | string | undefined,
  columnKey: string,
  fieldType?: number | null
) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-[var(--color-muted)]">-</span>
  }

  // 人员字段：人员类型、值本身是人员结构（数组含 name 的对象）、或字段名以"人"结尾
  // （如 领料人/发料人/入库人/出库人 等，部分表为文本/单选字段仅存姓名），渲染头像+姓名
  const isPersonValue =
    Array.isArray(value) &&
    value.every((item) => typeof item === 'object' && item !== null && 'name' in item)
  const isPersonNamedField = typeof columnKey === 'string' && columnKey.endsWith('人')
  if (
    (fieldType !== null && fieldType !== undefined && FIELD_PERSON_TYPES.has(fieldType)) ||
    isPersonValue ||
    isPersonNamedField
  ) {
    return renderPersonList(value)
  }

  if (columnKey === '质量状态') {
    const colorMap: Record<string, string> = { 合格: 'green', 待验: 'orange', 不合格: 'red' }
    const text = String(value)
    return <Tag color={colorMap[text] ?? 'default'}>{text}</Tag>
  }

  if (columnKey === '预警') {
    const text = String(value)
    if (text.includes('严重不足')) {
      return <Tag color="red">{text}</Tag>
    }
    if (text.includes('不足')) {
      return <Tag color="orange">{text}</Tag>
    }
    return <Tag color="gold">{text}</Tag>
  }

  if (typeof value === 'boolean') {
    return value ? <Tag color="green">是</Tag> : <Tag color="default">否</Tag>
  }

  return String(value)
}

export function formatDetailDisplayValue(field: WarehouseRecordFieldValue): string {
  const value = field.value
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') {
          return item
        }
        if (item && typeof item === 'object') {
          const obj = item as Record<string, unknown>
          return String(obj.name ?? obj.text ?? obj.id ?? obj.file_token ?? JSON.stringify(obj))
        }
        return String(item)
      })
      .join('、')
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }
  return String(value)
}

export function formatSyncTime(time: string | undefined): string {
  if (!time) {
    return '-'
  }
  const date = new Date(time)
  if (Number.isNaN(date.getTime())) {
    return '-'
  }
  // 后端同步时间为 UTC 时间戳，固定按北京时间（Asia/Shanghai）展示，
  // 保证 SSR 与客户端渲染一致，避免时区导致的 hydration 不匹配
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
  return formatter.format(date).replace(/\//g, '-')
}

// 人员字段渲染：头像 + 姓名（类似飞书联系人展示）。
// 兼容飞书人员结构（数组/单对象，含 id/name/avatar_url）与纯字符串姓名
// （如部分表的"发料人"为文本/单选字段，仅存姓名文本，无头像数据时用姓名首字占位）。
function renderPersonList(value: unknown) {
  // 飞书人员值可能是单个 dict、多个 dict 的 list，或纯字符串姓名，统一归一为数组
  const normalized = Array.isArray(value)
    ? value
    : typeof value === 'string' && value.trim()
      ? [value]
      : value !== null && typeof value === 'object'
        ? [value]
        : []
  if (!normalized.length) {
    return <span className="text-[var(--color-muted)]">-</span>
  }
  return (
    <Space size={6} wrap>
      {normalized.map((person, index) => {
        const item =
          typeof person === 'object' && person !== null
            ? (person as Record<string, unknown>)
            : { name: String(person) }
        const name = String(item.name ?? '?')
        return (
          <span key={index} className="inline-flex items-center gap-1">
            <Avatar size={20} src={item.avatar_url ? String(item.avatar_url) : undefined}>
              {name.slice(0, 1)}
            </Avatar>
            <span>{name}</span>
          </span>
        )
      })}
    </Space>
  )
}

function renderDetailField(
  field: WarehouseRecordFieldValue,
  editValues: Record<string, unknown>,
  onChange: (fieldName: string, value: unknown) => void,
  editMode: boolean
) {
  const fieldName = field.field_name
  const value = editValues[fieldName]

  // 只读/仅查看字段：纯展示，不提供编辑入口
  if (field.readonly || field.view_only) {
    // 人员字段：头像 + 姓名展示（含字段名以"人"结尾的文本/单选人员字段）
    const isPersonField =
      (field.field_type !== null && field.field_type !== undefined && FIELD_PERSON_TYPES.has(field.field_type)) ||
      fieldName.endsWith('人')
    if (isPersonField) {
      return renderPersonList(field.value)
    }
    return <span className="break-all text-[13px]">{formatDetailDisplayValue(field)}</span>
  }

  // 查看模式：可编辑字段同样只读展示，点击「编辑」后才进入编辑状态
  if (!editMode) {
    // 人员字段（含字段名以"人"结尾的文本/单选人员字段）：头像 + 姓名展示
    const isPersonField = fieldName.endsWith('人')
    if (isPersonField) {
      return renderPersonList(field.value)
    }
    return <span className="break-all text-[13px]">{formatDetailDisplayValue(field)}</span>
  }

  switch (field.field_type) {
    case FIELD_TYPE_NUMBER:
      return (
        <InputNumber
          style={{ width: '100%' }}
          value={value !== undefined && value !== '' && value !== null ? Number(value) : undefined}
          onChange={(next) => onChange(fieldName, next)}
        />
      )
    case FIELD_TYPE_SINGLE_SELECT:
      return (
        <Select
          style={{ width: '100%' }}
          value={value !== undefined && value !== '' ? String(value) : undefined}
          options={(field.options ?? []).map((option) => ({ label: option.name, value: option.name }))}
          onChange={(next) => onChange(fieldName, next)}
        />
      )
    case FIELD_TYPE_MULTI_SELECT:
      return (
        <Select
          mode="multiple"
          style={{ width: '100%' }}
          value={Array.isArray(value) ? value.map(String) : undefined}
          options={(field.options ?? []).map((option) => ({ label: option.name, value: option.name }))}
          onChange={(next) => onChange(fieldName, next)}
        />
      )
    case FIELD_TYPE_DATE:
      return (
        <DatePicker
          style={{ width: '100%' }}
          value={value ? dayjs(String(value)) : null}
          onChange={(next) => onChange(fieldName, next ? next.format('YYYY-MM-DD') : '')}
        />
      )
    case FIELD_TYPE_CHECKBOX:
      return (
        <Switch
          checked={Boolean(value)}
          onChange={(next) => onChange(fieldName, next)}
          checkedChildren="是"
          unCheckedChildren="否"
        />
      )
    case FIELD_TYPE_TEXT:
      return (
        <Input.TextArea
          rows={2}
          value={value !== undefined && value !== null ? String(value) : ''}
          onChange={(event) => onChange(fieldName, event.target.value)}
        />
      )
    default:
      return (
        <Input
          value={value !== undefined && value !== null ? String(value) : ''}
          onChange={(event) => onChange(fieldName, event.target.value)}
        />
      )
  }
}

// ── 多级分组排列 ─────────────────────────────────────────────
interface WarehouseGroupRow {
  __group_row: true
  __group_level: number
  __group_value: string
  __group_count: number
  // 从根分组到当前分组的完整值路径，用于生成全局唯一 key；
  // 不同父组下的同名子组因此不会产生重复 key
  __group_path: string[]
}

type WarehouseTableRow = WarehouseFeishuRow | WarehouseGroupRow

function isGroupRow(record: WarehouseTableRow): record is WarehouseGroupRow {
  return (record as WarehouseGroupRow).__group_row === true
}

export function buildGroupedRows(
  rows: WarehouseFeishuRow[],
  groupKeys: string[]
): WarehouseTableRow[] {
  if (!groupKeys.length) {
    return rows
  }
  const result: WarehouseTableRow[] = []
  const groupRecursive = (items: WarehouseFeishuRow[], level: number, parentPath: string[]) => {
    if (level >= groupKeys.length) {
      result.push(...items)
      return
    }
    const key = groupKeys[level]
    const buckets = new Map<string, WarehouseFeishuRow[]>()
    items.forEach((row) => {
      const raw = row[key]
      const value = raw === null || raw === undefined || raw === '' ? '（空）' : String(raw)
      if (!buckets.has(value)) {
        buckets.set(value, [])
      }
      buckets.get(value)!.push(row)
    })
    // 组内按值排序：日期字段组倒序（最新在前），其余字段组升序（中文环境），空值组排最后
    const isDateGroup = isDateLikeColumn(key)
    const sortedKeys = Array.from(buckets.keys()).sort((a, b) => {
      if (a === '（空）') return 1
      if (b === '（空）') return -1
      return isDateGroup ? b.localeCompare(a, 'zh-CN') : a.localeCompare(b, 'zh-CN')
    })
    sortedKeys.forEach((value) => {
      const groupItems = buckets.get(value)!
      const path = [...parentPath, value]
      result.push({
        __group_row: true,
        __group_level: level,
        __group_value: value,
        __group_count: groupItems.length,
        __group_path: path,
      })
      groupRecursive(groupItems, level + 1, path)
    })
  }
  groupRecursive(rows, 0, [])
  return result
}

export function WarehouseFeishuTablePage({
  data,
  pageKey,
}: WarehouseFeishuTablePageProps) {
  const { message } = App.useApp()
  const { hasAny } = usePermission()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [isPending, startTransition] = useTransition()
  const currentKeyword = searchParams.get('keyword') ?? ''
  const resolvedPageKey = pageKey ?? data.page_key
  // 编辑权限：本页面所属子领域（成品/五金/原辅料及包材）细分码或模块级 write；
  // 由后台部门角色映射决定，无权限时隐藏写按钮（后端端点校验为最终边界）
  const canEditThisPage = hasAny([
    warehouseScopeWritePermission(warehouseScopeOf(resolvedPageKey)),
    'warehouse:write',
  ])
  const isCompactPage = Boolean(PAGE_COLUMN_RULES[resolvedPageKey]?.length)
  const currentDateField = searchParams.get('date_field') ?? ''
  const currentDateFilterType = (searchParams.get('date_filter_type') as DateFilterType | null) ?? ''
  const currentStartDate = searchParams.get('start_date') ?? ''
  const currentEndDate = searchParams.get('end_date') ?? ''
  const currentProduct = searchParams.get('product') ?? ''
  const currentArea = searchParams.get('area') ?? ''
  const currentQualityStatus = searchParams.get('quality_status') ?? ''
  const currentWarningStatus = searchParams.get('warning_status') ?? ''
  const currentMaterialCategory = searchParams.get('material_category') ?? ''
  const currentAdvancedFilters = useMemo(
    () => parseAdvancedFilters(searchParams.get('filters')),
    [searchParams]
  )
  const [keywordInput, setKeywordInput] = useState(currentKeyword)
  const [dateFieldValue, setDateFieldValue] = useState(currentDateField)
  const [dateFilterType, setDateFilterType] = useState<DateFilterType | ''>(currentDateFilterType)
  const [dateValue, setDateValue] = useState<Dayjs | null>(
    currentStartDate ? dayjs(currentStartDate) : currentEndDate ? dayjs(currentEndDate) : null
  )
  const [productValue, setProductValue] = useState(currentProduct)
  const [areaValue, setAreaValue] = useState(currentArea)
  const [qualityStatusValue, setQualityStatusValue] = useState(currentQualityStatus)
  const [warningStatusValue, setWarningStatusValue] = useState(currentWarningStatus)
  const [materialCategoryValue, setMaterialCategoryValue] = useState(currentMaterialCategory)
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(currentAdvancedFilters.length > 0)
  const [advancedFilters, setAdvancedFilters] = useState<WarehouseAdvancedFilter[]>(
    currentAdvancedFilters
  )
  const [localData, setLocalData] = useState<WarehouseFeishuMaterialPageData>(data)
  const [refreshing, setRefreshing] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(false)
  // 详情弹窗状态
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<WarehouseRecordDetail | null>(null)
  const [editValues, setEditValues] = useState<Record<string, unknown>>({})
  const [editMode, setEditMode] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // 分组排列状态（按选择顺序多级分组，localStorage 持久化）
  // 初始为空数组保证 SSR 与客户端首帧一致（避免 hydration 失败），
  // 分组配置在 useEffect 中从 localStorage 恢复
  const [groupKeys, setGroupKeys] = useState<string[]>([])
  // 统计卡片明细弹窗状态
  const [statDetailOpen, setStatDetailOpen] = useState(false)
  const [statDetailTitle, setStatDetailTitle] = useState('')
  const [statDetailLoading, setStatDetailLoading] = useState(false)
  const [statDetailData, setStatDetailData] = useState<WarehouseFeishuMaterialPageData | null>(null)
  const columnWidth = isCompactPage ? undefined : 180

  useEffect(() => {
    setLocalData(data)
  }, [data])

  // SSR 降级（空数据）时自动补拉：Server Component 8s 超时后返回空数据渲染，
  // 组件挂载后立即请求真实数据（后端缓存命中则秒回，冷启动则等待全量拉取）
  const autoFetchedRef = useRef(false)
  useEffect(() => {
    if (autoFetchedRef.current) {
      return
    }
    const isEmpty = (localData.rows?.length ?? 0) === 0 && (localData.total ?? 0) === 0
    if (isEmpty && localData.source === 'feishu_bitable') {
      autoFetchedRef.current = true
      void refreshData(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localData.source, localData.rows, localData.total])

  // 从 localStorage 恢复分组配置（仅客户端执行，保证 hydration 一致）
  // 无保存配置时回落到该页默认分组（如产品汇总按产品名称、产品明细按规格）
  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      const saved = window.localStorage.getItem(`wh-group-${resolvedPageKey}`)
      if (saved) {
        const parsed = JSON.parse(saved)
        // 仅有非空的保存配置才覆盖默认分组；空数组视为未设置，回落默认
        if (Array.isArray(parsed) && parsed.length > 0) {
          setGroupKeys(parsed)
          return
        }
      }
    } catch {
      // localStorage 不可用时忽略，分组仅本次会话生效
    }
    const candidates = DEFAULT_GROUP_PER_PAGE[resolvedPageKey] ?? []
    const columnKeys = new Set(localData.columns.map((column) => column.key))
    const firstMatch = candidates.find((key) => columnKeys.has(key))
    setGroupKeys(firstMatch ? [firstMatch] : [])
  }, [resolvedPageKey, localData.columns])

  const visibleData = useMemo(
    () => buildVisiblePageData(resolvedPageKey, localData),
    [resolvedPageKey, localData]
  )

  useEffect(() => {
    setKeywordInput(currentKeyword)
    setDateFieldValue(currentDateField)
    setDateFilterType(currentDateFilterType)
    setDateValue(currentStartDate ? dayjs(currentStartDate) : currentEndDate ? dayjs(currentEndDate) : null)
    setProductValue(currentProduct)
    setAreaValue(currentArea)
    setQualityStatusValue(currentQualityStatus)
    setWarningStatusValue(currentWarningStatus)
    setMaterialCategoryValue(currentMaterialCategory)
    setAdvancedFilters(currentAdvancedFilters)
    setShowAdvancedFilters(currentAdvancedFilters.length > 0)
  }, [
    currentAdvancedFilters,
    currentArea,
    currentDateField,
    currentDateFilterType,
    currentEndDate,
    currentKeyword,
    currentMaterialCategory,
    currentProduct,
    currentQualityStatus,
    currentStartDate,
    currentWarningStatus,
  ])

  const dateFieldOptions = useMemo(
    () =>
      visibleData.columns
        .filter((column) => isDateLikeColumn(column.key))
        .map((column) => ({ label: column.title, value: column.key })),
    [visibleData.columns]
  )
  const defaultDateField = dateFieldOptions[0]?.value ?? ''
  const selectedDateField = dateFieldValue || defaultDateField
  const requiresSingleDate = dateFilterType === 'eq' || dateFilterType === 'gt' || dateFilterType === 'lt'
  const productOptions = useMemo(
    () => getUniqueOptions(visibleData.rows, ['使用产品/类别', '使用产品']),
    [visibleData.rows]
  )
  const areaOptions = useMemo(
    () => getUniqueOptions(visibleData.rows, ['库区', '出库库区', '领用车间']),
    [visibleData.rows]
  )
  const qualityOptions = useMemo(
    () => getUniqueOptions(visibleData.rows, ['质量状态']),
    [visibleData.rows]
  )
  const warningOptions = useMemo(
    () => getUniqueOptions(visibleData.rows, ['预警']),
    [visibleData.rows]
  )
  const materialCategoryOptions = useMemo(
    () => getUniqueOptions(visibleData.rows, ['物料类别']),
    [visibleData.rows]
  )
  const hasDateFilter = dateFieldOptions.length > 0
  const hasProductFilter = visibleData.columns.some((column) =>
    ['使用产品/类别', '使用产品'].includes(column.key)
  )
  const hasAreaFilter = visibleData.columns.some((column) =>
    ['库区', '出库库区', '领用车间'].includes(column.key)
  )
  const hasQualityFilter = visibleData.columns.some((column) => column.key === '质量状态')
  const hasWarningFilter = visibleData.columns.some((column) => column.key === '预警')
  const hasMaterialCategoryFilter = visibleData.columns.some(
    (column) => column.key === '物料类别'
  )
  const advancedFieldOptions = useMemo(
    () => visibleData.columns.map((column) => ({ label: column.title, value: column.key })),
    [visibleData.columns]
  )
  const activeFilterTags = useMemo(() => {
    const tags: string[] = []
    if (currentKeyword) tags.push(`关键字：${currentKeyword}`)
    const dateFilterLabel = buildDateFilterLabel(currentDateFilterType, currentStartDate, currentEndDate)
    if (dateFilterLabel) tags.push(dateFilterLabel)
    if (currentProduct) tags.push(`产品/类别：${currentProduct}`)
    if (currentArea) tags.push(`库区/车间：${currentArea}`)
    if (currentQualityStatus) tags.push(`质量状态：${currentQualityStatus}`)
    if (currentWarningStatus) tags.push(`预警：${currentWarningStatus}`)
    if (currentMaterialCategory) tags.push(`物料类别：${currentMaterialCategory}`)
    currentAdvancedFilters.forEach((filter) => {
      tags.push(buildAdvancedFilterLabel(filter))
    })
    return tags
  }, [
    currentAdvancedFilters,
    currentArea,
    currentDateFilterType,
    currentEndDate,
    currentKeyword,
    currentMaterialCategory,
    currentProduct,
    currentQualityStatus,
    currentStartDate,
    currentWarningStatus,
  ])

  // ── 详情弹窗：打开记录详情（columns 操作列引用，需先声明）──────
  const openDetail = useCallback(
    async (recordId: string) => {
      setDetailOpen(true)
      setDetailLoading(true)
      setDetailData(null)
      setEditValues({})
      setEditMode(false)
      try {
        const detail = await fetchWarehouseRecordDetail(resolvedPageKey, recordId)
        setDetailData(detail)
      } catch (error) {
        const detail = error instanceof Error ? error.message : '未知错误'
        message.error(`详情加载失败：${detail}`)
        setDetailOpen(false)
      } finally {
        setDetailLoading(false)
      }
    },
    [resolvedPageKey]
  )

  const columns: TableColumnsType<WarehouseTableRow> = useMemo(
    () => [
      ...visibleData.columns.map((column, columnIndex) => ({
        title: column.title,
        dataIndex: column.key,
        key: column.key,
        width: PAGE_COLUMN_WIDTH_OVERRIDES[resolvedPageKey]?.[column.key] ?? columnWidth,
        align: 'center' as const,
        onHeaderCell: () =>
          ({
            style: {
              backgroundColor: '#e8f0fe',
              color: '#1a2a52',
              fontWeight: 600,
              whiteSpace: 'normal',
              wordBreak: 'break-word',
              paddingInline: 8,
              fontSize: isCompactPage ? 12 : 13,
              lineHeight: 1.2,
            },
          } as React.HTMLAttributes<HTMLElement>),
        onCell: (record: WarehouseTableRow) => {
          const nowrap = NOWRAP_COLUMNS_PER_PAGE[resolvedPageKey]?.includes(column.key)
          const baseStyle = {
            style: {
              whiteSpace: nowrap ? ('nowrap' as const) : ('normal' as const),
              wordBreak: nowrap ? ('normal' as const) : ('break-word' as const),
              paddingInline: 8,
              fontSize: isCompactPage ? 12 : 13,
              lineHeight: 1.2,
            },
          } as const
          if (isGroupRow(record)) {
            // 分组行：第一列跨全部列，其余列隐藏
            return {
              colSpan: columnIndex === 0 ? visibleData.columns.length + 1 : 0,
              ...baseStyle,
            } as React.TdHTMLAttributes<HTMLElement>
          }
          return baseStyle as React.HTMLAttributes<HTMLElement>
        },
        render: (value: WarehouseFeishuCellValue | string | undefined, record: WarehouseTableRow) => {
          if (isGroupRow(record) && columnIndex === 0) {
            return (
              <span
                style={{
                  paddingLeft: (record.__group_level ?? 0) * 20,
                  fontWeight: 600,
                  color: '#1a2a52',
                  display: 'inline-block',
                }}
              >
                {record.__group_value}（{record.__group_count} 条）
              </span>
            )
          }
          return renderCell(value, column.key, column.field_type)
        },
      })),
      {
        title: '操作',
        key: '__actions',
        width: 80,
        align: 'center' as const,
        fixed: 'right' as const,
        onCell: (record: WarehouseTableRow) =>
          isGroupRow(record)
            ? ({ colSpan: 0 } as React.TdHTMLAttributes<HTMLElement>)
            : ({} as React.HTMLAttributes<HTMLElement>),
        render: (_, record: WarehouseTableRow) =>
          !isGroupRow(record) && record.__record_id ? (
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => openDetail(record.__record_id as string)}
            >
              详情
            </Button>
          ) : null,
      },
    ],
    [columnWidth, isCompactPage, resolvedPageKey, visibleData.columns, openDetail]
  )

  const basePath = pathname || `/warehouse/materials/${resolvedPageKey}`

  const pushWithParams = (nextParams: URLSearchParams) => {
    const queryString = nextParams.toString()
    const nextUrl = queryString ? `${basePath}?${queryString}` : basePath

    startTransition(() => {
      router.push(nextUrl)
    })
  }

  const buildNextParams = () => {
    const nextParams = new URLSearchParams()
    const trimmedKeyword = keywordInput.trim()
    if (trimmedKeyword) {
      nextParams.set('keyword', trimmedKeyword)
    }
    if (hasDateFilter && selectedDateField && dateFilterType) {
      const { startDate, endDate } = resolveDateFilterRange(dateFilterType, dateValue)
      if (startDate || endDate) {
        nextParams.set('date_field', selectedDateField)
        nextParams.set('date_filter_type', dateFilterType)
        if (startDate) nextParams.set('start_date', startDate)
        if (endDate) nextParams.set('end_date', endDate)
      }
    }
    if (productValue) nextParams.set('product', productValue)
    if (areaValue) nextParams.set('area', areaValue)
    if (qualityStatusValue) nextParams.set('quality_status', qualityStatusValue)
    if (warningStatusValue) nextParams.set('warning_status', warningStatusValue)
    if (materialCategoryValue) nextParams.set('material_category', materialCategoryValue)

    const validAdvancedFilters = advancedFilters.filter((filter) => {
      if (!filter.field || !filter.operator) {
        return false
      }
      if (filter.operator === 'empty' || filter.operator === 'not_empty') {
        return true
      }
      if (filter.operator === 'between') {
        return Boolean(filter.value?.trim() && filter.value_to?.trim())
      }
      return Boolean(filter.value?.trim())
    })
    if (validAdvancedFilters.length > 0) {
      nextParams.set('filters', JSON.stringify(validAdvancedFilters))
    }
    return nextParams
  }

  const handleSearchSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    pushWithParams(buildNextParams())
  }

  const buildQueryParams = (): WarehouseMaterialPageQueryParams => {
    const params: WarehouseMaterialPageQueryParams = {
      page: Number(searchParams.get('page') || 1),
      page_size: Number(searchParams.get('page_size') || localData.page_size || 50),
      keyword: currentKeyword || undefined,
      start_date: currentStartDate || undefined,
      end_date: currentEndDate || undefined,
      date_field: currentDateField || undefined,
      product: currentProduct || undefined,
      area: currentArea || undefined,
      quality_status: currentQualityStatus || undefined,
      warning_status: currentWarningStatus || undefined,
      material_category: currentMaterialCategory || undefined,
      filters: currentAdvancedFilters.length ? currentAdvancedFilters : undefined,
    }
    return params
  }

  // React Query 缓存层：queryKey 含全部筛选参数（JSON.stringify 序列化稳定）；
  // initialData 用 SSR 首帧 props.data，配合 Provider 的 staleTime 30s 避免首屏重复请求。
  // 查询结果经 useEffect 同步回 localData（组件数据源保持 localData 不变，渲染/分组/详情逻辑零改动）。
  const queryClient = useQueryClient()
  const queryKey = [
    'warehouse-material-page',
    resolvedPageKey,
    JSON.stringify(buildQueryParams()),
  ] as const
  const { data: queryData } = useQuery({
    queryKey,
    queryFn: () => fetchWarehouseMaterialPage(resolvedPageKey, buildQueryParams()),
    initialData: data,
  })

  // 查询结果同步到 localData（与上方 useEffect(() => setLocalData(data)) 的 SSR prop 同步并存：
  // queryData 首帧即 initialData=props.data，不会把 SSR 数据覆盖成空）
  useEffect(() => {
    if (queryData) {
      setLocalData(queryData)
    }
  }, [queryData])

  // 刷新从「直接 fetch」改为 mutation（签名不变，所有调用点零改动）：
  // force=true 直连飞书拉最新，force=false 走后端缓存；成功后同步 localData 并回写 query 缓存。
  const refreshMutation = useMutation({
    mutationFn: (force: boolean) =>
      fetchWarehouseMaterialPage(
        resolvedPageKey,
        {
          ...buildQueryParams(),
          force,
        },
        60000 // 60 秒超时：后端已支持按日期增量拉取（秒级），首次全量/异常时留足余量
      ),
    onSuccess: (latest) => {
      setLocalData(latest)
      queryClient.setQueryData(queryKey, latest)
    },
    onError: (error) => {
      const detail = error instanceof Error ? error.message : '未知错误'
      message.error(`刷新失败：${detail}`)
    },
    onSettled: () => {
      setRefreshing(false)
    },
  })

  // mutate 是 useMutation 内部引用稳定的 useCallback，以其作依赖可保证 refreshData 稳定，
  // 自动轮询定时器不会在每次渲染时被重置（属性访问写法会触发 exhaustive-deps 误报，故禁用该规则）
  const refreshData = useCallback(
    (force: boolean) => {
      setRefreshing(true)
      refreshMutation.mutate(force)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refreshMutation.mutate]
  )

  const handleRefresh = () => {
    void refreshData(true)
  }

  // 自动轮询：默认关闭，开启后每 60s 拉取一次最新数据（命中后端缓存，开销小）
  useEffect(() => {
    if (!autoRefresh) {
      return
    }
    const timer = setInterval(() => {
      void refreshData(false)
    }, 60000)
    return () => clearInterval(timer)
  }, [autoRefresh, refreshData])

  // ── 详情弹窗 ──────────────────────────────────────────────
  const closeDetail = () => {
    setDetailOpen(false)
    setDetailData(null)
    setEditValues({})
    setEditMode(false)
  }

  const handleStartEdit = () => {
    if (!detailData) {
      return
    }
    const initial: Record<string, unknown> = {}
    detailData.fields.forEach((field) => {
      if (!field.editable) {
        return
      }
      let value = field.value
      if (field.field_type === FIELD_TYPE_MULTI_SELECT && typeof value === 'string') {
        value = value.split(',').map((item) => item.trim()).filter(Boolean)
      }
      initial[field.field_name] = value ?? ''
    })
    setEditValues(initial)
    setEditMode(true)
  }

  const handleCancelEdit = () => {
    setEditValues({})
    setEditMode(false)
  }

  const handleEditValueChange = (fieldName: string, value: unknown) => {
    setEditValues((current) => ({ ...current, [fieldName]: value }))
  }

  const handleSave = async () => {
    if (!detailData) {
      return
    }
    setSaving(true)
    try {
      await updateWarehouseRecordAction(resolvedPageKey, detailData.record_id, editValues)
      message.success('保存成功，已同步更新到飞书多维表格')
      setDetailOpen(false)
      setDetailData(null)
      setEditMode(false)
      void refreshData(false)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      message.error(`保存失败：${detail}，请重试`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!detailData) {
      return
    }
    setDeleting(true)
    try {
      await deleteWarehouseRecordAction(resolvedPageKey, detailData.record_id)
      message.success('删除成功，已从飞书多维表格移除')
      setDetailOpen(false)
      setDetailData(null)
      void refreshData(false)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      message.error(`删除失败：${detail}，请重试`)
    } finally {
      setDeleting(false)
    }
  }

  // ── 统计概览卡片（仓储业务指标，点击弹出明细弹窗）────────
  const openStatDetail = async (
    title: string,
    buildParams: () => WarehouseMaterialPageQueryParams
  ) => {
    setStatDetailTitle(title)
    setStatDetailOpen(true)
    setStatDetailLoading(true)
    setStatDetailData(null)
    try {
      const latest = await fetchWarehouseMaterialPage(resolvedPageKey, {
        page: 1,
        page_size: 200,
        ...buildParams(),
      })
      setStatDetailData(latest)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      message.error(`明细加载失败：${detail}`)
      setStatDetailOpen(false)
    } finally {
      setStatDetailLoading(false)
    }
  }

  // 明细弹窗内展示列/行：复用页面列配置映射
  const statDetailVisible = useMemo(
    () =>
      statDetailData
        ? buildVisiblePageData(resolvedPageKey, statDetailData)
        : { columns: [], rows: [] },
    [resolvedPageKey, statDetailData]
  )

  const statDetailColumns: TableColumnsType<WarehouseFeishuRow> = useMemo(
    () =>
      statDetailVisible.columns.map((column) => ({
        title: column.title,
        dataIndex: column.key,
        key: column.key,
        width: PAGE_COLUMN_WIDTH_OVERRIDES[resolvedPageKey]?.[column.key] ?? columnWidth,
        align: 'center' as const,
        onCell: () => ({
          style: { whiteSpace: 'normal' as const, wordBreak: 'break-word' as const },
        }),
        render: (value: WarehouseFeishuCellValue | string | undefined) =>
          renderCell(value, column.key, column.field_type),
      })),
    [statDetailVisible.columns, columnWidth, resolvedPageKey]
  )

  const statCards = useMemo(() => {
    const stats = localData.stats
    const firstDateField = localData.columns.find((column) => isDateLikeColumn(column.key))?.key

    const buildFilterQuery = (key: string, value: string): WarehouseMaterialPageQueryParams => ({
      [key]: value,
    })
    const buildDateQuery = (startDate: string, endDate: string): WarehouseMaterialPageQueryParams => ({
      ...(firstDateField ? { date_field: firstDateField } : {}),
      start_date: startDate,
      end_date: endDate,
    })

    const cards: Array<{
      key: string
      title: string
      value: number
      color?: string
      prefix?: string
      buildParams?: () => WarehouseMaterialPageQueryParams
    }> = []

    // 库存预警类（原辅料/包材汇总表）
    if (stats?.severe_low_stock_count !== undefined) {
      cards.push({
        key: 'severe-low',
        title: '库存严重不足',
        value: stats.severe_low_stock_count,
        color: '#ff4d4f',
        buildParams: () => buildFilterQuery('warning_status', '库存严重不足'),
      })
    }
    if (stats?.low_stock_count !== undefined) {
      cards.push({
        key: 'low',
        title: '库存不足',
        value: stats.low_stock_count,
        color: '#fa8c16',
        buildParams: () => buildFilterQuery('warning_status', '库存不足'),
      })
    }
    // 质量状态分布（库存明细/成品明细）
    if (stats?.failed_count !== undefined) {
      cards.push({
        key: 'failed',
        title: '不合格',
        value: stats.failed_count,
        color: '#ff4d4f',
        buildParams: () => buildFilterQuery('quality_status', '不合格'),
      })
    }
    if (stats?.pending_count !== undefined) {
      cards.push({
        key: 'pending',
        title: '待验',
        value: stats.pending_count,
        color: '#faad14',
        buildParams: () => buildFilterQuery('quality_status', '待验'),
      })
    }
    if (stats?.qualified_count !== undefined) {
      cards.push({
        key: 'qualified',
        title: '合格',
        value: stats.qualified_count,
        color: '#52c41a',
        buildParams: () => buildFilterQuery('quality_status', '合格'),
      })
    }
    // 出入库/台账类（本月/今日）
    if (stats?.month_count !== undefined && cards.length < 4) {
      cards.push({
        key: 'month',
        title: '本月记录',
        value: stats.month_count,
        color: '#722ed1',
        buildParams: () =>
          buildDateQuery(
            dayjs().startOf('month').format('YYYY-MM-DD'),
            dayjs().endOf('month').format('YYYY-MM-DD')
          ),
      })
    }
    if (stats?.today_count !== undefined && cards.length < 4) {
      cards.push({
        key: 'today',
        title: '今日记录',
        value: stats.today_count,
        color: '#13c2c2',
        buildParams: () => {
          const today = dayjs().format('YYYY-MM-DD')
          return buildDateQuery(today, today)
        },
      })
    }
    // 五金/库存金额类
    if (stats?.amount_total !== undefined && cards.length < 4) {
      cards.push({
        key: 'amount',
        title: '金额合计',
        value: stats.amount_total,
        color: '#1677ff',
        prefix: '¥',
      })
    }
    if (stats?.stock_count !== undefined && cards.length < 4) {
      cards.push({
        key: 'stock',
        title: '有库存物料',
        value: stats.stock_count,
        color: '#5645d4',
      })
    }
    return cards.slice(0, 4)
  }, [localData.stats, localData.columns])

  // ── 多级分组排列 ──────────────────────────────────────────
  // 分组配置持久化：修改后一直生效，直到下次修改（localStorage 按页面保存）
  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.localStorage.setItem(`wh-group-${resolvedPageKey}`, JSON.stringify(groupKeys))
    } catch {
      // localStorage 不可用时静默忽略，分组仅本次会话生效
    }
  }, [groupKeys, resolvedPageKey])

  const groupOptions = useMemo(
    () =>
      localData.columns
        .filter((column) => column.key !== '__record_id' && column.key !== '__actions')
        .map((column) => ({ label: column.title, value: column.key })),
    [localData.columns]
  )

  // 出入库登记链接（按页面前缀映射飞书视图）
  const inoutLinks = useMemo(() => resolveInoutLinks(resolvedPageKey), [resolvedPageKey])

  // 本地快照新鲜度：15 分钟内同步过视为新鲜（增量同步每 10 分钟一轮）
  const [snapshotNow, setSnapshotNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setSnapshotNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const isSnapshotFresh = useMemo(() => {
    if (localData.source !== 'local_snapshot' || !localData.last_sync_time) {
      return false
    }
    const syncTime = new Date(localData.last_sync_time)
    const minutesAgo = (snapshotNow - syncTime.getTime()) / (1000 * 60)
    return minutesAgo < 15
  }, [localData.source, localData.last_sync_time, snapshotNow])

  const groupedRows = useMemo(
    () => buildGroupedRows(visibleData.rows, groupKeys),
    [visibleData.rows, groupKeys]
  )

  const handleReset = () => {
    setKeywordInput('')
    setDateFieldValue(defaultDateField)
    setDateFilterType('')
    setDateValue(null)
    setProductValue('')
    setAreaValue('')
    setQualityStatusValue('')
    setWarningStatusValue('')
    setMaterialCategoryValue('')
    setAdvancedFilters([])
    setShowAdvancedFilters(false)
    startTransition(() => {
      router.push(basePath)
    })
  }

  const handleAddAdvancedFilter = () => {
    const defaultField = advancedFieldOptions[0]?.value ?? ''
    setAdvancedFilters((current) => [
      ...current,
      { field: defaultField, operator: 'contains', value: '' },
    ])
  }

  const handleUpdateAdvancedFilter = (
    index: number,
    patch: Partial<WarehouseAdvancedFilter>
  ) => {
    setAdvancedFilters((current) =>
      current.map((filter, currentIndex) =>
        currentIndex === index ? { ...filter, ...patch } : filter
      )
    )
  }

  const handleRemoveAdvancedFilter = (index: number) => {
    setAdvancedFilters((current) => current.filter((_, currentIndex) => currentIndex !== index))
  }

  const handleTableChange = (pagination: TablePaginationConfig) => {
    const nextParams = buildNextParams()
    nextParams.set('page', String(pagination.current ?? 1))
    nextParams.set('page_size', String(pagination.pageSize ?? localData.page_size ?? 50))
    pushWithParams(nextParams)
  }

  return (
    <div className="w-full">
      <style>{`
        .wh-table .ant-table-tbody > tr:nth-child(even) > td {
          background-color: #f7f8fc;
        }
        .wh-table .ant-table-tbody > tr:hover > td {
          background-color: rgba(86, 69, 212, 0.06) !important;
        }
        .wh-table .ant-table-thead > tr > th {
          padding-block: 10px;
        }
        .wh-table .ant-table-tbody > tr.wh-group-row > td {
          background-color: #eef4ff !important;
          padding-block: 6px;
          border-bottom: 1px solid #d6e4ff;
        }
        .wh-stat-card .ant-statistic-title {
          font-size: 13px;
          color: var(--color-steel);
        }
        .wh-stat-card .ant-statistic-content {
          font-weight: 700;
        }
        .wh-stat-card-clickable {
          cursor: pointer;
          transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        .wh-stat-card-clickable:hover {
          box-shadow: 0 2px 12px rgba(86, 69, 212, 0.18);
          transform: translateY(-2px);
        }
      `}</style>

      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          {localData.page_title}
        </h1>
        <Space wrap size={8}>
          {localData.source === 'local_snapshot' ? (
            isSnapshotFresh ? (
              <Tag color="blue" icon={<DatabaseOutlined />}>
                本地缓存（定时同步中，数据最新）
              </Tag>
            ) : (
              <Tag color="orange">本地快照（飞书暂不可达，数据可能滞后）</Tag>
            )
          ) : (
            <Tag color="blue" icon={<DatabaseOutlined />}>
              {localData.base_name ? `${localData.base_name}多维表格` : '飞书多维表格'}
            </Tag>
          )}
          <Tag icon={<ClockCircleOutlined />}>同步于 {formatSyncTime(localData.last_sync_time)}</Tag>
          <Tag color="processing">共 {localData.total} 条</Tag>
          {canEditThisPage && inoutLinks?.inbound ? (
            <Button
              type="primary"
              size="small"
              icon={<ImportOutlined />}
              href={inoutLinks.inbound}
              target="_blank"
            >
              {inoutLinks.inboundLabel ?? '入库登记'}
            </Button>
          ) : null}
          {canEditThisPage && inoutLinks?.outbound ? (
            <Button
              size="small"
              icon={<ExportOutlined />}
              href={inoutLinks.outbound}
              target="_blank"
            >
              {inoutLinks.outboundLabel ?? '出库登记'}
            </Button>
          ) : null}
        </Space>
      </div>

      {!NO_STAT_CARD_PAGE_KEYS.has(resolvedPageKey) ? (
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {statCards.map((card) => (
            <Card
              key={card.key}
              className={`wh-stat-card${card.buildParams ? ' wh-stat-card-clickable' : ''}`}
              variant="borderless"
              onClick={() => {
                if (card.buildParams) {
                  void openStatDetail(card.title, card.buildParams)
                }
              }}
            >
              <Statistic
                title={card.title}
                value={card.value}
                prefix={card.prefix}
                styles={{ content: { color: card.color } }}
              />
              {card.buildParams ? (
                <div className="mt-1 text-[12px] text-[var(--color-steel)]">点击查看明细</div>
              ) : null}
            </Card>
          ))}
        </div>
      ) : null}

      <Card
        className="w-full"
        variant="borderless"
        title={localData.table_name}
        extra={
          <Space wrap size={8}>
            <span className="text-[12px] text-[var(--color-steel)]">自动刷新</span>
            <Switch
              size="small"
              checked={autoRefresh}
              onChange={setAutoRefresh}
              checkedChildren="开"
              unCheckedChildren="关"
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => void refreshData(true)}
              loading={refreshing}
            >
              刷新
            </Button>
          </Space>
        }
      >
        <form onSubmit={handleSearchSubmit}>
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            {/* 左侧：筛选控件 */}
            <Space wrap size={12} className="min-w-0">
              {/* 分组排列（靠左显示） */}
              <Select
                mode="multiple"
                allowClear
                maxTagCount={3}
                placeholder="分组排列（按选择顺序）"
                style={{ width: 280 }}
                value={groupKeys}
                options={groupOptions}
                onChange={(value) => setGroupKeys(value as string[])}
              />
              <span className="text-[12px] text-[var(--color-steel)]">
                分组仅对当前页生效
              </span>
              <Input
                allowClear
                value={keywordInput}
                onChange={(event) => setKeywordInput(event.target.value)}
                placeholder="关键字搜索"
                style={{ width: 220 }}
              />
              {hasDateFilter && dateFieldOptions.length > 1 ? (
                <Select
                  allowClear
                  placeholder="日期字段"
                  style={{ width: 140 }}
                  value={dateFieldValue || undefined}
                  options={dateFieldOptions}
                  onChange={(value) => setDateFieldValue(value)}
                />
              ) : null}
              {hasDateFilter ? (
                <Select
                  allowClear
                  placeholder="日期条件"
                  style={{ width: 150 }}
                  value={dateFilterType || undefined}
                  options={DATE_FILTER_TYPE_OPTIONS as unknown as Array<{ label: string; value: string }>}
                  onChange={(value) => {
                    setDateFilterType((value as DateFilterType | undefined) ?? '')
                    if (!value) {
                      setDateValue(null)
                    }
                  }}
                />
              ) : null}
              {hasDateFilter && requiresSingleDate ? (
                <DatePicker
                  value={dateValue}
                  onChange={(value) => setDateValue(value)}
                  placeholder="选择日期"
                />
              ) : null}
              {hasProductFilter ? (
                <Select
                  allowClear
                  placeholder="产品/类别"
                  style={{ width: 160 }}
                  value={productValue || undefined}
                  options={productOptions}
                  onChange={(value) => setProductValue(value)}
                />
              ) : null}
              {hasAreaFilter ? (
                <Select
                  allowClear
                  placeholder="库区/车间"
                  style={{ width: 160 }}
                  value={areaValue || undefined}
                  options={areaOptions}
                  onChange={(value) => setAreaValue(value)}
                />
              ) : null}
              {hasQualityFilter ? (
                <Select
                  allowClear
                  placeholder="质量状态"
                  style={{ width: 140 }}
                  value={qualityStatusValue || undefined}
                  options={qualityOptions}
                  onChange={(value) => setQualityStatusValue(value)}
                />
              ) : null}
              {hasWarningFilter ? (
                <Select
                  allowClear
                  placeholder="预警状态"
                  style={{ width: 140 }}
                  value={warningStatusValue || undefined}
                  options={warningOptions}
                  onChange={(value) => setWarningStatusValue(value)}
                />
              ) : null}
              {hasMaterialCategoryFilter ? (
                <Select
                  allowClear
                  placeholder="物料类别"
                  style={{ width: 140 }}
                  value={materialCategoryValue || undefined}
                  options={materialCategoryOptions}
                  onChange={(value) => setMaterialCategoryValue(value)}
                />
              ) : null}
            </Space>
            {/* 右侧：操作按钮 */}
            <Space wrap size={8}>
              <Button type="primary" htmlType="submit" loading={isPending}>
                查询
              </Button>
              <Button onClick={handleReset} loading={isPending}>
                重置
              </Button>
              <Button
                onClick={() => setShowAdvancedFilters((current) => !current)}
                loading={isPending}
              >
                高级筛选
              </Button>
              <Button onClick={handleRefresh} loading={isPending}>
                刷新
              </Button>
            </Space>
          </div>

          {showAdvancedFilters ? (
            <div className="mb-4 rounded border border-[var(--color-border)] p-3">
              <Space orientation="vertical" size={12} className="w-full">
                {advancedFilters.map((filter, index) => (
                  <Space key={`${filter.field}-${index}`} wrap size={8}>
                    <Select
                      style={{ width: 180 }}
                      value={filter.field}
                      options={advancedFieldOptions}
                      onChange={(value) => handleUpdateAdvancedFilter(index, { field: value })}
                    />
                    <Select
                      style={{ width: 140 }}
                      value={filter.operator}
                      options={ADVANCED_OPERATOR_OPTIONS}
                      onChange={(value) =>
                        handleUpdateAdvancedFilter(index, {
                          operator: value as WarehouseAdvancedFilter['operator'],
                        })
                      }
                    />
                    {filter.operator !== 'empty' && filter.operator !== 'not_empty' ? (
                      <Input
                        placeholder="筛选值"
                        style={{ width: 180 }}
                        value={filter.value}
                        onChange={(event) =>
                          handleUpdateAdvancedFilter(index, { value: event.target.value })
                        }
                      />
                    ) : null}
                    {filter.operator === 'between' ? (
                      <Input
                        placeholder="结束值"
                        style={{ width: 180 }}
                        value={filter.value_to}
                        onChange={(event) =>
                          handleUpdateAdvancedFilter(index, { value_to: event.target.value })
                        }
                      />
                    ) : null}
                    <Button danger onClick={() => handleRemoveAdvancedFilter(index)}>
                      删除条件
                    </Button>
                  </Space>
                ))}
                <Space wrap size={8}>
                  <Button onClick={handleAddAdvancedFilter}>新增条件</Button>
                  <span className="text-[12px] text-[var(--color-muted)]">
                    多条件当前按“且”同时生效
                  </span>
                </Space>
              </Space>
            </div>
          ) : null}

          {activeFilterTags.length ? (
            <Space className="mb-4" wrap size={8}>
              {activeFilterTags.map((tag) => (
                <Tag key={tag} color="blue">
                  {tag}
                </Tag>
              ))}
            </Space>
          ) : null}
        </form>

        <div className="w-full overflow-x-auto">
          <Spin spinning={refreshing} description="数据加载中...">
          <Table<WarehouseTableRow>
            className="wh-table"
            style={{ width: '100%' }}
            columns={columns}
            dataSource={groupedRows}
            rowKey={(record) =>
              isGroupRow(record)
                ? `group-${JSON.stringify(record.__group_path)}`
                : (record as WarehouseFeishuRow).__record_id || JSON.stringify(record)
            }
            rowClassName={(record, index) =>
              isGroupRow(record)
                ? 'wh-group-row'
                : index % 2 === 1
                  ? 'wh-row-striped'
                  : ''
            }
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={activeFilterTags.length ? '未找到符合当前筛选条件的数据' : '暂无数据'}
                />
              ),
            }}
            pagination={{
              current: localData.page,
              // 分组行计入 dataSource 后长度可能超过 page_size，
              // 动态取 max 避免 antd 的 dataSource/pagination 不一致警告
              pageSize: Math.max(localData.page_size, groupedRows.length),
              total: localData.total,
              showSizeChanger: true,
              pageSizeOptions: [100, 500, 1000],
              showTotal: (total) => `共 ${total} 条`,
            }}
            onChange={handleTableChange}
            scroll={isCompactPage ? undefined : { x: 'max-content' }}
            size="small"
            tableLayout={isCompactPage ? 'auto' : undefined}
          />
          </Spin>
        </div>
      </Card>

      <Modal
        open={detailOpen}
        onCancel={closeDetail}
        width={820}
        title={`记录详情${detailData ? `（${detailData.record_id}）` : ''}`}
        footer={
          <Space>
            <Popconfirm
              title="确定删除该记录？"
              description="删除后将同步从飞书多维表格移除，不可恢复。"
              okText="删除"
              okButtonProps={{ danger: true, loading: deleting }}
              cancelText="取消"
              onConfirm={() => void handleDelete()}
            >
              {canEditThisPage ? (
                <Button danger loading={deleting}>
                  删除记录
                </Button>
              ) : null}
            </Popconfirm>
            {editMode ? (
              canEditThisPage ? (
                <>
                  <Button onClick={handleCancelEdit}>取消</Button>
                  <Button type="primary" loading={saving} onClick={() => void handleSave()}>
                    保存修改（同步到飞书）
                  </Button>
                </>
              ) : null
            ) : (
              canEditThisPage ? (
                <Button type="primary" onClick={handleStartEdit}>
                  编辑
                </Button>
              ) : null
            )}
          </Space>
        }
      >
        <Spin spinning={detailLoading}>
          {detailData ? (
            <Descriptions bordered size="small" column={2} className="wh-detail-desc">
              {detailData.fields
                .filter((field) => !HIDDEN_FIELD_NAMES.has(field.field_name))
                .map((field) => (
                <Descriptions.Item
                  key={field.field_name}
                  label={
                    <Space size={4}>
                      <span>{field.field_name}</span>
                      {field.readonly ? <Tag color="default">只读</Tag> : null}
                      {field.view_only ? <Tag color="purple">仅查看</Tag> : null}
                    </Space>
                  }
                >
                  {renderDetailField(field, editValues, handleEditValueChange, editMode)}
                </Descriptions.Item>
              ))}
            </Descriptions>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="加载中或记录不存在" />
          )}
        </Spin>
      </Modal>

      {/* 统计卡片明细弹窗：点击卡片弹出，罗列该指标的记录，不影响下方表格 */}
      <Modal
        open={statDetailOpen}
        onCancel={() => {
          setStatDetailOpen(false)
          setStatDetailData(null)
        }}
        width={1100}
        title={`${statDetailTitle}明细（共 ${statDetailData?.total ?? 0} 条）`}
        footer={null}
      >
        <Spin spinning={statDetailLoading}>
          <div className="w-full overflow-x-auto">
            <Table<WarehouseFeishuRow>
              className="wh-table"
              style={{ width: '100%' }}
              columns={statDetailColumns}
              dataSource={statDetailVisible.rows}
              rowKey={(record) => record.__record_id || JSON.stringify(record)}
              rowClassName={(_, index) => (index % 2 === 1 ? 'wh-row-striped' : '')}
              locale={{
                emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无明细数据" />,
              }}
              pagination={{
                pageSize: 20,
                showSizeChanger: true,
                pageSizeOptions: [20, 50, 100],
                showTotal: (total) => `共 ${total} 条`,
              }}
              scroll={{ x: 'max-content', y: 480 }}
              size="small"
            />
          </div>
        </Spin>
      </Modal>
    </div>
  )
}
