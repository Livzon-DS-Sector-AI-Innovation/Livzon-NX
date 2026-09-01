'use client'

import { TableEmptyState } from './TableEmptyState'
import { qualityTokens } from './themeTokens'

import { useCallback, useMemo, useState } from 'react'
import { App, Table, Tag, Space, Button, Input, Select, Tooltip, DatePicker } from 'antd'
import { DeleteOutlined, SearchOutlined, ImportOutlined, ExportOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { DeviationListItem, DeviationStatus, DeviationLevel } from '@/types/quality'
import { useDeviationStore } from '@/stores/quality'
import { deleteDeviation, batchDeleteDeviations } from '@/actions/quality-deviation'
import Link from 'next/link'
import { DeviationImportDrawer } from './DeviationImportDrawer'
import dayjs, { Dayjs } from 'dayjs'

const statusConfig: Record<DeviationStatus, { color: string; bgColor: string; label: string }> = {
  draft: { color: qualityTokens.textMuted, bgColor: '#f0eeec', label: '草稿' },
  pending_ai_analysis: { color: qualityTokens.primary, bgColor: '#e6f4ff', label: '待AI分析' },
  pending_investigation: { color: '#7b3ff2', bgColor: '#e6e0f5', label: '待调查' },
  pending_dept_head_review: { color: qualityTokens.orangeText, bgColor: qualityTokens.warningSoft, label: '待部门审核' },
  pending_cross_dept_head_review: { color: qualityTokens.orangeText, bgColor: qualityTokens.warningSoft, label: '待跨部门审核' },
  pending_qa_review: { color: qualityTokens.orangeText, bgColor: qualityTokens.warningSoft, label: '待QA审核' },
  pending_qa_head_review: { color: qualityTokens.orangeText, bgColor: qualityTokens.warningSoft, label: '待QA负责人审核' },
  pending_quality_head_review: { color: qualityTokens.orangeText, bgColor: qualityTokens.warningSoft, label: '待质量负责人审核' },
  pending_final_code: { color: '#13c2c2', bgColor: '#e6fffb', label: '待编号' },
  returned: { color: '#e03131', bgColor: '#fff1f0', label: '已退回' },
  closed: { color: qualityTokens.success, bgColor: '#e6f7e6', label: '已关闭' },
  cancelled: { color: qualityTokens.textMuted, bgColor: '#f0eeec', label: '已取消' },
}

const levelConfig: Record<DeviationLevel, { color: string; bgColor: string; label: string }> = {
  minor: { color: qualityTokens.success, bgColor: '#e6f7e6', label: '次要偏差' },
  moderate: { color: qualityTokens.orangeText, bgColor: qualityTokens.warningSoft, label: '中等偏差' },
  major: { color: '#e03131', bgColor: '#fff1f0', label: '严重偏差' },
}

const statusOptions = Object.entries(statusConfig).map(([value, config]) => ({
  label: config.label,
  value,
}))

const levelOptions = Object.entries(levelConfig).map(([value, config]) => ({
  label: config.label,
  value,
}))

const booleanFilterOptions = [
  { label: '是', value: 'true' },
  { label: '否', value: 'false' },
]

interface DeviationTableProps {
  loading?: boolean
}

const defaultColumnWidths: Record<string, number> = {
  index: 54,
  deviation_code: 126,
  product_batch: 135,
  description: 378,
  has_occurred_before: 108,
  root_cause_analysis: 288,
  level: 81,
  investigation_completed_at: 108,
  action: 120,
}

function formatDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export function DeviationTable({ loading = false }: DeviationTableProps) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [importOpen, setImportOpen] = useState(false)
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const {
    deviations,
    total,
    page,
    pageSize,
    statusFilter,
    levelFilter,
    departmentFilter,
    keyword,
    deviationCodeFilter,
    productKeywordFilter,
    hasOccurredBeforeFilter,
    isClosedFilter,
    investigationCompletedFrom,
    investigationCompletedTo,
    rootCauseKeywordFilter,
    correctiveActionsKeywordFilter,
    setPage,
    setPageSize,
    setStatusFilter,
    setLevelFilter,
    setDepartmentFilter,
    setKeyword,
    setDeviationCodeFilter,
    setProductKeywordFilter,
    setHasOccurredBeforeFilter,
    setIsClosedFilter,
    setInvestigationCompletedRange,
    setRootCauseKeywordFilter,
    setCorrectiveActionsKeywordFilter,
    resetFilters,
  } = useDeviationStore()

  const handleDelete = useCallback((record: DeviationListItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除偏差 "${record.title}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteDeviation(record.id)
          message.success('删除成功')
          queryClient.invalidateQueries({ queryKey: ['quality-deviation'] })
        } catch (error) {
          message.error((error instanceof Error ? error.message : '') || '删除失败')
        }
      },
    })
  }, [modal, message, queryClient])

  const handleExport = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (statusFilter) params.set('status', statusFilter)
      if (levelFilter) params.set('level', levelFilter)
      if (departmentFilter) params.set('department', departmentFilter)
      if (keyword) params.set('keyword', keyword)
      if (deviationCodeFilter) params.set('deviation_code', deviationCodeFilter)
      if (productKeywordFilter) params.set('product_keyword', productKeywordFilter)
      if (hasOccurredBeforeFilter) params.set('has_occurred_before', hasOccurredBeforeFilter)
      if (isClosedFilter) params.set('is_closed', isClosedFilter)
      if (investigationCompletedFrom) params.set('investigation_completed_from', investigationCompletedFrom)
      if (investigationCompletedTo) params.set('investigation_completed_to', investigationCompletedTo)
      if (rootCauseKeywordFilter) params.set('root_cause_keyword', rootCauseKeywordFilter)
      if (correctiveActionsKeywordFilter) params.set('corrective_actions_keyword', correctiveActionsKeywordFilter)
      const res = await fetch(`/api/v1/quality/deviations/export?${params.toString()}`)
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `偏差登记表_${new Date().toISOString().slice(0, 10)}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    }
  }, [
    statusFilter,
    levelFilter,
    departmentFilter,
    keyword,
    deviationCodeFilter,
    productKeywordFilter,
    hasOccurredBeforeFilter,
    isClosedFilter,
    investigationCompletedFrom,
    investigationCompletedTo,
    rootCauseKeywordFilter,
    correctiveActionsKeywordFilter,
    message,
  ])

  const handleBatchDelete = useCallback(() => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的记录')
      return
    }
    modal.confirm({
      title: '确认批量删除',
      content: `确定要删除选中的 ${selectedRowKeys.length} 条偏差记录吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const result = await batchDeleteDeviations(selectedRowKeys)
          message.success(`已删除 ${result?.deleted ?? 0} 条记录`)
          setSelectedRowKeys([])
          queryClient.invalidateQueries({ queryKey: ['quality-deviation'] })
        } catch (error) {
          message.error((error instanceof Error ? error.message : '') || '批量删除失败')
        }
      },
    })
  }, [message, modal, queryClient, selectedRowKeys])

  const resetAllFilters = useCallback(() => {
    resetFilters()
    message.success('已清空筛选条件')
  }, [message, resetFilters])

  const investigationRangeValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!investigationCompletedFrom || !investigationCompletedTo) return null
    return [dayjs(investigationCompletedFrom), dayjs(investigationCompletedTo)]
  }, [investigationCompletedFrom, investigationCompletedTo])

  const baseColumns = [
    {
      title: '序号',
      key: 'index',
      width: defaultColumnWidths.index,
      render: (_: unknown, __: unknown, index: number) => (page - 1) * pageSize + index + 1,
    },
    {
      title: '偏差编号',
      dataIndex: 'deviation_code',
      key: 'deviation_code',
      width: defaultColumnWidths.deviation_code,
      fixed: 'start' as const,
    },
    {
      title: '产品名称/批号',
      key: 'product_batch',
      width: defaultColumnWidths.product_batch,
      render: (_: unknown, record: any) => {
        const items = record.affected_items || '-'
        const batch = record.batch_number || '-'
        if (items === '-' && batch === '-') return '-'
        return (
          <div>
            <div>{items}</div>
            {batch !== '-' && <div style={{ color: '#999', fontSize: 12 }}>{batch}</div>}
          </div>
        )
      },
    },
    {
      title: '偏差简要描述',
      dataIndex: 'description',
      key: 'description',
      width: defaultColumnWidths.description,
      render: (text: string | null, record: DeviationListItem) => (
        <Tooltip title={text || record.title} placement="topLeft">
          <Link href={`/quality/deviations/${record.id}`} className="text-blue-600 hover:text-blue-800">
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.5 }}>
              {text || record.title || '-'}
            </div>
          </Link>
        </Tooltip>
      ),
    },
    {
      title: '偏差是否曾发生',
      dataIndex: 'has_occurred_before',
      key: 'has_occurred_before',
      width: defaultColumnWidths.has_occurred_before,
      render: (v: boolean | null, record: DeviationListItem) => {
        // 对齐桌面模板勾选格式：选中项 ☑，未选中项 □
        // 曾发生→"☑是 编号：[编号]\n□否"；未发生/未知→"□是 编号：\n☑否"
        const isTrue = v === true
        const codeText = record.previous_occurrence_code ?? ''
        return (
          <div style={{ whiteSpace: 'pre-line', lineHeight: 1.6 }}>
            <div style={{ color: isTrue ? '#000' : '#999' }}>
              {isTrue ? '☑' : '□'}是{isTrue && codeText ? ` 编号：${codeText}` : ' 编号：'}
            </div>
            <div style={{ color: isTrue ? '#999' : '#000' }}>{isTrue ? '□否' : '☑否'}</div>
          </div>
        )
      },
    },
    {
      title: '根本原因',
      dataIndex: 'root_cause_analysis',
      key: 'root_cause_analysis',
      width: defaultColumnWidths.root_cause_analysis,
      render: (v: string | null) => {
        if (!v) return '-'
        return (
          <Tooltip title={v}>
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.5 }}>{v}</div>
          </Tooltip>
        )
      },
    },
    {
      title: '偏差等级',
      dataIndex: 'level',
      key: 'level',
      width: defaultColumnWidths.level,
      render: (level: DeviationLevel | null) => {
        if (!level) return '-'
        const config = levelConfig[level] || { color: qualityTokens.textMuted, bgColor: '#f0eeec', label: level }
        return (
          <Tag style={{ color: config.color, background: config.bgColor, border: 'none', borderRadius: 4, fontWeight: 500 }}>
            {config.label}
          </Tag>
        )
      },
    },
    {
      title: '调查完成时间',
      key: 'investigation_completed_at',
      width: defaultColumnWidths.investigation_completed_at,
      render: (_: unknown, record: any) => {
        const v = record.investigation_completed_at || record.status_updated_at
        return formatDate(v)
      },
    },
    {
      title: '操作',
      key: 'action',
      width: defaultColumnWidths.action,
      fixed: 'end' as const,
      render: (_: unknown, record: DeviationListItem) => (
        <Space>
          <Link href={`/quality/deviations/${record.id}`}>
            <Button type="link" style={{ padding: 0 }}>
              详情
            </Button>
          </Link>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} style={{ padding: 0 }}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const columns = useMemo(() => baseColumns, [baseColumns])

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input
          placeholder="偏差编号"
          style={{ width: 160 }}
          value={deviationCodeFilter}
          onChange={(e) => setDeviationCodeFilter(e.target.value)}
          allowClear
        />
        <Input
          placeholder="产品名称/批号"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 220 }}
          value={productKeywordFilter}
          onChange={(e) => setProductKeywordFilter(e.target.value)}
          allowClear
        />
        <DatePicker.RangePicker
          placeholder={['调查完成开始', '调查完成结束']}
          value={investigationRangeValue}
          onChange={(dates) =>
            setInvestigationCompletedRange(
              dates?.[0] ? dates[0].format('YYYY-MM-DD') : '',
              dates?.[1] ? dates[1].format('YYYY-MM-DD') : '',
            )
          }
        />
        <Select
          placeholder="是否关闭"
          allowClear
          style={{ width: 120 }}
          value={isClosedFilter || undefined}
          onChange={(value) => setIsClosedFilter((value || '') as '' | 'true' | 'false')}
          options={booleanFilterOptions}
        />
        <Select
          placeholder="是否曾发生"
          allowClear
          style={{ width: 120 }}
          value={hasOccurredBeforeFilter || undefined}
          onChange={(value) => setHasOccurredBeforeFilter((value || '') as '' | 'true' | 'false')}
          options={booleanFilterOptions}
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
            background: qualityTokens.bgSoft,
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
            placeholder="级别"
            allowClear
            value={levelFilter || undefined}
            onChange={(value) => setLevelFilter(value || '')}
            options={levelOptions}
          />
          <Input
            placeholder="部门"
            value={departmentFilter}
            onChange={(e) => setDepartmentFilter(e.target.value)}
            allowClear
          />
          <Input
            placeholder="标题/描述关键词"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            allowClear
          />
          <Input
            placeholder="根本原因关键词"
            value={rootCauseKeywordFilter}
            onChange={(e) => setRootCauseKeywordFilter(e.target.value)}
            allowClear
          />
          <Input
            placeholder="纠正预防措施关键词"
            value={correctiveActionsKeywordFilter}
            onChange={(e) => setCorrectiveActionsKeywordFilter(e.target.value)}
            allowClear
          />
        </div>
      ) : null}
      <Table
        columns={columns}
        dataSource={deviations}
        locale={{
          emptyText: <TableEmptyState hasFilters={Boolean(keyword || statusFilter || levelFilter)} />,
        }}
        rowKey="id"
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
      <DeviationImportDrawer
        isOpen={importOpen}
        onClose={() => setImportOpen(false)}
        onSuccess={() => queryClient.invalidateQueries({ queryKey: ['quality-deviation'] })}
      />
    </div>
  )
}
