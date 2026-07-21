'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App, Button, DatePicker, Input, Select, Space, Table, Tag, Tooltip } from 'antd'
import { DeleteOutlined, EditOutlined, ExportOutlined, FilterOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import Link from 'next/link'
import { deleteFeishuDeviationLedgerRecord, pullQualityRecordsFromFeishu } from '@/actions/quality'
import { exportFeishuDeviationLedgerRecords } from '@/lib/api/quality'
import { useDeviationStore } from '@/stores/quality'
import type { FeishuDeviationLedgerRecordItem } from '@/types/quality'
import { buildResizableColumns, ResizableHeaderCell } from './resizable-table-header'

const levelConfig: Record<string, { color: string; bgColor: string; label: string }> = {
  major: { color: '#e03131', bgColor: '#fff1f0', label: '重大' },
  '重大': { color: '#e03131', bgColor: '#fff1f0', label: '重大' },
  moderate: { color: '#dd5b00', bgColor: '#fff7e6', label: '次要' },
  '次要': { color: '#dd5b00', bgColor: '#fff7e6', label: '次要' },
  minor: { color: '#1aae39', bgColor: '#e6f7e6', label: '微小' },
  '微小': { color: '#1aae39', bgColor: '#e6f7e6', label: '微小' },
}

const booleanFilterOptions = [
  { label: '是', value: 'true' },
  { label: '否', value: 'false' },
]

interface DeviationTableProps {
  loading?: boolean
  onRefresh?: () => void
}

const COLUMN_WIDTH_STORAGE_KEY = 'quality-deviation-table-column-widths'

const defaultColumnWidths: Record<string, number> = {
  index: 60,
  deviation_code: 140,
  product_batch: 180,
  description: 420,
  has_occurred_before: 120,
  root_cause_analysis: 320,
  level: 100,
  investigation_completed_at: 160,
  corrective_actions: 420,
  material_disposition: 180,
  is_closed: 100,
  close_time: 160,
  action: 140,
}

const minColumnWidths: Record<string, number> = {
  index: 50,
  deviation_code: 110,
  product_batch: 130,
  description: 260,
  has_occurred_before: 100,
  root_cause_analysis: 220,
  level: 90,
  investigation_completed_at: 130,
  corrective_actions: 260,
  material_disposition: 130,
  is_closed: 90,
  close_time: 130,
  action: 120,
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : value
}

function renderTextWithTooltip(value: string | null | undefined) {
  if (!value) return '-'
  return (
    <Tooltip title={value}>
      <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.5 }}>{value}</div>
    </Tooltip>
  )
}

export function DeviationTable({ loading = false, onRefresh }: DeviationTableProps) {
  const { message, modal } = App.useApp()
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [pulling, setPulling] = useState(false)
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const resizingRef = useRef<{
    columnKey: string
    startX: number
    startWidth: number
  } | null>(null)
  const {
    deviations,
    total,
    page,
    pageSize,
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

  const handleDelete = useCallback((record: FeishuDeviationLedgerRecordItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除飞书偏差台账“${record.deviation_code || record.title || record.record_id}”吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteFeishuDeviationLedgerRecord(record.record_id)
          message.success('飞书台账已删除')
          onRefresh?.()
        } catch (error: any) {
          message.error(error?.message || '删除失败')
        }
      },
    })
  }, [message, modal, onRefresh])

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

  const resetColumnWidths = useCallback(() => {
    setColumnWidths(defaultColumnWidths)
    window.localStorage.removeItem(COLUMN_WIDTH_STORAGE_KEY)
    message.success('已恢复默认列宽')
  }, [message])

  const resetAllFilters = useCallback(() => {
    resetFilters()
    message.success('已清空筛选条件')
  }, [message, resetFilters])

  const handleExport = useCallback(async () => {
    try {
      const { blob, filename } = await exportFeishuDeviationLedgerRecords(
        selectedRowKeys.length > 0
          ? { record_ids: selectedRowKeys }
          : {
              keyword: keyword || undefined,
              deviation_code: deviationCodeFilter || undefined,
              product_keyword: productKeywordFilter || undefined,
              has_occurred_before: hasOccurredBeforeFilter || undefined,
              is_closed: isClosedFilter || undefined,
              investigation_completed_from: investigationCompletedFrom || undefined,
              investigation_completed_to: investigationCompletedTo || undefined,
              root_cause_keyword: rootCauseKeywordFilter || undefined,
              corrective_actions_keyword: correctiveActionsKeywordFilter || undefined,
            }
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      message.success(selectedRowKeys.length > 0 ? `已导出 ${selectedRowKeys.length} 条记录` : '导出成功')
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '导出失败')
    }
  }, [
    correctiveActionsKeywordFilter,
    deviationCodeFilter,
    hasOccurredBeforeFilter,
    investigationCompletedFrom,
    investigationCompletedTo,
    isClosedFilter,
    keyword,
    message,
    productKeywordFilter,
    rootCauseKeywordFilter,
    selectedRowKeys,
  ])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullQualityRecordsFromFeishu('deviation_ledger')
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      onRefresh?.()
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '从飞书拉取偏差台账失败')
    } finally {
      setPulling(false)
    }
  }, [message, onRefresh])

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
      render: (_: unknown, record: FeishuDeviationLedgerRecordItem) => {
        const productName = record.affected_items?.trim() || ''
        const batchNumber = record.batch_number?.trim() || ''
        const lines = [productName, batchNumber].filter(Boolean)

        if (lines.length === 0) return '-'

        return (
          <div style={{ lineHeight: 1.5 }}>
            {lines.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        )
      },
    },
    {
      title: '偏差简要描述',
      dataIndex: 'description',
      key: 'description',
      width: defaultColumnWidths.description,
      render: (text: string | null, record: FeishuDeviationLedgerRecordItem) => (
        <Tooltip title={text || record.title} placement="topLeft">
          <Link href={`/quality/deviations/${record.record_id}`} className="text-blue-600 hover:text-blue-800">
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
      render: (value: boolean | null | undefined) => {
        if (value === true) return <Tag color="green" style={{ borderRadius: 4, fontWeight: 500 }}>是</Tag>
        if (value === false) return <Tag style={{ borderRadius: 4 }}>否</Tag>
        return '-'
      },
    },
    {
      title: '根本原因',
      dataIndex: 'root_cause_analysis',
      key: 'root_cause_analysis',
      width: defaultColumnWidths.root_cause_analysis,
      render: (value: string | null) => renderTextWithTooltip(value),
    },
    {
      title: '偏差等级',
      dataIndex: 'level',
      key: 'level',
      width: defaultColumnWidths.level,
      render: (level: string | null) => {
        if (!level) return '-'
        const config = levelConfig[level]
        if (!config) {
          return <Tag style={{ borderRadius: 4 }}>{String(level)}</Tag>
        }
        return (
          <Tag style={{ color: config.color, background: config.bgColor, border: 'none', borderRadius: 4, fontWeight: 500 }}>
            {config.label}
          </Tag>
        )
      },
    },
    {
      title: '调查完成时间',
      dataIndex: 'investigation_completed_at',
      key: 'investigation_completed_at',
      width: defaultColumnWidths.investigation_completed_at,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '纠正预防措施',
      dataIndex: 'corrective_actions',
      key: 'corrective_actions',
      width: defaultColumnWidths.corrective_actions,
      render: (value: string | null) => renderTextWithTooltip(value),
    },
    {
      title: '产品/物料处理结果',
      dataIndex: 'material_disposition',
      key: 'material_disposition',
      width: defaultColumnWidths.material_disposition,
      render: (value: string | null) => renderTextWithTooltip(value),
    },
    {
      title: '是否关闭',
      key: 'is_closed',
      width: defaultColumnWidths.is_closed,
      render: (_: unknown, record: FeishuDeviationLedgerRecordItem) => {
        const isClosed = record.status === 'closed'
        return isClosed ? (
          <Tag color="green" style={{ borderRadius: 4, fontWeight: 500 }}>是</Tag>
        ) : (
          <Tag style={{ borderRadius: 4 }}>否</Tag>
        )
      },
    },
    {
      title: '关闭时间',
      dataIndex: 'close_time',
      key: 'close_time',
      width: defaultColumnWidths.close_time,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: defaultColumnWidths.action,
      fixed: 'end' as const,
      render: (_: unknown, record: FeishuDeviationLedgerRecordItem) => (
        <Space>
          <Link href={`/quality/deviations/${record.record_id}?edit=1`}>
            <Button type="link" icon={<EditOutlined />} style={{ padding: 0 }}>
              修改
            </Button>
          </Link>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
            style={{ padding: 0 }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const columns = useMemo(
    () =>
      // eslint-disable-next-line react-hooks/refs
      buildResizableColumns(baseColumns, {
        widths: columnWidths,
        minWidths: minColumnWidths,
        onResizeStart: handleResizeStart,
      }),
    [baseColumns, columnWidths, handleResizeStart],
  )

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>偏差台账</h1>
      </div>
      <div
        style={{
          marginBottom: 12,
          display: 'flex',
          gap: 12,
          alignItems: 'center',
          overflowX: 'auto',
          paddingBottom: 4,
        }}
      >
        <Input
          placeholder="产品名称/批号"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 220, flexShrink: 0 }}
          value={productKeywordFilter}
          onChange={(e) => setProductKeywordFilter(e.target.value)}
          allowClear
        />
        <Select
          placeholder="是否关闭"
          allowClear
          style={{ width: 120, flexShrink: 0 }}
          value={isClosedFilter || undefined}
          onChange={(value) => setIsClosedFilter((value || '') as '' | 'true' | 'false')}
          options={booleanFilterOptions}
        />
        <Select
          placeholder="是否曾发生"
          allowClear
          style={{ width: 120, flexShrink: 0 }}
          value={hasOccurredBeforeFilter || undefined}
          onChange={(value) => setHasOccurredBeforeFilter((value || '') as '' | 'true' | 'false')}
          options={booleanFilterOptions}
        />
        <Button
          icon={<FilterOutlined />}
          onClick={() => setShowAdvancedFilters((prev) => !prev)}
          style={{ flexShrink: 0 }}
        >
          {showAdvancedFilters ? '收起筛选' : '更多筛选'}
        </Button>
        <Button loading={pulling} onClick={() => void handlePullFromFeishu()} style={{ flexShrink: 0 }}>
          从飞书拉取
        </Button>
        <Button icon={<ReloadOutlined />} onClick={resetAllFilters} style={{ flexShrink: 0 }}>
          重置筛选
        </Button>
        <Button onClick={resetColumnWidths} style={{ flexShrink: 0 }}>
          恢复默认列宽
        </Button>
        <Button icon={<ExportOutlined />} onClick={handleExport} style={{ flexShrink: 0 }}>
          导出Word
        </Button>
        {selectedRowKeys.length > 0 ? (
          <span style={{ color: '#595959', whiteSpace: 'nowrap', flexShrink: 0 }}>
            已勾选 {selectedRowKeys.length} 条
          </span>
        ) : null}
        <div style={{ flex: 1, minWidth: 24 }} />
        <Link href="/quality/deviations/new" style={{ flexShrink: 0 }}>
          <Button type="primary" icon={<PlusOutlined />}>
            新增台账
          </Button>
        </Link>
      </div>
      {showAdvancedFilters ? (
        <div
          style={{
            marginBottom: 12,
            padding: 12,
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            background: '#fafafa',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: 12,
          }}
        >
          <Input
            placeholder="标题/描述关键词"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            allowClear
          />
          <Input
            placeholder="偏差编号"
            value={deviationCodeFilter}
            onChange={(e) => setDeviationCodeFilter(e.target.value)}
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
      <Table<FeishuDeviationLedgerRecordItem>
        columns={columns}
        dataSource={deviations as FeishuDeviationLedgerRecordItem[]}
        rowKey={(record) => record.record_id}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys as string[]),
        }}
        components={{
          header: {
            cell: ResizableHeaderCell,
          },
        }}
        size="small"
        loading={loading}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (value) => `共 ${value} 条`,
          onChange: (newPage, newPageSize) => {
            setPage(newPage)
            setPageSize(newPageSize)
          },
        }}
      />
    </div>
  )
}
