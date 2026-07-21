'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App, Table, Tag, Space, Button, Input, Modal, Form, DatePicker, Select } from 'antd'
import { EditOutlined, DeleteOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import type { DepartmentContact, FeishuCapaLedgerItem } from '@/types/quality'
import { useCapaStore } from '@/stores/quality'
import { deleteFeishuCapa, updateFeishuCapa } from '@/actions/quality'
import { fetchDepartmentContacts } from '@/lib/api/quality'
import { buildResizableColumns, ResizableHeaderCell } from './resizable-table-header'
import dayjs, { type Dayjs } from 'dayjs'

const statusConfig: Record<string, { label: string }> = {
  进行中: { label: '进行中' },
  已完成: { label: '已完成' },
  已关闭: { label: '已关闭' },
}

const statusOptions = [
  { value: '进行中', label: '进行中' },
  { value: '已完成', label: '已完成' },
  { value: '已关闭', label: '已关闭' },
]

interface CapaTableProps {
  loading?: boolean
  onRefresh?: () => void
}

interface CapaEditFormValues {
  CAPA编号: string
  启动日期?: Dayjs | null
  事件部门?: string
  涉及产品?: string
  CAPA简述?: string
  CAPA效果评估?: string
  关闭日期?: Dayjs | null
  QA质量员?: string
  QA质量员确认日期?: Dayjs | null
  CAPA状态?: string
}

const COLUMN_WIDTH_STORAGE_KEY = 'quality-capa-table-column-widths-v3'

const defaultColumnWidths: Record<string, number> = {
  CAPA编号: 150,
  启动日期: 130,
  事件部门: 110,
  涉及产品: 150,
  CAPA简述: 420,
  CAPA效果评估: 120,
  关闭日期: 120,
  qa_info: 150,
  CAPA状态: 120,
  action: 100,
}

const minColumnWidths: Record<string, number> = {
  CAPA编号: 120,
  启动日期: 110,
  事件部门: 90,
  涉及产品: 120,
  CAPA简述: 260,
  CAPA效果评估: 100,
  关闭日期: 110,
  qa_info: 120,
  CAPA状态: 100,
  action: 80,
}

function formatDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v)
  if (isNaN(d.getTime())) return v
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export function CapaTable({ loading = false, onRefresh }: CapaTableProps) {
  const { message, modal } = App.useApp()
  const [editOpen, setEditOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<FeishuCapaLedgerItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [editForm] = Form.useForm<CapaEditFormValues>()
  const [qaContacts, setQaContacts] = useState<DepartmentContact[]>([])
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const resizingRef = useRef<{
    columnKey: string
    startX: number
    startWidth: number
  } | null>(null)
  const {
    capas,
    total,
    page,
    pageSize,
    keyword,
    departmentFilter,
    productFilter,
    statusFilter,
    setKeyword,
    setDepartmentFilter,
    setProductFilter,
    setStatusFilter,
    setPage,
    setPageSize,
  } = useCapaStore()

  // Client-side filtering
  const filteredCapas = useMemo(() => {
    return capas.filter(item => {
      if (keyword && !(item.CAPA编号 || '').toLowerCase().includes(keyword.toLowerCase())) return false
      if (departmentFilter && (item.事件部门 || '') !== departmentFilter) return false
      if (productFilter && !(item.涉及产品 || '').includes(productFilter)) return false
      if (statusFilter && (item.CAPA状态 || '') !== statusFilter) return false
      return true
    })
  }, [capas, keyword, departmentFilter, productFilter, statusFilter])

  const filteredTotal = filteredCapas.length

  const qaOptions = useMemo(() =>
    qaContacts
      .filter(c => c.department === 'QA')
      .map(c => ({ label: c.name ?? '', value: c.name ?? '' })),
    [qaContacts],
  )

  useEffect(() => {
    fetchDepartmentContacts().then(setQaContacts)
  }, [])

  const handleDelete = useCallback((record: FeishuCapaLedgerItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除CAPA "${record.CAPA编号}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteFeishuCapa(record.record_id)
          message.success('删除成功')
          onRefresh?.()
        } catch (error: any) {
          message.error(error?.message || '删除失败')
        }
      },
    })
  }, [modal, message, onRefresh])

  const openEdit = useCallback((record: FeishuCapaLedgerItem) => {
    setEditingRecord(record)
    editForm.setFieldsValue({
      CAPA编号: record.CAPA编号,
      启动日期: record.启动日期 ? dayjs(record.启动日期) : null,
      事件部门: record.事件部门 || undefined,
      涉及产品: record.涉及产品 || undefined,
      CAPA简述: record.CAPA简述 || undefined,
      CAPA效果评估: record.CAPA效果评估 || undefined,
      关闭日期: record.关闭日期 ? dayjs(record.关闭日期) : null,
      QA质量员: record.QA质量员 || undefined,
      QA质量员确认日期: record.QA质量员确认日期 ? dayjs(record.QA质量员确认日期) : null,
      CAPA状态: record.CAPA状态 || undefined,
    })
    setEditOpen(true)
  }, [editForm])

  const handleEditSubmit = useCallback(async () => {
    const values = await editForm.validateFields()
    if (!editingRecord) return
    const payload: Record<string, unknown> = {
      CAPA编号: values.CAPA编号,
      启动日期: values.启动日期 ? values.启动日期.format('YYYY-MM-DD') : null,
      事件部门: values.事件部门 || null,
      涉及产品: values.涉及产品 || null,
      CAPA简述: values.CAPA简述 || null,
      CAPA效果评估: values.CAPA效果评估 || null,
      关闭日期: values.关闭日期 ? values.关闭日期.format('YYYY-MM-DD') : null,
      QA质量员: values.QA质量员 || null,
      QA质量员确认日期: values.QA质量员确认日期 ? values.QA质量员确认日期.format('YYYY-MM-DD') : null,
      CAPA状态: values.CAPA状态 || null,
    }
    try {
      setSaving(true)
      await updateFeishuCapa(editingRecord.record_id, payload)
      message.success('CAPA更新成功')
      setEditOpen(false)
      onRefresh?.()
    } catch (error: any) {
      message.error(error?.message || '更新CAPA失败')
    } finally {
      setSaving(false)
    }
  }, [editForm, editingRecord, message, onRefresh])

  // Column resize logic
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

  const baseColumns = [
    {
      title: 'CAPA编号',
      dataIndex: 'CAPA编号',
      key: 'CAPA编号',
      width: defaultColumnWidths.CAPA编号,
      fixed: 'start' as const,
    },
    {
      title: '启动日期',
      dataIndex: '启动日期',
      key: '启动日期',
      width: defaultColumnWidths.启动日期,
      render: (v: string | null) => formatDate(v),
    },
    {
      title: '事件部门',
      dataIndex: '事件部门',
      key: '事件部门',
      width: defaultColumnWidths.事件部门,
      render: (v: string | null) => v || '-',
    },
    {
      title: '涉及产品',
      dataIndex: '涉及产品',
      key: '涉及产品',
      width: defaultColumnWidths.涉及产品,
      render: (v: string | null) => v || '-',
    },
    {
      title: 'CAPA简述',
      dataIndex: 'CAPA简述',
      key: 'CAPA简述',
      width: defaultColumnWidths.CAPA简述,
      render: (text: string | null) => (
        <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.5 }}>
          {text || '-'}
        </div>
      ),
    },
    {
      title: 'CAPA效果评估',
      dataIndex: 'CAPA效果评估',
      key: 'CAPA效果评估',
      width: defaultColumnWidths.CAPA效果评估,
      render: (v: string | null) => {
        if (!v) return '-'
        const isEffective = v === '有效' || v.includes('有效')
        return (
          <Tag color={isEffective ? 'green' : 'default'} style={{ borderRadius: 4, fontWeight: 500 }}>
            {v}
          </Tag>
        )
      },
    },
    {
      title: '关闭日期',
      dataIndex: '关闭日期',
      key: '关闭日期',
      width: defaultColumnWidths.关闭日期,
      render: (v: string | null) => formatDate(v),
    },
    {
      title: 'QA质量员/日期',
      key: 'qa_info',
      width: defaultColumnWidths.qa_info,
      render: (_: unknown, record: FeishuCapaLedgerItem) => {
        const qaName = record.QA质量员?.trim() || ''
        const qaConfirmDate = record.QA质量员确认日期 || null
        if (!qaName && !qaConfirmDate) return '-'
        return (
          <div style={{ lineHeight: 1.5 }}>
            {qaName ? <div>{qaName}</div> : null}
            {qaConfirmDate ? (
              <div style={{ color: '#999', fontSize: 12 }}>
                {formatDate(qaConfirmDate)}
              </div>
            ) : null}
          </div>
        )
      },
    },
    {
      title: 'CAPA状态',
      dataIndex: 'CAPA状态',
      key: 'CAPA状态',
      width: defaultColumnWidths.CAPA状态,
      render: (value: string | null) => {
        const config = statusConfig[value || ''] || { label: value || '-' }
        if (value === '已完成') {
          return <Tag color="blue" style={{ borderRadius: 4, fontWeight: 500 }}>{config.label}</Tag>
        }
        if (value === '已关闭') {
          return <Tag color="green" style={{ borderRadius: 4, fontWeight: 500 }}>{config.label}</Tag>
        }
        if (value === '进行中') {
          return <Tag color="orange" style={{ borderRadius: 4, fontWeight: 500 }}>{config.label}</Tag>
        }
        return <Tag style={{ borderRadius: 4 }}>{config.label}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: defaultColumnWidths.action,
      fixed: 'end' as const,
      render: (_: unknown, record: FeishuCapaLedgerItem) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
            style={{ padding: 0 }}
          >
            修改
          </Button>
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
      <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input
          placeholder="CAPA编号搜索"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 200 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          allowClear
        />
        <Input
          placeholder="事件部门"
          style={{ width: 140 }}
          value={departmentFilter}
          onChange={(e) => setDepartmentFilter(e.target.value)}
          allowClear
        />
        <Input
          placeholder="涉及产品"
          style={{ width: 160 }}
          value={productFilter}
          onChange={(e) => setProductFilter(e.target.value)}
          allowClear
        />
        <Select
          placeholder="CAPA状态"
          allowClear
          style={{ width: 130 }}
          value={statusFilter || undefined}
          onChange={(value) => setStatusFilter(value || '')}
          options={statusOptions}
        />
        <div style={{ flex: 1 }} />
        <Button onClick={resetColumnWidths}>
          恢复默认列宽
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={filteredCapas}
        rowKey="record_id"
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
          pageSize: pageSize,
          total: filteredTotal,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (value) => `共 ${value} 条`,
          onChange: (newPage, newPageSize) => {
            setPage(newPage)
            setPageSize(newPageSize)
          },
        }}
      />
      <Modal
        title="修改CAPA"
        open={editOpen}
        onOk={() => void handleEditSubmit()}
        onCancel={() => setEditOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
        width={640}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="CAPA编号" label="CAPA编号" rules={[{ required: true, message: '请输入CAPA编号' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="启动日期" label="启动日期">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="事件部门" label="事件部门">
            <Input />
          </Form.Item>
          <Form.Item name="涉及产品" label="涉及产品">
            <Input />
          </Form.Item>
          <Form.Item name="CAPA简述" label="CAPA简述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="CAPA效果评估" label="CAPA效果评估">
            <Input />
          </Form.Item>
          <Form.Item name="关闭日期" label="关闭日期">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="QA质量员" label="QA质量员">
            <Select showSearch allowClear placeholder="选择QA质量员" options={qaOptions} />
          </Form.Item>
          <Form.Item name="QA质量员确认日期" label="QA质量员确认日期">
            <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item name="CAPA状态" label="CAPA状态">
            <Select options={statusOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
