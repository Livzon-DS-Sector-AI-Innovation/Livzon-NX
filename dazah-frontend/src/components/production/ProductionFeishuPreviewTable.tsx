'use client'

import { Empty, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import type {
  ProductionFeishuRecordPreview,
  ProductionFeishuTablePreview,
} from '@/types/production'

const { Text } = Typography

interface ProductionFeishuPreviewTableProps {
  preview?: ProductionFeishuTablePreview | null
  loading?: boolean
  size?: 'small' | 'middle'
}

function formatFeishuValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => formatFeishuValue(item))
      .filter((item) => item !== '-')
      .join('、')
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    if ('value' in record) {
      return formatFeishuValue(record.value)
    }

    for (const key of ['text', 'name', 'en_us', 'zh_cn', 'link', 'url']) {
      if (record[key] !== undefined && record[key] !== null && record[key] !== '') {
        return formatFeishuValue(record[key])
      }
    }

    const entries = Object.entries(record).filter(([key]) => key !== 'type')
    if (entries.length === 1) {
      return formatFeishuValue(entries[0][1])
    }

    return JSON.stringify(Object.fromEntries(entries))
  }
  return String(value)
}

export function ProductionFeishuPreviewTable({
  preview,
  loading,
  size = 'small',
}: ProductionFeishuPreviewTableProps) {
  const visibleFields = (preview?.fields || []).slice(0, 8)
  const columns: ColumnsType<ProductionFeishuRecordPreview> = [
    {
      title: 'record_id',
      dataIndex: 'record_id',
      key: 'record_id',
      width: 180,
      fixed: 'left',
      render: (value: string) => <Text copyable>{value}</Text>,
    },
    ...visibleFields.map((field) => ({
      title: field.field_name,
      key: field.field_id,
      ellipsis: true,
      width: 160,
      render: (_: unknown, record: ProductionFeishuRecordPreview) => {
        const value = formatFeishuValue(record.fields[field.field_name])
        return <span title={value}>{value}</span>
      },
    })),
  ]

  if (!loading && !preview) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无飞书数据" />
  }

  return (
    <div>
      {preview && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Tag>{preview.table_id}</Tag>
          <Text type="secondary">
            字段 {preview.fields.length} 个，记录 {preview.total ?? preview.records.length} 条
          </Text>
        </div>
      )}
      <Table
        columns={columns}
        dataSource={preview?.records || []}
        rowKey="record_id"
        loading={loading}
        size={size}
        scroll={{ x: Math.max(900, 180 + visibleFields.length * 160) }}
        pagination={false}
      />
    </div>
  )
}
