'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState, useTransition } from 'react'
import {
  App,
  Breadcrumb,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'

import {
  createCertificateEntry,
  deleteCertificateEntry,
  updateCertificateEntry,
} from '@/actions/registration'
import { ResizableHeaderCell } from '@/components/quality'
import {
  type RegistrationCertificateFieldConfig,
  type RegistrationCertificateFieldKey,
  registrationCertificatePageLayouts,
  registrationCertificateSheetFields,
} from '@/lib/registration-certificate'
import type { CertificateEntryInput, CertificateSheetDetail } from '@/types/registration'

interface CertificateSheetPageProps {
  detail: CertificateSheetDetail
}

const COLUMN_WIDTH_STORAGE_KEY_PREFIX = 'registration-certificate-column-widths'

type CertificateFormValues = Partial<
  Record<RegistrationCertificateFieldKey, string | number | undefined>
> & {
  sheet_key?: string
}

function getColumnWidthStorageKey(sheetKey: string): string {
  return `${COLUMN_WIDTH_STORAGE_KEY_PREFIX}:${sheetKey}`
}

function readStoredColumnWidths(sheetKey: string): Record<string, number> {
  if (typeof window === 'undefined') {
    return {}
  }

  try {
    const rawValue = window.localStorage.getItem(getColumnWidthStorageKey(sheetKey))
    if (!rawValue) {
      return {}
    }

    const parsed = JSON.parse(rawValue) as Record<string, unknown>
    return Object.entries(parsed).reduce<Record<string, number>>((acc, [key, value]) => {
      if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
        acc[key] = value
      }
      return acc
    }, {})
  } catch {
    return {}
  }
}

function persistColumnWidths(sheetKey: string, widths: Record<string, number>) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(getColumnWidthStorageKey(sheetKey), JSON.stringify(widths))
}

function toOptionalString(value: string | number | undefined): string | null {
  if (value === undefined || value === null || value === '') {
    return null
  }
  return String(value)
}

function toRequiredString(value: string | number | undefined): string {
  return String(value || '').trim()
}

const documentTableHeaderStyle = {
  borderBottom: '1px solid #f0f0f0',
  textAlign: 'center' as const,
  verticalAlign: 'middle' as const,
  padding: '10px 8px',
  fontWeight: 600,
  fontSize: 14,
  lineHeight: 1.75,
  background: '#fff',
}

const documentTableCellStyle = {
  borderBottom: '1px solid #f0f0f0',
  textAlign: 'center' as const,
  verticalAlign: 'middle' as const,
  padding: '10px 8px',
  fontSize: 14,
  lineHeight: 1.75,
  whiteSpace: 'pre-wrap' as const,
  wordBreak: 'break-word' as const,
  overflowWrap: 'anywhere' as const,
  background: '#fff',
}

export default function CertificateSheetPage({
  detail,
}: CertificateSheetPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm<CertificateFormValues>()
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRowId, setEditingRowId] = useState<string | null>(null)
  const [pending, startTransition] = useTransition()
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})

  const fieldConfigs =
    registrationCertificateSheetFields[
      detail.sheet_key as keyof typeof registrationCertificateSheetFields
    ] || []
  const pageLayout =
    registrationCertificatePageLayouts[
      detail.sheet_key as keyof typeof registrationCertificatePageLayouts
    ]

  useEffect(() => {
    if (!detail.rows.length) {
      setSelectedRowId(null)
      return
    }

    setSelectedRowId((prev) =>
      prev && detail.rows.some((row) => row.id === prev) ? prev : detail.rows[0].id
    )
  }, [detail.rows])

  const selectedRow = useMemo(
    () => detail.rows.find((row) => row.id === selectedRowId) || null,
    [detail.rows, selectedRowId]
  )

  const documentColumns = useMemo(() => {
    if (pageLayout) {
      return pageLayout.columns.filter((column) => column.type !== 'blank')
    }

    return [
      { key: 'sequence', label: '序号', width: 72, type: 'sequence' as const },
      ...detail.columns.map((column) => ({
        key: column.key,
        label: column.label,
        width: 180,
        type: 'field' as const,
      })),
    ]
  }, [detail.columns, pageLayout])

  useEffect(() => {
    const storedWidths = readStoredColumnWidths(detail.sheet_key)
    setColumnWidths(() => {
      const next: Record<string, number> = {}
      for (const column of documentColumns) {
        next[column.key] = storedWidths[column.key] ?? column.width
      }
      return next
    })
  }, [detail.sheet_key, documentColumns])

  useEffect(() => {
    if (!Object.keys(columnWidths).length) {
      return
    }
    persistColumnWidths(detail.sheet_key, columnWidths)
  }, [columnWidths, detail.sheet_key])

  const minColumnWidths = useMemo<Record<string, number>>(
    () =>
      documentColumns.reduce<Record<string, number>>((acc, column) => {
        acc[column.key] = column.type === 'sequence' ? 72 : 120
        return acc
      }, {}),
    [documentColumns]
  )

  const handleResizeStart = useCallback(
    (columnKey: string, event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.stopPropagation()

      const startX = event.clientX
      const startWidth = columnWidths[columnKey] ?? 160
      const minWidth = minColumnWidths[columnKey] ?? 120

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const nextWidth = Math.max(minWidth, startWidth + moveEvent.clientX - startX)
        setColumnWidths((prev) => ({
          ...prev,
          [columnKey]: nextWidth,
        }))
      }

      const handleMouseUp = () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }

      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    },
    [columnWidths, minColumnWidths]
  )

  const totalColumnWidth = useMemo(
    () =>
      documentColumns.reduce(
        (total, column) => total + (columnWidths[column.key] ?? column.width),
        0
      ),
    [columnWidths, documentColumns]
  )

  const tableColumns = useMemo<ColumnsType<CertificateSheetDetail['rows'][number]>>(
    () =>
      documentColumns.map((column) => {
        const width = columnWidths[column.key] ?? column.width
        const minWidth = minColumnWidths[column.key] ?? 120

        if (column.type === 'sequence') {
          return {
            title: column.label,
            key: column.key,
            dataIndex: 'sequence',
            width,
            align: 'center' as const,
            onHeaderCell: () => ({
              width,
              minWidth,
              style: documentTableHeaderStyle,
              resizable: true,
              onResizeStart: (event: React.MouseEvent<HTMLDivElement>) =>
                handleResizeStart(column.key, event),
            }),
            onCell: () => ({ style: documentTableCellStyle }),
          }
        }

        return {
          title: column.label,
          key: column.key,
          width,
          align: 'center' as const,
          onHeaderCell: () => ({
            width,
            minWidth,
            style: documentTableHeaderStyle,
            resizable: true,
            onResizeStart: (event: React.MouseEvent<HTMLDivElement>) =>
              handleResizeStart(column.key, event),
          }),
          onCell: () => ({ style: documentTableCellStyle }),
          render: (_: unknown, row: CertificateSheetDetail['rows'][number]) =>
            row.values[column.label] ?? '',
        }
      }),
    [columnWidths, documentColumns, handleResizeStart, minColumnWidths]
  )

  function openCreateModal() {
    setEditingRowId(null)
    form.resetFields()
    form.setFieldsValue({ sheet_key: detail.sheet_key })
    setModalOpen(true)
  }

  function openEditModal() {
    if (!selectedRow) {
      message.warning('请先在台账中选择一条记录')
      return
    }

    setEditingRowId(selectedRow.id)
    const nextValues: CertificateFormValues = {
      sheet_key: detail.sheet_key,
    }
    for (const field of fieldConfigs) {
      const rawValue = selectedRow.values[field.label]
      if (field.numeric) {
        nextValues[field.key] = rawValue ? Number(rawValue) : undefined
      } else {
        nextValues[field.key] = rawValue || undefined
      }
    }
    form.setFieldsValue(nextValues)
    setModalOpen(true)
  }

  async function handleSubmit(values: CertificateFormValues) {
    const payload: CertificateEntryInput = {
      sheet_key: detail.sheet_key,
      certificate_name: toRequiredString(values.certificate_name),
      acceptance_number: toOptionalString(values.acceptance_number),
      approval_number: toOptionalString(values.approval_number),
      certificate_number: toOptionalString(values.certificate_number),
      issuing_authority: toOptionalString(values.issuing_authority),
      issue_date: toOptionalString(values.issue_date),
      validity_period: toOptionalString(values.validity_period),
      product_scope: toOptionalString(values.product_scope),
      quality_standard: toOptionalString(values.quality_standard),
      page_count:
        values.page_count === undefined || values.page_count === null || values.page_count === ''
          ? null
          : Number(values.page_count),
      remarks: toOptionalString(values.remarks),
    }

    startTransition(async () => {
      try {
        if (editingRowId) {
          await updateCertificateEntry(editingRowId, detail.sheet_key, payload)
          message.success('证书记录已更新')
        } else {
          await createCertificateEntry(payload)
          message.success('证书记录已新增')
        }
        setModalOpen(false)
        form.resetFields()
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '操作失败')
      }
    })
  }

  function handleDelete() {
    if (!selectedRow) {
      message.warning('请先在台账中选择一条记录')
      return
    }

    startTransition(async () => {
      try {
        await deleteCertificateEntry(selectedRow.id, detail.sheet_key)
        message.success('证书记录已删除')
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    })
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Breadcrumb
        items={[
          { title: <Link href="/registration/certificate-management">证书管理</Link> },
          { title: detail.sheet_name },
        ]}
      />

      <Card
        title={
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space>
              <Typography.Text strong>{detail.sheet_name}</Typography.Text>
              <Tag color="purple">{detail.summary.total_records} 条记录</Tag>
            </Space>
            <Space wrap>
              <Button icon={<PlusOutlined />} type="primary" onClick={openCreateModal}>
                新增
              </Button>
              <Button icon={<EditOutlined />} disabled={!selectedRow} onClick={openEditModal}>
                编辑选中
              </Button>
              <Popconfirm
                title="确认删除选中的证书记录吗？"
                okText="删除"
                cancelText="取消"
                onConfirm={handleDelete}
                disabled={!selectedRow}
              >
                <Button danger icon={<DeleteOutlined />} disabled={!selectedRow}>
                  删除选中
                </Button>
              </Popconfirm>
            </Space>
          </Space>
        }
        styles={{ body: { padding: 12 } }}
      >
        <Table<CertificateSheetDetail['rows'][number]>
          rowKey="id"
          columns={tableColumns}
          dataSource={detail.rows}
          components={{ header: { cell: ResizableHeaderCell } }}
          pagination={false}
          size="middle"
          tableLayout="fixed"
          locale={{ emptyText: '暂无台账数据' }}
          style={{ fontSize: 14, lineHeight: 1.75, width: '100%' }}
          scroll={{ x: totalColumnWidth }}
          onRow={(record) => ({
            onClick: () => setSelectedRowId(record.id),
            style: {
              cursor: 'pointer',
              backgroundColor: record.id === selectedRowId ? '#faf7ff' : '#fff',
            },
          })}
        />
      </Card>

      <Modal
        destroyOnHidden
        open={modalOpen}
        title={editingRowId ? '编辑证书记录' : '新增证书记录'}
        okText={editingRowId ? '保存' : '新增'}
        cancelText="取消"
        confirmLoading={pending}
        onOk={() => form.submit()}
        onCancel={() => {
          setModalOpen(false)
          form.resetFields()
        }}
      >
        <Form<CertificateFormValues> form={form} layout="vertical" onFinish={handleSubmit}>
          {fieldConfigs.map((field: RegistrationCertificateFieldConfig) => (
            <Form.Item
              key={field.key}
              name={field.key}
              label={field.label}
              rules={field.required ? [{ required: true, message: `请填写${field.label}` }] : undefined}
            >
              {field.numeric ? (
                <InputNumber min={0} precision={0} style={{ width: '100%' }} />
              ) : field.multiline ? (
                <Input.TextArea rows={3} />
              ) : (
                <Input />
              )}
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </Space>
  )
}
