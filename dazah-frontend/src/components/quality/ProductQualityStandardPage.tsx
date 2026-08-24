'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App,
  Breadcrumb,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Typography,
} from 'antd'
import { PlusOutlined, ReloadOutlined, CloudDownloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  ProductQualityStandardItem,
  CreateProductQualityStandardRequest,
} from '@/types/quality'
import { fetchProductQualityStandards } from '@/lib/api/client/quality'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createProductQualityStandardAction, updateProductQualityStandardAction, deleteProductQualityStandardAction, pullProductQualityStandardsAction } from '@/actions/quality'
import { buildResizableColumns, ResizableHeaderCell } from './ResizableTableHeader'

const { Title } = Typography
const { TextArea } = Input

const PAGE_SIZE = 100
const COLUMN_WIDTH_STORAGE_KEY_PREFIX = 'quality-product-standard-table-column-widths-v1'

const defaultColumnWidths: Record<string, number> = {
  serial_number: 70,
  customer_name: 140,
  quality_standard: 220,
  shipping_trend_url: 110,
  special_requirements: 220,
  packaging_requirements: 180,
  label_requirements: 180,
  pallet_requirements: 220,
  target_market: 100,
  registration_status: 260,
  other_notes: 240,
  actions: 120,
}

const minColumnWidths: Record<string, number> = {
  serial_number: 60,
  customer_name: 120,
  quality_standard: 160,
  shipping_trend_url: 90,
  special_requirements: 160,
  packaging_requirements: 140,
  label_requirements: 140,
  pallet_requirements: 160,
  target_market: 90,
  registration_status: 180,
  other_notes: 180,
  actions: 100,
}

const wrapCellStyle: React.CSSProperties = {
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  overflowWrap: 'anywhere',
  lineHeight: 1.35,
}

function renderWrappedText(value: string | null | undefined) {
  return <div style={wrapCellStyle}>{value || '-'}</div>
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error ?? '未知错误')
}

interface ProductQualityStandardPageProps {
  productCode: string
  productLabel: string
}

export default function ProductQualityStandardPage({
  productCode,
  productLabel,
}: ProductQualityStandardPageProps) {
  const { message } = App.useApp()
  const columnStorageKey = `${COLUMN_WIDTH_STORAGE_KEY_PREFIX}-${productCode}`

  // Data
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')

  // Modal
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ProductQualityStandardItem | null>(null)
  const [form] = Form.useForm()
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)

  const queryClient = useQueryClient()

  const { data, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['quality-product-standard', 'list', productCode],
    queryFn: () => fetchProductQualityStandards(productCode, {
      page: '1',
      page_size: String(PAGE_SIZE),
    }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error))
    }
  }, [error, message])

  const items = useMemo<ProductQualityStandardItem[]>(() => data?.items ?? [], [data?.items])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(columnStorageKey)
      if (!raw) {
        setColumnWidths(defaultColumnWidths)
        return
      }
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
  }, [columnStorageKey])

  useEffect(() => {
    window.localStorage.setItem(columnStorageKey, JSON.stringify(columnWidths))
  }, [columnStorageKey, columnWidths])

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
    window.localStorage.removeItem(columnStorageKey)
    message.success('已恢复默认列宽')
  }, [columnStorageKey, message])

  const handlePull = async () => {
    setPulling(true)
    try {
      const result = await pullProductQualityStandardsAction(productCode)
      if (result) {
        message.success(`拉取完成：${result.synced} 条`)
      }
      queryClient.invalidateQueries({ queryKey: ['quality-product-standard', 'list', productCode] })
    } catch (e) {
      message.error(getErrorMessage(e))
    } finally {
      setPulling(false)
    }
  }

  const openCreate = () => {
    setEditingRecord(null)
    form.resetFields()
    setModalVisible(true)
  }

  const openEdit = (record: ProductQualityStandardItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      customer_name: record.customer_name,
      quality_standard: record.quality_standard,
      shipping_trend_url: record.shipping_trend_url,
      special_requirements: record.special_requirements,
      packaging_requirements: record.packaging_requirements,
      label_requirements: record.label_requirements,
      pallet_requirements: record.pallet_requirements,
      target_market: record.target_market,
      registration_status: record.registration_status,
      other_notes: record.other_notes,
    })
    setModalVisible(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      const data: CreateProductQualityStandardRequest = {
        customer_name: values.customer_name || null,
        quality_standard: values.quality_standard || null,
        shipping_trend_url: values.shipping_trend_url || null,
        special_requirements: values.special_requirements || null,
        packaging_requirements: values.packaging_requirements || null,
        label_requirements: values.label_requirements || null,
        pallet_requirements: values.pallet_requirements || null,
        target_market: values.target_market || null,
        registration_status: values.registration_status || null,
        other_notes: values.other_notes || null,
      }

      if (editingRecord) {
        await updateProductQualityStandardAction(productCode, editingRecord.record_id, data as Record<string, unknown>)
        message.success('更新成功')
      } else {
        await createProductQualityStandardAction(productCode, data as Record<string, unknown>)
        message.success('创建成功')
      }
      setModalVisible(false)
      queryClient.invalidateQueries({ queryKey: ['quality-product-standard', 'list', productCode] })
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return // form validation
      message.error(getErrorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (recordId: string) => {
    try {
      await deleteProductQualityStandardAction(productCode, recordId)
      message.success('删除成功')
      queryClient.invalidateQueries({ queryKey: ['quality-product-standard', 'list', productCode] })
    } catch (e) {
      message.error(getErrorMessage(e))
    }
  }

  const filteredItems = useMemo(() => {
    if (!searchKeyword) return items
    const kw = searchKeyword.toLowerCase()
    return items.filter(
      (item) =>
        (item.customer_name ?? '').toLowerCase().includes(kw) ||
        (item.quality_standard ?? '').toLowerCase().includes(kw) ||
        (item.target_market ?? '').toLowerCase().includes(kw) ||
        (item.registration_status ?? '').toLowerCase().includes(kw)
    )
  }, [items, searchKeyword])

  const targetMarketOptions = useMemo(() => {
    const vals = [...new Set(items.map((i) => i.target_market).filter(Boolean))]
    return vals.map((v) => ({ label: v!, value: v! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])
  const [filterTargetMarket, setFilterTargetMarket] = useState<string>('')

  const finalItems = useMemo(() => {
    if (!filterTargetMarket) return filteredItems
    return filteredItems.filter((i) => i.target_market === filterTargetMarket)
  }, [filteredItems, filterTargetMarket])

  const baseColumns: ColumnsType<ProductQualityStandardItem> = [
    {
      title: '序号',
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 70,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '客户名称',
      dataIndex: 'customer_name',
      key: 'customer_name',
      width: 140,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '质量标准',
      dataIndex: 'quality_standard',
      key: 'quality_standard',
      width: 220,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '历史发货趋势',
      dataIndex: 'shipping_trend_url',
      key: 'shipping_trend_url',
      width: 110,
      render: (v) =>
        v ? (
          <a href={v} target="_blank" rel="noreferrer">
            查看
          </a>
        ) : (
          '-'
        ),
    },
    {
      title: '特殊要求',
      dataIndex: 'special_requirements',
      key: 'special_requirements',
      width: 220,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '包装要求',
      dataIndex: 'packaging_requirements',
      key: 'packaging_requirements',
      width: 180,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '标签要求',
      dataIndex: 'label_requirements',
      key: 'label_requirements',
      width: 180,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '发货打托要求',
      dataIndex: 'pallet_requirements',
      key: 'pallet_requirements',
      width: 220,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '目标市场',
      dataIndex: 'target_market',
      key: 'target_market',
      width: 100,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '注册情况',
      dataIndex: 'registration_status',
      key: 'registration_status',
      width: 260,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '其他注意事项',
      dataIndex: 'other_notes',
      key: 'other_notes',
      width: 240,
      render: (v) => renderWrappedText(v),
    },
    {
      title: '操作', key: 'actions', width: 120, fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" style={{ paddingInline: 0 }} onClick={() => openEdit(record)}>修改</Button>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.record_id)}>
            <Button type="link" size="small" danger style={{ paddingInline: 0 }}>删除</Button>
          </Popconfirm>
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

  return (
    <div style={{ padding: 24 }}>
      <Breadcrumb
        items={[{ title: '质量管理' }, { title: '产品质量管理' }, { title: productLabel }]}
        style={{ marginBottom: 16 }}
      />
      <Title level={4}>{productLabel}客户标准</Title>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <Input.Search
            placeholder="搜索客户名称、质量标准、目标市场"
            allowClear
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            style={{ width: 320 }}
          />
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>新增</Button>
            <Button icon={<CloudDownloadOutlined />} loading={pulling} onClick={handlePull}>从飞书拉取</Button>
            <Button icon={<ReloadOutlined />} onClick={() => void refetch()} loading={loading}>刷新</Button>
            <Button onClick={resetColumnWidths}>恢复列宽</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          <Select
            placeholder="目标市场"
            allowClear
            value={filterTargetMarket || undefined}
            onChange={(v) => setFilterTargetMarket(v ?? '')}
            options={targetMarketOptions}
            style={{ width: 160 }}
          />
          {(searchKeyword || filterTargetMarket) && (
            <Button
              size="small"
              onClick={() => { setSearchKeyword(''); setFilterTargetMarket('') }}
            >
              清除筛选
            </Button>
          )}
        </div>

        <Table
          columns={columns}
          components={{ header: { cell: ResizableHeaderCell } }}
          dataSource={finalItems}
          rowKey="record_id"
          loading={loading}
          pagination={false}
          scroll={{ x: 1900 }}
          size="middle"
          tableLayout="fixed"
          className="product-quality-standard-table"
        />
      </Card>

      <style jsx global>{`
        .product-quality-standard-table .ant-table-thead > tr > th {
          padding: 8px 10px;
        }

        .product-quality-standard-table .ant-table-tbody > tr > td {
          padding: 8px 10px;
          vertical-align: top;
        }
      `}</style>

      <Modal
        title={editingRecord ? '修改产品质量标准' : '新增产品质量标准'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={handleSubmit}
        confirmLoading={saving}
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="customer_name" label="客户名称">
            <Input placeholder="请输入客户名称" />
          </Form.Item>
          <Form.Item name="quality_standard" label="质量标准">
            <TextArea rows={2} placeholder="请输入质量标准" />
          </Form.Item>
          <Form.Item name="shipping_trend_url" label="历史发货趋势链接">
            <Input placeholder="请输入URL链接" />
          </Form.Item>
          <Form.Item name="special_requirements" label="特殊要求">
            <TextArea rows={2} placeholder="请输入特殊要求" />
          </Form.Item>
          <Form.Item name="packaging_requirements" label="包装要求">
            <TextArea rows={2} placeholder="请输入包装要求" />
          </Form.Item>
          <Form.Item name="label_requirements" label="标签要求">
            <TextArea rows={2} placeholder="请输入标签要求" />
          </Form.Item>
          <Form.Item name="pallet_requirements" label="发货打托要求">
            <TextArea rows={2} placeholder="请输入发货打托要求" />
          </Form.Item>
          <Form.Item name="target_market" label="目标市场">
            <Input placeholder="请输入目标市场" />
          </Form.Item>
          <Form.Item name="registration_status" label="注册情况">
            <Input placeholder="请输入注册情况" />
          </Form.Item>
          <Form.Item name="other_notes" label="其他注意事项">
            <TextArea rows={2} placeholder="请输入其他注意事项" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
