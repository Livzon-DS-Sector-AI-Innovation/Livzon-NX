'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Table, Space, Button, Input, Select, Tooltip, DatePicker } from 'antd'
import { EditOutlined, DeleteOutlined, SearchOutlined, ImportOutlined, ExportOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { CapaListItem, CapaWorkflowStatus, CapaSource } from '@/types/quality'
import { useCapaStore } from '@/stores/quality'
import { deleteCapa, batchDeleteFeishuCapas } from '@/actions/quality-capa'
import Link from 'next/link'
import { CapaImportDrawer } from './CapaImportDrawer'
import { buildResizableColumns, ResizableHeaderCell } from './ResizableTableHeader'
import dayjs, { Dayjs } from 'dayjs'

const statusConfig: Record<CapaWorkflowStatus, { color: string; bgColor: string; label: string }> = {
  draft: { color: '#787671', bgColor: '#f0eeec', label: '草稿' },
  part_a: { color: '#1677ff', bgColor: '#e6f4ff', label: 'A部分' },
  part_b: { color: '#1677ff', bgColor: '#e6f4ff', label: 'B部分' },
  part_c: { color: '#1677ff', bgColor: '#e6f4ff', label: 'C部分' },
  pending_dept_head_confirm: { color: '#fa8c16', bgColor: '#fff7e6', label: '待部门主管确认' },
  pending_qa_review: { color: '#fa8c16', bgColor: '#fff7e6', label: '待QA审核' },
  pending_q_head_approval: { color: '#fa8c16', bgColor: '#fff7e6', label: '待质量主管审批' },
  executing: { color: '#13c2c2', bgColor: '#e6fffb', label: '执行中' },
  pending_evaluation: { color: '#722ed1', bgColor: '#f9f0ff', label: '待效果评价' },
  submitted: { color: '#1677ff', bgColor: '#e6f4ff', label: '已提交' },
  under_execution: { color: '#7b3ff2', bgColor: '#e6e0f5', label: '执行中' },
  evaluation: { color: '#dd5b00', bgColor: '#fff7e6', label: '评估中' },
  closed: { color: '#1aae39', bgColor: '#e6f7e6', label: '已关闭' },
  returned: { color: '#e03131', bgColor: '#fff1f0', label: '已退回' },
  cancelled: { color: '#787671', bgColor: '#f0eeec', label: '已取消' },
}

const sourceConfig: Record<CapaSource, { label: string }> = {
  deviation: { label: '偏差' },
  audit: { label: '审计' },
  customer_complaint: { label: '客户投诉' },
  internal_inspection: { label: '内部检查' },
}

const categoryOptions = [
  { label: 'A类', value: 'A' },
  { label: 'B类', value: 'B' },
  { label: 'C类', value: 'C' },
]

const statusOptions = Object.entries(statusConfig).map(([value, config]) => ({
  label: config.label,
  value,
}))

const sourceOptions = Object.entries(sourceConfig).map(([value, config]) => ({
  label: config.label,
  value,
}))

const evaluationResultOptions = [
  { label: '有效', value: '有效' },
  { label: '无效', value: '无效' },
]

interface CapaTableProps {
  capas: CapaListItem[]
  total: number
  loading?: boolean
}

const COLUMN_WIDTH_STORAGE_KEY = 'quality-capa-table-column-widths-v2'

const defaultColumnWidths: Record<string, number> = {
  capa_code: 150,
  created_at: 140,
  department: 110,
  affected_product: 150,
  source_code: 140,
  title: 420,
  action: 120,
}

const minColumnWidths: Record<string, number> = {
  capa_code: 120,
  created_at: 130,
  department: 90,
  affected_product: 120,
  source_code: 120,
  title: 260,
  action: 100,
}

function formatDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export function CapaTable({ capas, total, loading = false }: CapaTableProps) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [importOpen, setImportOpen] = useState(false)
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const {
    page,
    pageSize,
    statusFilter,
    sourceFilter,
    categoryFilter,
    keyword,
    capaCodeFilter,
    affectedProductFilter,
    sourceCodeFilter,
    evaluationResultFilter,
    closureDateFrom,
    closureDateTo,
    departmentFilter,
    qaConfirmerFilter,
    setPage,
    setPageSize,
    setStatusFilter,
    setSourceFilter,
    setCategoryFilter,
    setKeyword,
    setCapaCodeFilter,
    setAffectedProductFilter,
    setSourceCodeFilter,
    setEvaluationResultFilter,
    setClosureDateRange,
    setDepartmentFilter,
    setQaConfirmerFilter,
    resetFilters,
  } = useCapaStore()

  const handleDelete = useCallback((record: CapaListItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除CAPA "${record.title}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteCapa(record.id)
          message.success('删除成功')
          queryClient.invalidateQueries({ queryKey: ['quality-capa'] })
        } catch (error: unknown) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }, [modal, message, queryClient])

  const handleExport = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (statusFilter) params.set('status', statusFilter)
      if (sourceFilter) params.set('source', sourceFilter)
      if (categoryFilter) params.set('category', categoryFilter)
      if (keyword) params.set('keyword', keyword)
      if (capaCodeFilter) params.set('capa_code', capaCodeFilter)
      if (affectedProductFilter) params.set('affected_product', affectedProductFilter)
      if (sourceCodeFilter) params.set('source_code', sourceCodeFilter)
      if (evaluationResultFilter) params.set('evaluation_result', evaluationResultFilter)
      if (closureDateFrom) params.set('closure_date_from', closureDateFrom)
      if (closureDateTo) params.set('closure_date_to', closureDateTo)
      if (departmentFilter) params.set('department', departmentFilter)
      if (qaConfirmerFilter) params.set('qa_confirmer', qaConfirmerFilter)
      const res = await fetch(`/api/v1/quality/capas/export?${params.toString()}`)
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `CAPA登记汇总表_${new Date().toISOString().slice(0, 10)}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '导出失败')
    }
  }, [
    statusFilter,
    sourceFilter,
    categoryFilter,
    keyword,
    capaCodeFilter,
    affectedProductFilter,
    sourceCodeFilter,
    evaluationResultFilter,
    closureDateFrom,
    closureDateTo,
    departmentFilter,
    qaConfirmerFilter,
    message,
  ])

  const handleBatchDelete = useCallback(() => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的记录')
      return
    }
    modal.confirm({
      title: '确认批量删除',
      content: `确定要删除选中的 ${selectedRowKeys.length} 条 CAPA 记录吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const result = await batchDeleteFeishuCapas(selectedRowKeys)
          message.success(result.message)
          setSelectedRowKeys([])
          queryClient.invalidateQueries({ queryKey: ['quality-capa'] })
        } catch (error: unknown) {
          message.error(error instanceof Error ? error.message : '批量删除失败')
        }
      },
    })
  }, [message, modal, queryClient, selectedRowKeys])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY)
      if (!raw) return
      const saved = JSON.parse(raw) as Record<string, number>
      const normalized = Object.fromEntries(
        Object.entries({ ...defaultColumnWidths, ...saved }).map(([key, width]) => [
          key,
          Math.max(minColumnWidths[key] ?? 80, Number(width) || defaultColumnWidths[key] || 120),
        ]),
      )
      setColumnWidths(normalized)
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
    const startX = event.clientX
    const startWidth = columnWidths[columnKey] ?? defaultColumnWidths[columnKey] ?? 120

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX
      const nextWidth = Math.max(minColumnWidths[columnKey] ?? 80, startWidth + delta)
      setColumnWidths((prev) => ({
        ...prev,
        [columnKey]: nextWidth,
      }))
    }

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [columnWidths])

  const resetColumnWidths = useCallback(() => {
    setColumnWidths(defaultColumnWidths)
    window.localStorage.removeItem(COLUMN_WIDTH_STORAGE_KEY)
    message.success('已恢复默认列宽')
  }, [message])

  const resetAllFilters = useCallback(() => {
    resetFilters()
    message.success('已清空筛选条件')
  }, [message, resetFilters])

  const closureDateRangeValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!closureDateFrom || !closureDateTo) return null
    return [dayjs(closureDateFrom), dayjs(closureDateTo)]
  }, [closureDateFrom, closureDateTo])

  const baseColumns = useMemo(() => [
    {
      title: 'CAPA编号',
      dataIndex: 'capa_code',
      key: 'capa_code',
      width: defaultColumnWidths.capa_code,
      fixed: 'start' as const,
    },
    {
      title: '启动日期',
      dataIndex: 'created_at',
      key: 'created_at',
      width: defaultColumnWidths.created_at,
      render: (v: string) => formatDate(v),
    },
    {
      title: '事件部门',
      dataIndex: 'department',
      key: 'department',
      width: defaultColumnWidths.department,
      render: (v: string | null) => v || '-',
    },
    {
      title: '涉及产品',
      dataIndex: 'affected_product',
      key: 'affected_product',
      width: defaultColumnWidths.affected_product,
      render: (v: string | null) => v || '-',
    },
    {
      title: '来源编号',
      dataIndex: 'source_code',
      key: 'source_code',
      width: defaultColumnWidths.source_code,
      render: (v: string | null) => v || '-',
    },
    {
      title: 'CAPA简述',
      dataIndex: 'title',
      key: 'title',
      width: defaultColumnWidths.title,
      render: (text: string | null, record: CapaListItem) => (
        <Tooltip title={text} placement="topLeft">
          <Link href={`/quality/capas/${record.id}`} className="text-blue-600 hover:text-blue-800">
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.5 }}>
              {text || '-'}
            </div>
          </Link>
        </Tooltip>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: defaultColumnWidths.action,
      fixed: 'end' as const,
      render: (_: unknown, record: CapaListItem) => (
        <Space>
          <Link href={`/quality/capas/${record.id}`}>
            <Button type="link" icon={<EditOutlined />} style={{ padding: 0 }}>
              详情
            </Button>
          </Link>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} style={{ padding: 0 }}>
            删除
          </Button>
        </Space>
      ),
    },
  ], [handleDelete])

  const columns = useMemo(
    () =>
      buildResizableColumns(baseColumns, {
        widths: columnWidths,
        minWidths: minColumnWidths,
        onResizeStart: handleResizeStart,
      }),
    [baseColumns, columnWidths, handleResizeStart],
  )

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input
          placeholder="CAPA编号"
          style={{ width: 160 }}
          value={capaCodeFilter}
          onChange={(e) => setCapaCodeFilter(e.target.value)}
          allowClear
        />
        <Input
          placeholder="涉及产品"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 180 }}
          value={affectedProductFilter}
          onChange={(e) => setAffectedProductFilter(e.target.value)}
          allowClear
        />
        <Select
          placeholder="效果评估"
          allowClear
          style={{ width: 120 }}
          value={evaluationResultFilter || undefined}
          onChange={(value) => setEvaluationResultFilter((value || '') as '' | '有效' | '无效')}
          options={evaluationResultOptions}
        />
        <Input
          placeholder="来源编号"
          style={{ width: 160 }}
          value={sourceCodeFilter}
          onChange={(e) => setSourceCodeFilter(e.target.value)}
          allowClear
        />
        <Button icon={<FilterOutlined />} onClick={() => setShowAdvancedFilters((prev) => !prev)}>
          {showAdvancedFilters ? '收起筛选' : '更多筛选'}
        </Button>
        <Button icon={<ReloadOutlined />} onClick={resetAllFilters}>
          重置筛选
        </Button>
        <div style={{ flex: 1 }} />
        <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
          导入
        </Button>
        <Button danger disabled={selectedRowKeys.length === 0} onClick={handleBatchDelete}>
          批量删除
        </Button>
        <Button onClick={resetColumnWidths}>
          恢复默认列宽
        </Button>
        <Button icon={<ExportOutlined />} onClick={handleExport}>
          导出
        </Button>
      </div>
      {showAdvancedFilters ? (
        <div
          style={{
            marginBottom: 16,
            padding: 16,
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            background: '#fafafa',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          <Select
            placeholder="状态"
            allowClear
            value={statusFilter || undefined}
            onChange={(value) => setStatusFilter(value || '')}
            options={statusOptions}
          />
          <Select
            placeholder="来源"
            allowClear
            value={sourceFilter || undefined}
            onChange={(value) => setSourceFilter(value || '')}
            options={sourceOptions}
          />
          <Select
            placeholder="类别"
            allowClear
            value={categoryFilter || undefined}
            onChange={(value) => setCategoryFilter(value || '')}
            options={categoryOptions}
          />
          <Input
            placeholder="事件部门"
            value={departmentFilter}
            onChange={(e) => setDepartmentFilter(e.target.value)}
            allowClear
          />
          <Input
            placeholder="CAPA简述关键词"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            allowClear
          />
          <DatePicker.RangePicker
            placeholder={['关闭日期开始', '关闭日期结束']}
            value={closureDateRangeValue}
            onChange={(dates) =>
              setClosureDateRange(
                dates?.[0] ? dates[0].format('YYYY-MM-DD') : '',
                dates?.[1] ? dates[1].format('YYYY-MM-DD') : '',
              )
            }
          />
          <Input
            placeholder="QA质量员"
            value={qaConfirmerFilter}
            onChange={(e) => setQaConfirmerFilter(e.target.value)}
            allowClear
          />
        </div>
      ) : null}
      <Table
        columns={columns}
        dataSource={capas}
        rowKey="id"
        components={{
          header: {
            cell: ResizableHeaderCell,
          },
        }}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys as string[]),
        }}
        size="small"
        loading={loading}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize: pageSize,
          total: total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (value) => `共 ${value} 条`,
          onChange: (newPage, newPageSize) => {
            setPage(newPage)
            setPageSize(newPageSize)
          },
        }}
      />
      <CapaImportDrawer
        isOpen={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['quality-capa'] })}
      />
    </div>
  )
}
