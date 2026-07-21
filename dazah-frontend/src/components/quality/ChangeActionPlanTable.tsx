'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { Button, Input, Select, Space, Table, Tag, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { CloudDownloadOutlined, DeleteOutlined, EditOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import type { ChangeActionPlanListItem } from '@/types/quality'
import { ResizableHeaderCell } from './resizable-table-header'

interface ChangeActionPlanFilters {
  change_code: string
  project_name: string
  related_work: string
  owner_name: string
  status: string
}

interface ChangeActionPlanTableProps {
  items: ChangeActionPlanListItem[]
  total: number
  loading: boolean
  page: number
  pageSize: number
  filters: ChangeActionPlanFilters
  onFilterChange: (patch: Partial<ChangeActionPlanFilters>) => void
  onPageChange: (page: number, pageSize: number) => void
  onRefresh: () => void
  onSyncAll: () => void
  onEdit: (record: ChangeActionPlanListItem) => void
  onSyncSingle: (record: ChangeActionPlanListItem) => void
  onDelete: (record: ChangeActionPlanListItem) => void
}

const COLUMN_WIDTH_STORAGE_KEY = 'quality-change-action-plan-table-column-widths-v1'

const defaultColumnWidths: Record<string, number> = {
  change_code: 160,
  project_name: 180,
  related_work: 260,
  owner_name: 120,
  director_name: 120,
  deadline_date: 140,
  status: 120,
  delay_flag: 120,
  delayed_deadline_date: 140,
  sync_status: 120,
  reminder_status: 160,
  action: 180,
}

const minColumnWidths: Record<string, number> = {
  change_code: 120,
  project_name: 140,
  related_work: 180,
  owner_name: 100,
  director_name: 100,
  deadline_date: 120,
  status: 100,
  delay_flag: 100,
  delayed_deadline_date: 120,
  sync_status: 100,
  reminder_status: 140,
  action: 160,
}

const statusOptions = [
  { label: '未启动', value: '未启动' },
  { label: '推进中', value: '推进中' },
  { label: '已完成', value: '已完成' },
  { label: '未按时完成', value: '未按时完成' },
]

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function renderSyncStatus(record: ChangeActionPlanListItem) {
  const color =
    record.sync_status === 'synced'
      ? 'green'
      : record.sync_status === 'failed'
        ? 'red'
        : 'gold'
  const label =
    record.sync_status === 'synced'
      ? '已同步'
      : record.sync_status === 'failed'
        ? '同步失败'
        : '待同步'
  return (
    <Tooltip title={record.sync_error || label}>
      <Tag color={color}>{label}</Tag>
    </Tooltip>
  )
}

function renderReminderStatus(record: ChangeActionPlanListItem) {
  if (!record.reminder_enabled) {
    return <Tag>未启用</Tag>
  }
  if (record.reminder_status === 'confirmed') {
    return (
      <Tooltip
        title={`确认人：${record.reminder_confirmed_by || '-'}\n确认时间：${formatDate(record.reminder_confirmed_at)}`}
      >
        <Tag color="green">已确认</Tag>
      </Tooltip>
    )
  }
  if (record.reminder_status === 'reminded') {
    return (
      <Tooltip title={`最近提醒：${formatDate(record.last_reminded_at)}`}>
        <Tag color="gold">已提醒</Tag>
      </Tooltip>
    )
  }
  return <Tag>待提醒</Tag>
}

export function ChangeActionPlanTable({
  items,
  total,
  loading,
  page,
  pageSize,
  filters,
  onFilterChange,
  onPageChange,
  onRefresh,
  onSyncAll,
  onEdit,
  onSyncSingle,
  onDelete,
}: ChangeActionPlanTableProps) {
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const resizingRef = useRef<{
    columnKey: string
    startX: number
    startWidth: number
  } | null>(null)

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY)
      if (!raw) return
      const saved = JSON.parse(raw) as Record<string, number>
      setColumnWidths({ ...defaultColumnWidths, ...saved })
    } catch {
      setColumnWidths(defaultColumnWidths)
    }
  }, [])

  useEffect(() => {
    window.localStorage.setItem(COLUMN_WIDTH_STORAGE_KEY, JSON.stringify(columnWidths))
  }, [columnWidths])

  const handleResizeStart = useCallback((columnKey: string, event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()

    resizingRef.current = {
      columnKey,
      startX: event.clientX,
      startWidth: columnWidths[columnKey] ?? defaultColumnWidths[columnKey] ?? 120,
    }

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const current = resizingRef.current
      if (!current) return
      const delta = moveEvent.clientX - current.startX
      const nextWidth = Math.max(
        minColumnWidths[current.columnKey] ?? 80,
        current.startWidth + delta,
      )
      setColumnWidths((prev) => ({
        ...prev,
        [current.columnKey]: nextWidth,
      }))
    }

    const handleMouseUp = () => {
      resizingRef.current = null
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [columnWidths])

  const baseColumns = useMemo<TableColumnsType<ChangeActionPlanListItem>>(
    () => [
      {
        title: '变更控制号',
        dataIndex: 'change_code',
        key: 'change_code',
        width: defaultColumnWidths.change_code,
        render: (value: string, record) =>
          record.change_id ? <Link href={`/quality/change/${record.change_id}`}>{value}</Link> : value,
      },
      { title: '项目名称', dataIndex: 'project_name', key: 'project_name', width: defaultColumnWidths.project_name },
      {
        title: '涉及工作',
        dataIndex: 'related_work',
        key: 'related_work',
        width: defaultColumnWidths.related_work,
        render: (value: string | null) => (
          <Tooltip title={value || '-'}>
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>{value || '-'}</div>
          </Tooltip>
        ),
      },
      { title: '总负责人', dataIndex: 'owner_name', key: 'owner_name', width: defaultColumnWidths.owner_name, render: (value: string | null) => value || '-' },
      { title: '部门负责人', dataIndex: 'director_name', key: 'director_name', width: defaultColumnWidths.director_name, render: (value: string | null) => value || '-' },
      { title: '项目截止时间', dataIndex: 'deadline_date', key: 'deadline_date', width: defaultColumnWidths.deadline_date, render: formatDate },
      { title: '状态', dataIndex: 'status', key: 'status', width: defaultColumnWidths.status, render: (value: string | null) => value || '-' },
      { title: '延期', dataIndex: 'delay_flag', key: 'delay_flag', width: defaultColumnWidths.delay_flag, render: (value: string | null) => value || '-' },
      { title: '延期后日期', dataIndex: 'delayed_deadline_date', key: 'delayed_deadline_date', width: defaultColumnWidths.delayed_deadline_date, render: formatDate },
      {
        title: '同步状态',
        key: 'sync_status',
        width: defaultColumnWidths.sync_status,
        render: (_, record) => renderSyncStatus(record),
      },
      {
        title: '提醒状态',
        key: 'reminder_status',
        width: defaultColumnWidths.reminder_status,
        render: (_, record) => renderReminderStatus(record),
      },
      {
        title: '操作',
        key: 'action',
        width: defaultColumnWidths.action,
        fixed: 'right' as const,
        render: (_, record) => (
          <Space>
            <Button type="text" icon={<EditOutlined />} onClick={() => onEdit(record)} />
            <Button type="text" icon={<SyncOutlined />} onClick={() => onSyncSingle(record)} />
            <Button type="text" danger icon={<DeleteOutlined />} onClick={() => onDelete(record)} />
          </Space>
        ),
      },
    ],
    [onEdit, onSyncSingle, onDelete]
  )

  const columns = useMemo<TableColumnsType<ChangeActionPlanListItem>>(
    () =>
      baseColumns.map((column) => {
        const dataIndex = 'dataIndex' in column ? column.dataIndex : undefined
        const normalizedDataIndex = Array.isArray(dataIndex) ? dataIndex.join('.') : dataIndex
        const columnKey = String(column.key ?? normalizedDataIndex ?? '')
        const width = columnKey
          ? columnWidths[columnKey] ?? (typeof column.width === 'number' ? column.width : undefined)
          : column.width
        const minWidth = columnKey ? minColumnWidths[columnKey] : undefined
        const canResize = Boolean(columnKey && width)

        return {
          ...column,
          width,
          onHeaderCell: () => ({
            width,
            minWidth,
            resizable: canResize,
            onResizeStart: canResize
              // eslint-disable-next-line react-hooks/refs
              ? (event: React.MouseEvent<HTMLDivElement>) => handleResizeStart(columnKey, event)
              : undefined,
          }),
        }
      }),
    [baseColumns, columnWidths, handleResizeStart]
  )

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Input
          placeholder="变更控制号"
          style={{ width: 180 }}
          value={filters.change_code}
          onChange={(e) => onFilterChange({ change_code: e.target.value })}
          allowClear
        />
        <Input
          placeholder="项目名称"
          style={{ width: 180 }}
          value={filters.project_name}
          onChange={(e) => onFilterChange({ project_name: e.target.value })}
          allowClear
        />
        <Input
          placeholder="涉及工作"
          style={{ width: 220 }}
          value={filters.related_work}
          onChange={(e) => onFilterChange({ related_work: e.target.value })}
          allowClear
        />
        <Input
          placeholder="总负责人"
          style={{ width: 160 }}
          value={filters.owner_name}
          onChange={(e) => onFilterChange({ owner_name: e.target.value })}
          allowClear
        />
        <Select
          placeholder="状态"
          style={{ width: 140 }}
          value={filters.status || undefined}
          onChange={(value) => onFilterChange({ status: value ?? '' })}
          allowClear
          options={statusOptions}
        />
      </Space>

      <Space style={{ marginBottom: 12 }}>
        <Button icon={<CloudDownloadOutlined />} onClick={onSyncAll}>
          拉取飞书
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          刷新
        </Button>
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={columns}
        scroll={{ x: 1700 }}
        components={{ header: { cell: ResizableHeaderCell } }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: onPageChange,
        }}
      />
    </div>
  )
}
