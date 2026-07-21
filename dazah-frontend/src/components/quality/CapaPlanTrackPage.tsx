'use client'

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { App, Button, Checkbox, DatePicker, Form, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import type { ColumnsType } from 'antd/es/table'
import {
  createFeishuCapaPlanTrack,
  deleteFeishuCapaPlanTrack,
  updateFeishuCapaPlanTrack,
} from '@/actions/quality'
import { fetchFeishuCapaPlanTracks } from '@/lib/api/quality'
import type { FeishuCapaPlanTrackItem } from '@/types/quality'
import { buildResizableColumns, ResizableHeaderCell } from './resizable-table-header'

const progressConfig: Record<string, { color?: string; label: string }> = {
  未开始: { color: '#787671', label: '未开始' },
  正在进行: { color: '#1677ff', label: '正在进行' },
  已完成: { color: '#1aae39', label: '已完成' },
}

const reminderStatusConfig: Record<string, { color?: string; label: string }> = {
  未提醒: { color: '#787671', label: '未提醒' },
  已提醒: { color: '#dd5b00', label: '已提醒' },
  已确认: { color: '#1aae39', label: '已确认' },
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  return dayjs(value).format('YYYY-MM-DD')
}

function renderBooleanTag(value: boolean): React.ReactNode {
  return value ? (
    <Tag color="green" style={{ borderRadius: 4 }}>已确认</Tag>
  ) : (
    <Tag style={{ borderRadius: 4 }}>未确认</Tag>
  )
}

function renderProgressTag(value: string | null | undefined): React.ReactNode {
  if (!value) return <Tag style={{ borderRadius: 4 }}>-</Tag>
  const config = progressConfig[value]
  if (!config) return <Tag style={{ borderRadius: 4 }}>{value}</Tag>
  return (
    <Tag
      color={config.color}
      style={{ borderRadius: 4, fontWeight: 500 }}
    >
      {config.label}
    </Tag>
  )
}

function renderReminderTag(value: string | null | undefined): React.ReactNode {
  if (!value) return <Tag style={{ borderRadius: 4 }}>-</Tag>
  const config = reminderStatusConfig[value]
  if (!config) return <Tag style={{ borderRadius: 4 }}>{value}</Tag>
  return (
    <Tag
      color={config.color}
      style={{ borderRadius: 4, fontWeight: 500 }}
    >
      {config.label}
    </Tag>
  )
}

interface PlanTrackFormValues {
  CAPA编号: string
  计划内容: string
  完成时间?: Dayjs | null
  责任人?: string
  责任人确认?: boolean
  部门负责人确认?: boolean
  进度?: string
  提醒状态?: string
}

const COLUMN_WIDTH_STORAGE_KEY = 'quality-capa-plan-track-column-widths-v2'

const defaultColumnWidths: Record<string, number> = {
  CAPA编号: 160,
  计划内容: 460,
  完成时间: 130,
  责任人: 110,
  部门负责人: 120,
  责任人确认: 110,
  部门负责人确认: 130,
  进度: 110,
  提醒状态: 110,
  action: 120,
}

const minColumnWidths: Record<string, number> = {
  CAPA编号: 120,
  计划内容: 300,
  完成时间: 120,
  责任人: 90,
  部门负责人: 100,
  责任人确认: 100,
  部门负责人确认: 110,
  进度: 100,
  提醒状态: 100,
  action: 90,
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function CapaPlanTrackPage() {
  const { message, modal } = App.useApp()
  const [items, setItems] = useState<FeishuCapaPlanTrackItem[]>([])
  const [capaCodeFilter, setCapaCodeFilter] = useState('')
  const [ownerNameFilter, setOwnerNameFilter] = useState('')
  const [progressFilter, setProgressFilter] = useState('')
  const [reminderStatusFilter, setReminderStatusFilter] = useState('')
  const [dueDateRange, setDueDateRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [open, setOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<FeishuCapaPlanTrackItem | null>(null)
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const resizingRef = useRef<{
    columnKey: string
    startX: number
    startWidth: number
  } | null>(null)
  const [form] = Form.useForm<PlanTrackFormValues>()

  const resetFilters = useCallback(() => {
    setCapaCodeFilter('')
    setOwnerNameFilter('')
    setProgressFilter('')
    setReminderStatusFilter('')
    setDueDateRange(null)
  }, [])

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const result = await fetchFeishuCapaPlanTracks({
        keyword: capaCodeFilter || undefined,
        page: 1,
        page_size: 200,
      })
      setItems(result.items)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '加载CAPA计划跟踪失败'))
    } finally {
      setLoading(false)
    }
  }, [capaCodeFilter, message])

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

  // Client-side filtering for additional filters
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (ownerNameFilter && !(item.责任人 || '').includes(ownerNameFilter)) return false
      if (progressFilter && item.进度 !== progressFilter) return false
      if (reminderStatusFilter && item.提醒状态 !== reminderStatusFilter) return false
      if (dueDateRange) {
        const itemDate = item.完成时间 ? dayjs(item.完成时间) : null
        if (!itemDate) return false
        if (itemDate.isBefore(dueDateRange[0], 'day') || itemDate.isAfter(dueDateRange[1], 'day')) return false
      }
      return true
    })
  }, [items, ownerNameFilter, progressFilter, reminderStatusFilter, dueDateRange])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({
      责任人确认: false,
      部门负责人确认: false,
      提醒状态: '未提醒',
    })
    setOpen(true)
  }, [form])

  const openEdit = useCallback((record: FeishuCapaPlanTrackItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      CAPA编号: record.CAPA编号,
      计划内容: record.计划内容 || '',
      完成时间: record.完成时间 ? dayjs(record.完成时间) : null,
      责任人: record.责任人 || undefined,
      责任人确认: record.责任人确认,
      部门负责人确认: record.部门负责人确认,
      进度: record.进度 || undefined,
      提醒状态: record.提醒状态 || undefined,
    })
    setOpen(true)
  }, [form])

  const handleDelete = useCallback((record: FeishuCapaPlanTrackItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除计划跟踪 "${record.计划内容 || record.CAPA编号}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteFeishuCapaPlanTrack(record.record_id)
          message.success('删除成功')
          await loadData()
        } catch (error: any) {
          message.error(error?.message || '删除失败')
        }
      },
    })
  }, [modal, message, loadData])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    const payload: Record<string, unknown> = {
      CAPA编号: values.CAPA编号,
      计划内容: values.计划内容,
      完成时间: values.完成时间 ? values.完成时间.format('YYYY-MM-DD') : null,
      责任人: values.责任人 || null,
      责任人确认: values.责任人确认 ?? false,
      部门负责人确认: values.部门负责人确认 ?? false,
      进度: values.进度 || null,
      提醒状态: values.提醒状态 || '未提醒',
    }
    try {
      setSaving(true)
      if (editingRecord) {
        await updateFeishuCapaPlanTrack(editingRecord.record_id, payload)
        message.success('CAPA计划跟踪已更新')
      } else {
        await createFeishuCapaPlanTrack(payload)
        message.success('CAPA计划跟踪已创建')
      }
      setOpen(false)
      await loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存CAPA计划跟踪失败'))
    } finally {
      setSaving(false)
    }
  }, [editingRecord, form, loadData, message])

  const handleResizeStart = useCallback((columnKey: string, event: ReactMouseEvent<HTMLDivElement>) => {
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
      const nextWidth = Math.max(minColumnWidths[current.columnKey] ?? 80, current.startWidth + delta)
      setColumnWidths((prev) => ({ ...prev, [current.columnKey]: nextWidth }))
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

  const baseColumns: ColumnsType<FeishuCapaPlanTrackItem> = [
    { title: 'CAPA编号', dataIndex: 'CAPA编号', key: 'CAPA编号', width: defaultColumnWidths.CAPA编号, fixed: 'left' },
    {
      title: '计划内容',
      dataIndex: '计划内容',
      key: '计划内容',
      width: defaultColumnWidths.计划内容,
      render: (value: string | null) => (
        <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.6 }}>
          {value || '-'}
        </div>
      ),
    },
    {
      title: '完成时间',
      dataIndex: '完成时间',
      key: '完成时间',
      width: defaultColumnWidths.完成时间,
      render: (v: string | null) => formatDate(v),
    },
    {
      title: '责任人',
      dataIndex: '责任人',
      key: '责任人',
      width: defaultColumnWidths.责任人,
      render: (v: string | null) => v || '-',
    },
    {
      title: '部门负责人',
      key: '部门负责人',
      width: defaultColumnWidths.部门负责人,
      render: (_: unknown, record: FeishuCapaPlanTrackItem) => (record as FeishuCapaPlanTrackItem & { 部门负责人?: string | null }).部门负责人 || '-',
    },
    {
      title: '完成前一周提醒',
      key: '完成前一周提醒',
      children: [
        {
          title: '责任人确认',
          dataIndex: '责任人确认',
          key: '责任人确认',
          width: defaultColumnWidths.责任人确认,
          render: (v: boolean) => renderBooleanTag(v),
        },
        {
          title: '部门负责人确认',
          dataIndex: '部门负责人确认',
          key: '部门负责人确认',
          width: defaultColumnWidths.部门负责人确认,
          render: (v: boolean) => renderBooleanTag(v),
        },
      ],
    },
    {
      title: '进度',
      dataIndex: '进度',
      key: '进度',
      width: defaultColumnWidths.进度,
      render: (v: string | null) => renderProgressTag(v),
    },
    {
      title: '提醒状态',
      dataIndex: '提醒状态',
      key: '提醒状态',
      width: defaultColumnWidths.提醒状态,
      render: (v: string | null) => renderReminderTag(v),
    },
    {
      title: '操作',
      key: 'action',
      width: defaultColumnWidths.action,
      fixed: 'right',
      render: (_: unknown, record: FeishuCapaPlanTrackItem) => (
        <Space size="small">
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            修改
          </Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)}>
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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / CAPA管理 / 计划跟踪</p>
          <Typography.Title level={3} style={{ margin: 0 }}>CAPA计划跟踪</Typography.Title>
        </div>
        <Button type="primary" onClick={openCreate}>新增计划跟踪</Button>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="CAPA编号"
          style={{ width: 180 }}
          value={capaCodeFilter}
          onChange={(e) => setCapaCodeFilter(e.target.value)}
          allowClear
        />
        <Input
          placeholder="责任人"
          style={{ width: 160 }}
          value={ownerNameFilter}
          onChange={(e) => setOwnerNameFilter(e.target.value)}
          allowClear
        />
        <Select
          placeholder="进度"
          allowClear
          style={{ width: 140 }}
          value={progressFilter || undefined}
          onChange={(value) => setProgressFilter(value || '')}
          options={[
            { value: '未开始', label: '未开始' },
            { value: '正在进行', label: '正在进行' },
            { value: '已完成', label: '已完成' },
          ]}
        />
        <Select
          placeholder="提醒状态"
          allowClear
          style={{ width: 140 }}
          value={reminderStatusFilter || undefined}
          onChange={(value) => setReminderStatusFilter(value || '')}
          options={[
            { value: '未提醒', label: '未提醒' },
            { value: '已提醒', label: '已提醒' },
            { value: '已确认', label: '已确认' },
          ]}
        />
        <DatePicker.RangePicker
          placeholder={['完成时间开始', '完成时间结束']}
          value={dueDateRange}
          onChange={(dates) => setDueDateRange((dates as [Dayjs, Dayjs] | null) || null)}
        />
        <Button onClick={resetFilters}>重置筛选</Button>
      </Space>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadData()}>从飞书拉取</Button>
        <Button onClick={resetColumnWidths}>恢复默认列宽</Button>
      </Space>
      <Table<FeishuCapaPlanTrackItem>
        rowKey="record_id"
        loading={loading}
        columns={columns}
        dataSource={filteredItems}
        components={{
          header: {
            cell: ResizableHeaderCell,
          },
        }}
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
      />
      <Modal
        title={editingRecord ? '修改CAPA计划跟踪' : '新增CAPA计划跟踪'}
        open={open}
        onOk={() => void handleSubmit()}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="CAPA编号" label="CAPA编号" rules={[{ required: true, message: '请输入CAPA编号' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="计划内容" label="计划内容" rules={[{ required: true, message: '请输入计划内容' }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="完成时间" label="完成时间">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="责任人" label="责任人">
            <Input />
          </Form.Item>
          <Form.Item name="责任人确认" valuePropName="checked">
            <Checkbox>责任人已确认</Checkbox>
          </Form.Item>
          <Form.Item name="部门负责人确认" valuePropName="checked">
            <Checkbox>部门负责人已确认</Checkbox>
          </Form.Item>
          <Form.Item name="进度" label="进度">
            <Select
              allowClear
              options={[
                { value: '未开始', label: '未开始' },
                { value: '正在进行', label: '正在进行' },
                { value: '已完成', label: '已完成' },
              ]}
            />
          </Form.Item>
          <Form.Item name="提醒状态" label="提醒状态">
            <Select
              options={[
                { value: '未提醒', label: '未提醒' },
                { value: '已提醒', label: '已提醒' },
                { value: '已确认', label: '已确认' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
