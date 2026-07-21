'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dayjs from 'dayjs'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Alert, App, Button, Card, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { ensureDeviationFromReportRecord, pullQualityRecordsFromFeishu } from '@/actions/quality'
import { fetchFeishuDeviationReportRecords, formatQualitySyncSummary } from '@/lib/api/quality'
import type { FeishuDeviationReportRecordItem } from '@/types/quality'
import { buildResizableColumns, ResizableHeaderCell } from './resizable-table-header'

const COLUMN_WIDTH_STORAGE_KEY = 'quality-deviation-report-record-table-column-widths-v1'

const defaultColumnWidths: Record<string, number> = {
  deviation_code: 160,
  report_time: 180,
  description: 280,
  product_batch: 220,
  department: 140,
  reporter_name: 120,
  department_head: 140,
  department_head_result: 140,
  department_head_reviewed_at: 180,
  qa_name: 120,
  qa_result: 120,
  qa_reviewed_at: 180,
  qa_head_name: 120,
  qa_head_result: 140,
  qa_head_reviewed_at: 180,
  report_status: 140,
  actions: 180,
}

const minColumnWidths: Record<string, number> = {
  deviation_code: 120,
  report_time: 150,
  description: 220,
  product_batch: 160,
  department: 100,
  reporter_name: 100,
  department_head: 120,
  department_head_result: 120,
  department_head_reviewed_at: 150,
  qa_name: 100,
  qa_result: 100,
  qa_reviewed_at: 150,
  qa_head_name: 100,
  qa_head_result: 120,
  qa_head_reviewed_at: 150,
  report_status: 120,
  actions: 140,
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm:ss') : value
}

function formatBaseText(value: string | null | undefined): string {
  return value?.trim() || '-'
}

function formatApprovalResult(value: string | null | undefined): string {
  if (!value) return '-'
  if (value === 'approved') return '已确认'
  if (value === 'rejected') return '已拒绝'
  if (value === 'resubmitted') return '已退回'
  return value
}

function formatReportStatus(value: string | null | undefined): string {
  if (!value) return '-'
  if (value === 'approved') return 'QA负责人已确认'
  if (value === 'rejected') return '审核驳回'
  if (value === 'resubmitted') return '待重新提交'
  return value
}

export function DeviationReportRecordPage({
  initialItems = [],
  initialLoadError = null,
}: {
  initialItems?: FeishuDeviationReportRecordItem[]
  initialLoadError?: string | null
}) {
  const { message } = App.useApp()
  const router = useRouter()
  const [items, setItems] = useState<FeishuDeviationReportRecordItem[]>(initialItems)
  const [loading, setLoading] = useState(initialItems.length === 0 && !initialLoadError)
  const [loadError, setLoadError] = useState<string | null>(initialLoadError)
  const [openingAiRecordId, setOpeningAiRecordId] = useState<string | null>(null)
  const [pulling, setPulling] = useState(false)
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const resizingRef = useRef<{
    columnKey: string
    startX: number
    startWidth: number
  } | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      setLoadError(null)
      const result = await fetchFeishuDeviationReportRecords({ page: 1, page_size: 50 })
      setItems(result.items)
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '加载报告记录失败'
      setLoadError(nextError)
      setItems([])
      message.error(nextError)
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void loadData()
  }, [loadData])

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

  async function handleOpenAiWorkbench(record: FeishuDeviationReportRecordItem) {
    const recordId = record.record_id?.trim() || record.feishu_base_record_id?.trim() || record.id?.trim()
    if (!recordId) {
      message.warning('当前飞书记录缺少 record_id，暂时无法进入 AI 工作台')
      return
    }

    try {
      setOpeningAiRecordId(recordId)
      const ensured = await ensureDeviationFromReportRecord(recordId)
      if (!ensured?.deviation_id) {
        throw new Error('报告记录关联偏差失败，未返回偏差标识')
      }
      await loadData()
      router.push(`/quality/deviations/${ensured.deviation_id}/ai`)
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '打开 AI 工作台失败'
      message.error(nextError)
    } finally {
      setOpeningAiRecordId(null)
    }
  }

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullQualityRecordsFromFeishu('deviation_report_record')
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      await loadData()
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '从飞书拉取失败'
      message.error(nextError)
    } finally {
      setPulling(false)
    }
  }, [loadData, message])

  const baseColumns: ColumnsType<FeishuDeviationReportRecordItem> = [
    {
      title: '偏差编号',
      dataIndex: 'deviation_code',
      key: 'deviation_code',
      width: 160,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: '报告时间',
      dataIndex: 'report_time',
      key: 'report_time',
      width: 180,
      render: (value: string | null | undefined) => formatDateTime(value),
    },
    {
      title: '偏差内容',
      dataIndex: 'description',
      key: 'description',
      width: 280,
      render: (value: string | null) => formatBaseText(value),
    },
    {
      title: '涉及产品名称/批号',
      dataIndex: 'product_batch',
      key: 'product_batch',
      width: 220,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: '部门',
      dataIndex: 'department',
      key: 'department',
      width: 140,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: '报告人',
      dataIndex: 'reporter_name',
      key: 'reporter_name',
      width: 120,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: '部门负责人',
      dataIndex: 'department_head',
      key: 'department_head',
      width: 140,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: '部门负责人确认',
      dataIndex: 'department_head_result',
      key: 'department_head_result',
      width: 140,
      render: (value: string | null | undefined) => formatApprovalResult(value),
    },
    {
      title: '部门负责人确认时间',
      dataIndex: 'department_head_reviewed_at',
      key: 'department_head_reviewed_at',
      width: 180,
      render: (value: string | null | undefined) => formatDateTime(value),
    },
    {
      title: 'QA',
      dataIndex: 'qa_name',
      key: 'qa_name',
      width: 120,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: 'QA确认',
      dataIndex: 'qa_result',
      key: 'qa_result',
      width: 120,
      render: (value: string | null | undefined) => formatApprovalResult(value),
    },
    {
      title: 'QA确认时间',
      dataIndex: 'qa_reviewed_at',
      key: 'qa_reviewed_at',
      width: 180,
      render: (value: string | null | undefined) => formatDateTime(value),
    },
    {
      title: 'QA负责人',
      dataIndex: 'qa_head_name',
      key: 'qa_head_name',
      width: 140,
      render: (value: string | null | undefined) => formatBaseText(value),
    },
    {
      title: 'QA负责人确认',
      dataIndex: 'qa_head_result',
      key: 'qa_head_result',
      width: 140,
      render: (value: string | null | undefined) => formatApprovalResult(value),
    },
    {
      title: 'QA负责人确认时间',
      dataIndex: 'qa_head_reviewed_at',
      key: 'qa_head_reviewed_at',
      width: 180,
      render: (value: string | null | undefined) => formatDateTime(value),
    },
    {
      title: '报告状态',
      dataIndex: 'report_status',
      key: 'report_status',
      width: 140,
      render: (value: string | null | undefined) => formatReportStatus(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      fixed: 'right',
      render: (_value, record) => (
        <Button
          type="link"
          style={{ padding: 0 }}
          loading={openingAiRecordId === (record.record_id || record.id)}
          onClick={() => void handleOpenAiWorkbench(record)}
        >
          进入 AI 工作台
        </Button>
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

  const tableScrollX = useMemo(
    () => columns.reduce((sum, column) => sum + (typeof column.width === 'number' ? column.width : 0), 0),
    [columns],
  )

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 偏差管理 / 报告记录</p>
        <Typography.Title level={3} style={{ margin: 0 }}>报告记录</Typography.Title>
      </div>
      <Space style={{ marginBottom: 16 }}>
        <Link href="/quality/deviations/new"><Button type="primary">新建偏差</Button></Link>
        <Button icon={<ReloadOutlined />} loading={pulling} onClick={() => void handlePullFromFeishu()}>
          从飞书拉取
        </Button>
        <Link href="/quality/deviations/ledger"><Button>查看偏差台账</Button></Link>
        <Button icon={<ReloadOutlined />} onClick={resetColumnWidths}>恢复默认列宽</Button>
      </Space>
      <Card>
        {loadError ? (
          <Alert
            type="error"
            showIcon
            action={(
              <Button size="small" onClick={() => void loadData()}>
                重试加载
              </Button>
            )}
            message="报告记录加载失败"
            description={loadError}
          />
        ) : (
          <Table<FeishuDeviationReportRecordItem>
            components={{
              header: {
                cell: ResizableHeaderCell,
              },
            }}
            rowKey={(record) => record.record_id || record.id}
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: tableScrollX }}
          />
        )}
      </Card>
    </div>
  )
}
