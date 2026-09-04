'use client'

import { Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'

import {
  VALIDATION_REVIEW_CATEGORY_LABELS,
  VALIDATION_REVIEW_SEVERITY_LABELS,
} from '@/types/quality'
import type { ValidationReviewFinding } from '@/types/quality'

const SEVERITY_COLORS: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
}

interface ValidationReviewFindingsTableProps {
  findings: ValidationReviewFinding[]
  loading?: boolean
}

export function ValidationReviewFindingsTable({
  findings = [],
  loading,
}: ValidationReviewFindingsTableProps) {
  const columns: ColumnsType<ValidationReviewFinding> = [
    {
      title: '严重度',
      dataIndex: 'severity',
      width: 80,
      render: (value: string) => (
        <Tag color={SEVERITY_COLORS[value] ?? 'default'}>
          {VALIDATION_REVIEW_SEVERITY_LABELS[value] ?? value}
        </Tag>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 130,
      render: (value: string) => (
        <Typography.Text>
          {VALIDATION_REVIEW_CATEGORY_LABELS[value] ?? value}
        </Typography.Text>
      ),
    },
    {
      title: '位置',
      dataIndex: 'location',
      width: 140,
      ellipsis: true,
    },
    {
      title: '原文引用',
      dataIndex: 'quote',
      width: 220,
      ellipsis: true,
      render: (value: string, record) => (
        <Tooltip title={value}>
          <Typography.Text type={record.quote_verified ? undefined : 'danger'}>
            {value}
            {record.quote_verified ? '（已核）' : '（引文未核）'}
          </Typography.Text>
        </Tooltip>
      ),
    },
    {
      title: '说明',
      dataIndex: 'detail',
      ellipsis: true,
      render: (value: string) => <Typography.Text>{value}</Typography.Text>,
    },
  ]

  return (
    <Table<ValidationReviewFinding>
      rowKey={(record) => `${record.category}-${record.quote}-${record.location}`}
      columns={columns}
      dataSource={findings}
      loading={loading}
      size="small"
      scroll={{ x: 900 }}
      pagination={findings.length > 10 ? { pageSize: 10, showSizeChanger: false } : false}
      locale={{ emptyText: '未发现问题' }}
    />
  )
}
