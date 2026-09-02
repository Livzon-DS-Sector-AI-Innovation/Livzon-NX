'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Alert, App, Avatar, Button, Card, Descriptions, Drawer, Form, Input, Modal, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullQualityRecordsFromFeishu } from '@/actions/quality'
import { deleteDeviationReportRecord, updateDeviationReportRecord } from '@/actions/quality-deviation'
import { fetchDepartmentContacts, fetchFeishuDeviationReportRecords, fetchQualityFeishuAppSettings, formatQualitySyncSummary } from '@/lib/api/client/quality'

import type { FeishuDeviationReportRecordItem } from '@/types/quality'
import { buildResizableColumns, ResizableHeaderCell } from './ResizableTableHeader'

const COLUMN_WIDTH_STORAGE_KEY = 'quality-deviation-report-record-table-column-widths-v1'

const defaultColumnWidths: Record<string, number> = {
  deviation_code: 160,
  report_time: 180,
  description: 280,
  product_batch: 220,
  department: 140,
  reporters: 160,
  attachments: 200,
  actions: 220,
}

const minColumnWidths: Record<string, number> = {
  deviation_code: 120,
  report_time: 150,
  description: 220,
  product_batch: 160,
  department: 100,
  reporters: 100,
  attachments: 140,
  actions: 160,
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const y = date.getFullYear()
  const m = `${date.getMonth() + 1}`.padStart(2, '0')
  const d = `${date.getDate()}`.padStart(2, '0')
  const h = `${date.getHours()}`.padStart(2, '0')
  const mi = `${date.getMinutes()}`.padStart(2, '0')
  return `${y}-${m}-${d} ${h}:${mi}`
}

function formatBaseText(value: string | null | undefined): string {
  return value?.trim() || '-'
}

function formatReportStatus(value: string | null | undefined): string {
  if (!value) return '-'
  return value
}

interface EditFormValues {
  description: string
  product_batch: string
  reporter_open_id?: string
}

type ReportPersonItem = { name?: string; avatar_url?: string; id?: string }
type ReportAttachmentItem = { name?: string; url?: string; type?: string; size?: number }

/** 编辑偏差弹窗：独立子组件，仅在打开时挂载，避免 useForm 未连接与 SSR hydration 问题 */
function EditDeviationRecordModal({
  record,
  onClose,
  onSuccess,
}: {
  record: FeishuDeviationReportRecordItem
  onClose: () => void
  onSuccess?: () => void
}) {
  const { message } = App.useApp()
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<EditFormValues>()

  // 编辑弹窗的报告人选项
  const { data: contacts = [], isLoading: contactsLoading } = useQuery({
    queryKey: ['quality-department-contacts', 'for-deviation-report-edit', record.record_id || record.id],
    queryFn: () => fetchDepartmentContacts(),
  })

  const contactOptions = useMemo(
    () =>
      contacts
        .filter((c) => c.name && c.open_id)
        .map((c) => ({ label: c.name, value: c.open_id! })),
    [contacts],
  )

  // 打开时回填（报告人 id 为飞书 open_id，需能在联系人中匹配）
  useEffect(() => {
    const reporterId = record.reporters?.[0]?.id
    const matched = reporterId ? contacts.some((c) => c.open_id === reporterId) : false
    form.setFieldsValue({
      description: record.description || '',
      product_batch: record.product_batch || record.product_name_batch || '',
      reporter_open_id: matched ? reporterId : undefined,
    })
  }, [record, contacts, form])

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await updateDeviationReportRecord(record.record_id || record.id, {
        description: values.description.trim(),
        product_batch: values.product_batch.trim(),
        reporter_open_id: values.reporter_open_id,
      })
      message.success('偏差报告记录已更新')
      onClose()
      onSuccess?.()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(error instanceof Error ? error.message : '更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="编辑偏差"
      open
      onCancel={onClose}
      onOk={() => void handleSave()}
      confirmLoading={submitting}
      okText="保存"
      cancelText="取消"
      width={560}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="description"
          label="偏差内容"
          rules={[{ required: true, message: '请输入偏差内容' }]}
        >
          <Input.TextArea
            rows={4}
            placeholder="请输入偏差内容"
            maxLength={2000}
            showCount
          />
        </Form.Item>
        <Form.Item
          name="product_batch"
          label="涉及产品名称/批号"
          rules={[{ required: true, message: '请输入涉及产品名称/批号' }]}
        >
          <Input placeholder="请输入涉及产品名称/批号" maxLength={255} />
        </Form.Item>
        <Form.Item
          name="reporter_open_id"
          label="报告人"
          rules={[{ required: true, message: '请选择报告人' }]}
        >
          <Select
            placeholder="请选择报告人"
            loading={contactsLoading}
            options={contactOptions}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}

/** 人员列渲染：优先展示人员对象（头像+姓名），无对象时回退到姓名字符串 */
function renderPersons(
  persons: ReportPersonItem[] | null | undefined,
  fallbackName?: string | null,
): ReactNode {
  const list = persons && persons.length > 0 ? persons : fallbackName ? [{ name: fallbackName }] : []
  if (list.length === 0) return <span>-</span>
  return (
    <Space size={4} wrap>
      {list.map((person, index) => (
        <span key={index} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Avatar size={20} src={person.avatar_url || undefined}>
            {person.name?.slice(0, 1) || '?'}
          </Avatar>
          <span>{person.name || '-'}</span>
        </span>
      ))}
    </Space>
  )
}

/** 附件列渲染：附件链接列表，无附件显示 - */
function renderAttachments(attachments: ReportAttachmentItem[] | null | undefined): ReactNode {
  const list = attachments || []
  if (list.length === 0) return <span>-</span>
  return (
    <Space orientation="vertical" size={2}>
      {list.map((attachment, index) => (
        <a key={index} href={attachment.url} target="_blank" rel="noopener noreferrer">
          {attachment.name || attachment.url || '附件'}
        </a>
      ))}
    </Space>
  )
}

export function DeviationReportRecordPage({
  initialItems = [],
  initialLoadError = null,
}: {
  initialItems?: FeishuDeviationReportRecordItem[]
  initialLoadError?: string | null
}) {
  const { message, modal } = App.useApp()
  const router = useRouter()
  const queryClient = useQueryClient()
  const [pulling, setPulling] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [detailRecord, setDetailRecord] = useState<FeishuDeviationReportRecordItem | null>(null)
  const [editRecord, setEditRecord] = useState<FeishuDeviationReportRecordItem | null>(null)
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)

  const { data, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['quality-deviation-report', 'list', page, pageSize],
    queryFn: () => fetchFeishuDeviationReportRecords({ page, page_size: pageSize }),
  })

  const items = data?.items ?? initialItems
  const total = data?.total ?? items.length
  const loadError = error
    ? (error instanceof Error ? error.message : '加载报告记录失败')
    : initialLoadError

  // 读取飞书 App 设置（获取偏差报告新建表单链接）
  const { data: appSettings } = useQuery({
    queryKey: ['quality-feishu-settings', 'app'],
    queryFn: fetchQualityFeishuAppSettings,
  })

  useEffect(() => {
    if (error) {
      const nextError = error instanceof Error ? error.message : '加载报告记录失败'
      message.error(nextError)
    }
  }, [error, message])

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
      const nextWidth = Math.max(
        minColumnWidths[columnKey] ?? 80,
        startWidth + delta,
      )
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

  async function handleOpenAiWorkbench(record: FeishuDeviationReportRecordItem) {
    const recordId = record.record_id?.trim() || record.feishu_base_record_id?.trim() || record.id?.trim()
    if (!recordId) {
      message.warning('当前飞书记录缺少 record_id，暂时无法进入偏差工作台')
      return
    }
    // 进入新的独立偏差工作台页面，并预填该报告记录
    router.push(`/quality/deviations/workbench?record_id=${encodeURIComponent(recordId)}`)
  }

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullQualityRecordsFromFeishu('deviation_report_record')
      message.success(formatQualitySyncSummary(result))
      await queryClient.invalidateQueries({ queryKey: ['quality-deviation-report'] })
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '从飞书拉取失败'
      message.error(nextError)
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  // 新建偏差：跳转到飞书配置的新建表单链接
  const handleCreateNew = useCallback(() => {
    const url = (appSettings?.deviation_report_form_url || '').trim()
    if (!url) {
      message.warning('请在飞书设置中配置新建表单链接')
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
  }, [appSettings, message])

  const handleDeleteRecord = useCallback(
    (record: FeishuDeviationReportRecordItem) => {
      modal.confirm({
        title: '删除确认',
        content: `确定要删除偏差报告记录「${record.deviation_code || record.record_id || record.id}」吗？删除后不可恢复。`,
        okText: '确认',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: async () => {
          try {
            await deleteDeviationReportRecord(record.record_id || record.id)
            message.success('删除成功')
            await queryClient.invalidateQueries({ queryKey: ['quality-deviation-report'] })
          } catch (error) {
            message.error(error instanceof Error ? error.message : '删除失败')
          }
        },
      })
    },
    [modal, message, queryClient],
  )

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
      key: 'reporters',
      width: 160,
      render: (_: unknown, record: FeishuDeviationReportRecordItem) =>
        renderPersons(record.reporters, record.reporter_name),
    },
    {
      title: '附件',
      key: 'attachments',
      width: 200,
      render: (_: unknown, record: FeishuDeviationReportRecordItem) =>
        renderAttachments(record.attachments),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      fixed: 'right',
      render: (_value, record) => (
        <Space size={4}>
          <Button type="link" style={{ padding: 0 }} onClick={() => setDetailRecord(record)}>
            详情
          </Button>
          <Button
            type="link"
            style={{ padding: 0 }}
            onClick={() => setEditRecord(record)}
          >
            编辑
          </Button>
          <Button type="link" danger style={{ padding: 0 }} onClick={() => void handleDeleteRecord(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const columns = useMemo(
    () =>
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
        <Button type="primary" onClick={() => void handleCreateNew()}>新建偏差</Button>
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
              <Button size="small" onClick={() => void refetch()}>
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
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 条`,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              },
            }}
            scroll={{ x: tableScrollX }}
          />
        )}
      </Card>
      <Drawer
        title="报告记录详情"
        open={!!detailRecord}
        onClose={() => setDetailRecord(null)}
        size="large"
        extra={
          detailRecord ? (
            <Button type="primary" onClick={() => void handleOpenAiWorkbench(detailRecord)}>
              进入偏差工作台
            </Button>
          ) : null
        }
      >
        {detailRecord ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="偏差编号">
              {formatBaseText(detailRecord.deviation_code)}
            </Descriptions.Item>
            <Descriptions.Item label="报告时间">
              {formatDateTime(detailRecord.report_time)}
            </Descriptions.Item>
            <Descriptions.Item label="偏差内容">
              {formatBaseText(detailRecord.description)}
            </Descriptions.Item>
            <Descriptions.Item label="涉及产品名称/批号">
              {formatBaseText(detailRecord.product_batch || detailRecord.product_name_batch)}
            </Descriptions.Item>
            <Descriptions.Item label="部门">
              {formatBaseText(detailRecord.department)}
            </Descriptions.Item>
            <Descriptions.Item label="报告人">
              {renderPersons(detailRecord.reporters, detailRecord.reporter_name)}
            </Descriptions.Item>
            <Descriptions.Item label="附件">
              {renderAttachments(detailRecord.attachments)}
            </Descriptions.Item>
            <Descriptions.Item label="部门负责人">
              <Space orientation="vertical" size={2}>
                {renderPersons(detailRecord.department_heads, detailRecord.department_head)}
                <span>确认结果：{formatBaseText(detailRecord.department_head_result)}</span>
                <span>确认时间：{formatDateTime(detailRecord.department_head_reviewed_at)}</span>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="QA">
              <Space orientation="vertical" size={2}>
                {renderPersons(detailRecord.qas, detailRecord.qa_name)}
                <span>确认结果：{formatBaseText(detailRecord.qa_result)}</span>
                <span>确认时间：{formatDateTime(detailRecord.qa_reviewed_at)}</span>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="QA负责人">
              <Space orientation="vertical" size={2}>
                {renderPersons(detailRecord.qa_heads, detailRecord.qa_head_name)}
                <span>确认结果：{formatBaseText(detailRecord.qa_head_result)}</span>
                <span>确认时间：{formatDateTime(detailRecord.qa_head_reviewed_at)}</span>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="报告状态">
              {formatReportStatus(detailRecord.report_status)}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </Drawer>

      {editRecord ? (
        <EditDeviationRecordModal
          record={editRecord}
          onClose={() => setEditRecord(null)}
          onSuccess={() => void queryClient.invalidateQueries({ queryKey: ['quality-deviation-report'] })}
        />
      ) : null}
    </div>
  )
}
