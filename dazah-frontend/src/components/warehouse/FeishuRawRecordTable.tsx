'use client'

import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Alert, Button, Card, Modal, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type {
  WarehouseFeishuField,
  WarehouseFeishuRawRecord,
  WarehouseFeishuRawRecordData,
} from '@/types/warehouse'

const { Text } = Typography

interface FeishuRawRecordTableProps {
  title: string
  data: WarehouseFeishuRawRecordData | null
  error?: string | null
  currentPage?: number
  pageSize?: number
  onPageChange?: (page: number, pageSize: number) => void
  extra?: ReactNode
}

type JsonObject = Record<string, unknown>
type FeishuTableRecord = WarehouseFeishuRawRecord & { __row_key: string }

const FEISHU_DATE_FIELD_TYPES = new Set([5, 1001, 1002])
const FEISHU_DATE_FIELD_NAME_PATTERN =
  /(日期|时间|有效期|生产日|到货|创建|修改|date|time)/i
const DATE_TIME_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeEpoch(value: unknown): number | null {
  const raw =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && /^\d{10,13}$/.test(value.trim())
        ? Number(value.trim())
        : null
  if (raw === null || !Number.isFinite(raw)) return null

  const timestamp = raw > 100000000000 ? raw : raw * 1000
  const min = Date.UTC(2000, 0, 1)
  const max = Date.UTC(2100, 0, 1)
  if (timestamp < min || timestamp > max) return null
  return timestamp
}

function formatFeishuDate(value: unknown): string | null {
  const timestamp = normalizeEpoch(value)
  if (timestamp !== null) {
    const date = new Date(timestamp)
    if (Number.isNaN(date.getTime())) return null
    const parts = DATE_TIME_FORMATTER.formatToParts(date)
    const year = parts.find((part) => part.type === 'year')?.value
    const month = parts.find((part) => part.type === 'month')?.value
    const day = parts.find((part) => part.type === 'day')?.value
    return year && month && day ? `${year}/${month}/${day}` : null
  }

  if (Array.isArray(value) && value.length === 1) {
    return formatFeishuDate(value[0])
  }

  if (isObject(value)) {
    for (const key of ['date', 'timestamp', 'time', 'value']) {
      const parsed = formatFeishuDate(value[key])
      if (parsed) return parsed
    }
  }

  return null
}

function primitiveToText(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string') return value
  return null
}

function pickText(value: JsonObject, keys: string[]): string | null {
  for (const key of keys) {
    const raw = value[key]
    if (typeof raw === 'string' && raw.trim()) return raw
    if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw)
  }
  return null
}

function isDateField(field?: WarehouseFeishuField): boolean {
  if (!field) return false
  if (
    typeof field.type === 'number' &&
    FEISHU_DATE_FIELD_TYPES.has(field.type)
  ) {
    return true
  }
  return FEISHU_DATE_FIELD_NAME_PATTERN.test(field.field_name || '')
}

function parseFeishuValue(
  value: unknown,
  field?: WarehouseFeishuField,
  depth = 0,
): string | null {
  if (depth === 0 && isDateField(field)) {
    const formatted = formatFeishuDate(value)
    if (formatted) return formatted
  }

  const primitive = primitiveToText(value)
  if (primitive !== null) return primitive
  if (depth > 4) return null

  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    const items = value
      .map((item) => parseFeishuValue(item, field, depth + 1))
      .filter((item): item is string => Boolean(item && item !== '-'))
    return items.length > 0 ? items.join('、') : null
  }

  if (!isObject(value)) return null

  const directText = pickText(value, [
    'text',
    'name',
    'title',
    'display_name',
    'en_name',
    'email',
    'phone',
    'file_name',
    'filename',
    'url',
    'link',
  ])
  if (directText) return directText

  const nestedKeys = [
    'value',
    'values',
    'data',
    'text_arr',
    'segments',
    'record_ids',
    'recordIds',
    'users',
    'files',
    'attachments',
  ]
  for (const key of nestedKeys) {
    if (key in value) {
      const parsed = parseFeishuValue(value[key], field, depth + 1)
      if (parsed && parsed !== '-') return parsed
    }
  }

  const numberKeys = ['number', 'amount', 'timestamp', 'time', 'date']
  for (const key of numberKeys) {
    const raw = value[key]
    if (typeof raw === 'number') {
      return key === 'timestamp' || key === 'time' || key === 'date'
        ? formatFeishuDate(raw) || String(raw)
        : String(raw)
    }
  }

  const meaningfulEntries = Object.entries(value)
    .filter(([, raw]) => raw !== null && raw !== undefined && raw !== '')
    .map(([key, raw]) => {
      const parsed = parseFeishuValue(raw, field, depth + 1)
      return parsed && parsed !== '-' ? `${key}: ${parsed}` : null
    })
    .filter((item): item is string => Boolean(item))

  if (meaningfulEntries.length === 1) return meaningfulEntries[0].split(': ').at(-1) || null
  if (meaningfulEntries.length > 1) return meaningfulEntries.slice(0, 3).join('；')

  return null
}

function summarizeValue(value: unknown, field?: WarehouseFeishuField): string {
  const parsed = parseFeishuValue(value, field)
  if (parsed) return parsed
  if (Array.isArray(value)) return `${value.length} 项`
  if (isObject(value)) return '查看详情'
  return '-'
}

function deriveFields(data: WarehouseFeishuRawRecordData | null): WarehouseFeishuField[] {
  if (!data) return []
  if (data.fields.length > 0) return data.fields

  const names = new Set<string>()
  data.records.forEach((record) => {
    Object.keys(record.fields || {}).forEach((name) => names.add(name))
  })
  return Array.from(names).map((name, index) => ({
    field_id: name,
    field_name: name,
    type: null,
    property: null,
    display_order: index,
  }))
}

export function FeishuRawRecordTable({
  title,
  data,
  error,
  currentPage,
  pageSize,
  onPageChange,
  extra,
}: FeishuRawRecordTableProps) {
  const [detail, setDetail] = useState<{ title: string; value: unknown } | null>(null)

  const fields = useMemo(() => deriveFields(data), [data])
  const records = useMemo<FeishuTableRecord[]>(
    () =>
      (data?.records || []).map((record, index) => ({
        ...record,
        __row_key:
          record.record_id ||
          `${data?.table?.business_domain || 'warehouse'}-${data?.table?.table_id || 'table'}-${index}`,
      })),
    [data?.records, data?.table?.business_domain, data?.table?.table_id],
  )

  const columns: ColumnsType<FeishuTableRecord> = useMemo(
    () =>
      fields.map((field) => ({
        title: field.field_name,
        dataIndex: ['fields', field.field_name],
        key: field.field_id || field.field_name,
        width: 180,
        ellipsis: true,
        render: (value: unknown) => {
          if (Array.isArray(value) || (value && typeof value === 'object')) {
            return (
              <Button
                size="small"
                type="link"
                onClick={() => setDetail({ title: field.field_name, value })}
              >
                {summarizeValue(value, field)}
              </Button>
            )
          }
          return <span>{summarizeValue(value, field)}</span>
        },
      })),
    [fields],
  )

  if (error) {
    return <Alert type="warning" showIcon message={error} />
  }

  return (
    <>
      <Card variant="borderless">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
              {title}
            </h2>
            <Text type="secondary">
              {data?.table?.name || '未绑定数据表'}
              {data?.total !== null && data?.total !== undefined
                ? ` · 共 ${data.total} 条`
                : ''}
              {data?.table?.last_synced_at
                ? ` · 同步于 ${new Date(data.table.last_synced_at).toLocaleString('zh-CN')}`
                : ''}
            </Text>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {data?.table?.sync_status && (
              <Tag color={data.table.sync_status === 'failed' ? 'error' : 'default'}>
                {data.table.sync_status}
              </Tag>
            )}
            {data?.table?.table_id && <Tag>{data.table.table_id}</Tag>}
          </div>
        </div>
        {data?.table?.sync_error && (
          <Alert
            type="warning"
            showIcon
            className="mb-4"
            message={data.table.sync_error}
          />
        )}
        {extra && <div className="mb-4">{extra}</div>}
        <Table
          columns={columns}
          dataSource={records}
          rowKey="__row_key"
          size="small"
          scroll={{ x: Math.max(columns.length * 180, 900) }}
          pagination={{
            current: currentPage,
            pageSize: pageSize || data?.page_size || 50,
            total: data?.total ?? records.length,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: onPageChange,
          }}
        />
      </Card>

      <Modal
        open={Boolean(detail)}
        title={detail?.title}
        footer={null}
        onCancel={() => setDetail(null)}
        width={720}
      >
        <pre className="max-h-[520px] overflow-auto rounded-[8px] bg-[var(--color-surface)] p-4 text-[12px] leading-5">
          {JSON.stringify(detail?.value, null, 2)}
        </pre>
      </Modal>
    </>
  )
}
