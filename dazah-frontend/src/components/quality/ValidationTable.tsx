'use client'

import { qualityTokens } from './themeTokens'
import { useState, useCallback } from 'react'
import { Button, Input, Select, Space, Table, Tag, Tooltip, DatePicker, App } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, FilterOutlined, EyeOutlined } from '@ant-design/icons'
import type { ValidationListItem } from '@/types/quality'
import { TableEmptyState } from './TableEmptyState'
import dayjs, { Dayjs } from 'dayjs'

interface ValidationTableFilters {
  record_code: string
  keyword: string
  status: string
  department: string
  validation_type: string
  planned_end_date_from: string
  planned_end_date_to: string
  drafted_at_from: string
  drafted_at_to: string
  /** 年度表；空 = 验证总表 */
  year: string
}

interface ValidationTableProps {
  mode: 'master' | 'child'
  validationType?: string
  items: ValidationListItem[]
  total: number
  loading: boolean
  page: number
  pageSize: number
  filters: ValidationTableFilters
  onFilterChange: (patch: Partial<ValidationTableFilters>) => void
  onPageChange: (page: number, pageSize: number) => void
  onRefresh: () => void
  onCreate: () => void
  onDetail?: (record: ValidationListItem) => void
  onEdit: (record: ValidationListItem) => void
  onDelete: (record: ValidationListItem) => void
  onBatchDelete?: (recordIds: string[]) => void
}

const statusOptions = [
  { label: '完成', value: '完成' },
  { label: '未完成', value: '未完成' },
  { label: '待完成', value: '待完成' },
]

const statusLabelMap: Record<string, string> = {
  '完成': '完成',
  '未完成': '未完成',
  '待完成': '待完成',
  completed: '完成',
  incomplete: '未完成',
  pending: '待完成',
}

const validationTypeLabelMap: Record<string, string> = {
  equipment_qualification: '设备确认',
  process_validation: '工艺验证',
  cleaning_validation: '清洁验证',
  other_validation: '其他验证',
}

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

function renderStatus(status: string | null) {
  if (!status) return '-'
  const normalized = statusLabelMap[status] ?? status
  const color =
    normalized === '完成'
      ? 'green'
      : normalized === '待完成'
        ? 'orange'
        : 'red'
  return <Tag color={color}>{normalized}</Tag>
}

function renderProductCodes(codes: string[] | string | null | undefined) {
  if (!codes) return '-'
  const list = Array.isArray(codes) ? codes : [codes]
  if (list.length === 0) return '-'
  return (
    <Space wrap>
      {list.map((code) => (
        <Tag key={code}>{code}</Tag>
      ))}
    </Space>
  )
}

export function ValidationTable({
  mode,
  validationType,
  items,
  total,
  loading,
  page,
  pageSize,
  filters,
  onFilterChange,
  onPageChange,
  onRefresh,
  onCreate,
  onDetail,
  onEdit,
  onDelete,
  onBatchDelete,
}: ValidationTableProps) {
  const { message, modal } = App.useApp()
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])

  // 年度选项：2024-2028（未配置的年度表列表为空，可在飞书同步设置中绑定）
  const yearOptions = [
    { label: '总表（全部年份）', value: '' },
    ...Array.from({ length: 5 }, (_, i) => 2024 + i).map((year) => ({
      label: `${year}年`,
      value: String(year),
    })),
  ]

  // 部门选项
  const departmentOptions = [
    { label: '101 一车间', value: '101 一车间' },
    { label: '101 二车间', value: '101 二车间' },
    { label: '102 一车间', value: '102 一车间' },
    { label: '102 二车间', value: '102 二车间' },
    { label: '103 车间', value: '103 车间' },
    { label: '201 一车间', value: '201 一车间' },
    { label: '201 二车间', value: '201 二车间' },
    { label: '202 车间', value: '202 车间' },
    { label: '203 车间', value: '203 车间' },
    { label: 'QC', value: 'QC' },
    { label: '生产管理部', value: '生产管理部' },
    { label: '设备工程部', value: '设备工程部' },
    { label: '动力部', value: '动力部' },
  ]

  const validationTypeOptions = [
    { label: '设备确认', value: 'equipment_qualification' },
    { label: '工艺验证', value: 'process_validation' },
    { label: '清洁验证', value: 'cleaning_validation' },
    { label: '其他验证', value: 'other_validation' },
  ]

  // 批量删除
  const handleBatchDelete = useCallback(() => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的记录')
      return
    }
    modal.confirm({
      title: '确认批量删除',
      content: `确定要删除选中的 ${selectedRowKeys.length} 条记录吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          if (onBatchDelete) {
            await onBatchDelete(selectedRowKeys)
          }
          message.success(`成功删除 ${selectedRowKeys.length} 条记录`)
          setSelectedRowKeys([])
          onRefresh()
        } catch (error: unknown) {
          const msg = error instanceof Error ? error.message : '批量删除失败'
          message.error(msg)
        }
      },
    })
  }, [selectedRowKeys, onBatchDelete, onRefresh, message, modal])

  // 重置筛选
  const handleResetFilters = useCallback(() => {
    onFilterChange({
      record_code: '',
      keyword: '',
      status: '',
      department: '',
      validation_type: '',
      planned_end_date_from: '',
      planned_end_date_to: '',
      drafted_at_from: '',
      drafted_at_to: '',
      year: '',
    })
  }, [onFilterChange])

  // 验证计划页面列配置
  const planColumns: ColumnsType<ValidationListItem> = [
    {
      title: '确认名称',
      dataIndex: 'title',
      width: 280,
      render: (value: string, record: ValidationListItem) => (
        <Tooltip title={value}>
          <div style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>
            {onDetail ? (
              <a onClick={() => onDetail(record)}>{value}</a>
            ) : (
              value
            )}
          </div>
        </Tooltip>
      ),
    },
    {
      title: '验证类别',
      dataIndex: 'validation_type' as never,
      width: 130,
      render: (value: string | null) => validationTypeLabelMap[value ?? ''] ?? value ?? '-',
    },
    {
      title: '产品代码',
      dataIndex: 'product_codes',
      width: 160,
      render: renderProductCodes,
    },
    {
      title: '部门名称',
      dataIndex: 'department',
      width: 130,
      render: (value: string | null) => value || '-',
    },
    {
      title: '设备编码',
      dataIndex: 'equipment_code',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '验证到期时间',
      dataIndex: 'planned_end_date' as never,
      width: 130,
      render: formatDate,
    },
    {
      title: '任务状态',
      dataIndex: 'status',
      width: 110,
      render: (value: string | null) => renderStatus(value),
    },
  ]

  // 设备确认/工艺验证/清洁验证/其他验证 列配置
  const detailColumns: ColumnsType<ValidationListItem> = [
    {
      title: '确认名称',
      dataIndex: 'title',
      width: 280,
      render: (value: string) => (
        <Tooltip title={value}>
          <div style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>{value}</div>
        </Tooltip>
      ),
    },
    {
      title: '产品代码',
      dataIndex: 'product_codes',
      width: 160,
      render: renderProductCodes,
    },
    {
      title: '部门名称',
      dataIndex: 'department',
      width: 130,
      render: (value: string | null) => value || '-',
    },
    {
      title: '群组',
      dataIndex: 'group_chat',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '人员',
      dataIndex: 'participants',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '负责人',
      dataIndex: 'owner_name',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '方案名称',
      dataIndex: 'plan_name',
      width: 200,
      render: (value: string | null) => value || '-',
    },
    {
      title: '方案编码',
      dataIndex: 'plan_code',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '起草时间',
      dataIndex: 'drafted_at',
      width: 130,
      render: formatDate,
    },
    {
      title: '批准时间',
      dataIndex: 'approved_at',
      width: 130,
      render: formatDate,
    },
    {
      title: '报告编号',
      dataIndex: 'report_no',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '起草时间 1',
      dataIndex: 'drafted_at_1',
      width: 130,
      render: formatDate,
    },
    {
      title: '批准时间 1',
      dataIndex: 'approved_at_1',
      width: 130,
      render: formatDate,
    },
    {
      title: '再验证周期（几年）',
      dataIndex: 'revalidation_cycle_years',
      width: 140,
      render: (value: number | null) => (value != null ? `${value}年` : '-'),
    },
  ]

  // 根据验证类型选择列配置
  const columns = mode === 'master' ? planColumns : detailColumns

  // 添加操作列
  const columnsWithAction = [
    ...columns,
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: onDetail ? 150 : 120,
      render: (_: unknown, record: ValidationListItem) => (
        <Space size="small">
          {onDetail && (
            <Button type="text" icon={<EyeOutlined />} onClick={() => onDetail(record)} />
          )}
          <Button type="text" icon={<EditOutlined />} onClick={() => onEdit(record)} />
          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => onDelete(record)} />
        </Space>
      ),
    },
  ]

  // 行选择配置
  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys as string[]),
  }

  return (
    <div>
      {/* 基础筛选 */}
      <Space wrap style={{ marginBottom: 12 }}>
        <Input
          placeholder="确认名称/设备编码/方案编码"
          style={{ width: 280 }}
          value={filters.keyword}
          onChange={(e) => onFilterChange({ keyword: e.target.value })}
          allowClear
        />
        <Select
          placeholder="任务状态"
          style={{ width: 140 }}
          value={filters.status || undefined}
          onChange={(value) => onFilterChange({ status: value ?? '' })}
          allowClear
          options={statusOptions}
        />
        <Select
          placeholder="部门"
          style={{ width: 160 }}
          value={filters.department || undefined}
          onChange={(value) => onFilterChange({ department: value ?? '' })}
          allowClear
          showSearch
          options={departmentOptions}
        />
        {mode === 'master' && (
          <Select
            placeholder="验证类别"
            style={{ width: 160 }}
            value={filters.validation_type || undefined}
            onChange={(value) => onFilterChange({ validation_type: value ?? '' })}
            allowClear
            options={validationTypeOptions}
          />
        )}
        {mode === 'master' && (
          <Select
            placeholder="年度"
            style={{ width: 150 }}
            value={filters.year || ''}
            onChange={(value) => onFilterChange({ year: value ?? '' })}
            options={yearOptions}
          />
        )}
        <Button icon={<FilterOutlined />} onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}>
          {showAdvancedFilters ? '收起筛选' : '高级筛选'}
        </Button>
      </Space>

      {/* 高级筛选 */}
      {showAdvancedFilters && (
        <Space wrap style={{ marginBottom: 12, padding: 12, background: qualityTokens.bgSoft, borderRadius: 6 }}>
          <Input
            placeholder="记录编号"
            style={{ width: 200 }}
            value={filters.record_code}
            onChange={(e) => onFilterChange({ record_code: e.target.value })}
            allowClear
          />
          {mode === 'master' && (
            <>
              <DatePicker
                placeholder="验证到期时间起"
                style={{ width: 160 }}
                value={filters.planned_end_date_from ? dayjs(filters.planned_end_date_from) : null}
                onChange={(date: Dayjs | null) =>
                  onFilterChange({ planned_end_date_from: date ? date.format('YYYY-MM-DD') : '' })
                }
                allowClear
              />
              <DatePicker
                placeholder="验证到期时间止"
                style={{ width: 160 }}
                value={filters.planned_end_date_to ? dayjs(filters.planned_end_date_to) : null}
                onChange={(date: Dayjs | null) =>
                  onFilterChange({ planned_end_date_to: date ? date.format('YYYY-MM-DD') : '' })
                }
                allowClear
              />
            </>
          )}
          {mode === 'child' && (
            <>
              <DatePicker
                placeholder="起草时间起"
                style={{ width: 160 }}
                value={filters.drafted_at_from ? dayjs(filters.drafted_at_from) : null}
                onChange={(date: Dayjs | null) =>
                  onFilterChange({ drafted_at_from: date ? date.format('YYYY-MM-DD') : '' })
                }
                allowClear
              />
              <DatePicker
                placeholder="起草时间止"
                style={{ width: 160 }}
                value={filters.drafted_at_to ? dayjs(filters.drafted_at_to) : null}
                onChange={(date: Dayjs | null) =>
                  onFilterChange({ drafted_at_to: date ? date.format('YYYY-MM-DD') : '' })
                }
                allowClear
              />
            </>
          )}
          <Button onClick={handleResetFilters}>重置筛选</Button>
        </Space>
      )}

      {/* 操作按钮 */}
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={onCreate}>
          新增
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          刷新
        </Button>
        {selectedRowKeys.length > 0 && (
          <Button danger icon={<DeleteOutlined />} onClick={handleBatchDelete}>
            批量删除 ({selectedRowKeys.length})
          </Button>
        )}
      </Space>

      <Table
        rowKey="record_id"
        loading={loading}
        dataSource={items}
        locale={{
          emptyText: (
            <TableEmptyState
              hasFilters={Boolean(filters.keyword || filters.status || filters.department)}
            />
          ),
        }}
        columns={columnsWithAction}
        rowSelection={rowSelection}
        scroll={{ x: mode === 'master' ? 1500 : 2200 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: onPageChange,
        }}
      />
    </div>
  )
}
