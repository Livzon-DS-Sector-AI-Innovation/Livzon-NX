'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Form, Input, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createReturnLedgerRecord, deleteReturnLedgerRecord, pullReturnLedgerRecords, updateReturnLedgerRecord } from '@/actions/quality'
import { fetchDepartmentContacts, fetchReturnLedgerRecords } from '@/lib/api/client/quality'
import type { DepartmentContact, ReturnLedgerItem } from '@/types/quality'
import { TableEmptyState } from './TableEmptyState'


interface ReturnLedgerPageProps {
  initialItems?: ReturnLedgerItem[]
}

interface FormValues {
  serial_number: string
  product_name: string
  specification: string
  product_batch_number: string
  quantity: string
  return_unit_address: string
  return_date: Dayjs | null
  operator: string
  disposal_result: string
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : value
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function toDateValue(value: string | null | undefined): Dayjs | null {
  if (!value) return null
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed : null
}

export default function ReturnLedgerPage({
  initialItems = [],
}: ReturnLedgerPageProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterProduct, setFilterProduct] = useState<string | undefined>()
  const [filterBatch, setFilterBatch] = useState<string | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ReturnLedgerItem | null>(null)
  const [form] = Form.useForm<FormValues>()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data: contacts = [] } = useQuery<DepartmentContact[]>({
    queryKey: ['quality-department-contacts'],
    queryFn: fetchDepartmentContacts,
  })

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-return', 'list'],
    queryFn: () => fetchReturnLedgerRecords({ page: '1', page_size: '200' }),
    initialData: initialItems.length ? { data: initialItems } : undefined,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载退回台账失败'))
    }
  }, [error, message])

  const items = useMemo(() => data?.data ?? [], [data?.data])

  const contactOptions = contacts
    .filter((item) => item.name)
    .map((item) => ({
      label: item.name!,
      value: (item as any).bitable_user_id || item.open_id || item.name!,
    }))

  const productOptions = useMemo(() => {
    const values = [...new Set(items.map((item) => item.product_name).filter(Boolean))]
    return values.map((value) => ({ label: value!, value: value! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const batchOptions = useMemo(() => {
    const values = [...new Set(items.map((item) => item.product_batch_number).filter(Boolean))]
    return values.map((value) => ({ label: value!, value: value! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullReturnLedgerRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-return', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  const openCreate = useCallback(() => {
    setEditingRecord(null)
    form.resetFields()
    setModalVisible(true)
  }, [form])

  const openEdit = useCallback((record: ReturnLedgerItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      serial_number: record.serial_number ?? '',
      product_name: record.product_name ?? '',
      specification: record.specification ?? '',
      product_batch_number: record.product_batch_number ?? '',
      quantity: record.quantity ?? '',
      return_unit_address: record.return_unit_address ?? '',
      return_date: toDateValue(record.return_date),
      operator: record.operator ?? '',
      disposal_result: record.disposal_result ?? '',
    })
    setModalVisible(true)
  }, [form])

  const closeModal = useCallback(() => {
    setModalVisible(false)
    setEditingRecord(null)
    form.resetFields()
  }, [form])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      const payload: Record<string, unknown> = {
        serial_number: values.serial_number?.trim() || '',
        product_name: values.product_name?.trim() || '',
        specification: values.specification?.trim() || '',
        product_batch_number: values.product_batch_number?.trim() || '',
        quantity: values.quantity?.trim() || '',
        return_unit_address: values.return_unit_address?.trim() || '',
        return_date: values.return_date ? values.return_date.format('YYYY-MM-DD') : '',
        operator: values.operator || '',
        disposal_result: values.disposal_result?.trim() || '',
      }
      if (editingRecord) {
        await updateReturnLedgerRecord(editingRecord.record_id, payload)
        message.success('退回台账已更新')
      } else {
        await createReturnLedgerRecord(payload)
        message.success('退回台账已创建')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-return', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存退回台账失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteReturnLedgerRecord(recordId)
      message.success('退回台账已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-return', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除退回台账失败'))
    }
  }, [queryClient, message])

  const hasFilters = searchKeyword || filterProduct || filterBatch
  const clearFilters = useCallback(() => {
    setFilterProduct(undefined)
    setFilterBatch(undefined)
  }, [])

  const filteredItems = (() => {
    let result = items
    if (searchKeyword) {
      const keyword = searchKeyword.toLowerCase()
      result = result.filter((item) =>
        (item.product_name ?? '').toLowerCase().includes(keyword) ||
        (item.product_batch_number ?? '').toLowerCase().includes(keyword) ||
        (item.return_unit_address ?? '').toLowerCase().includes(keyword) ||
        (item.operator ?? '').toLowerCase().includes(keyword) ||
        (item.disposal_result ?? '').toLowerCase().includes(keyword)
      )
    }
    if (filterProduct) result = result.filter((item) => item.product_name === filterProduct)
    if (filterBatch) result = result.filter((item) => item.product_batch_number === filterBatch)
    return result
  })()

  // 搜索/筛选变化时回到第一页
  useEffect(() => {
    setPage(1)
  }, [searchKeyword, filterProduct, filterBatch])

  const pagedItems = filteredItems.slice((page - 1) * pageSize, page * pageSize)

  const columns: ColumnsType<ReturnLedgerItem> = [
    {
      title: '序号',
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 80,
      render: (value: string | null) => value || '-',
    },
    {
      title: '品名',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 160,
      render: (value: string | null) => value || '-',
    },
    {
      title: '规格',
      dataIndex: 'specification',
      key: 'specification',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '产品批号',
      dataIndex: 'product_batch_number',
      key: 'product_batch_number',
      width: 160,
      render: (value: string | null) => value || '-',
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      render: (value: string | null) => value || '-',
    },
    {
      title: '退货单位及地址',
      dataIndex: 'return_unit_address',
      key: 'return_unit_address',
      width: 220,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '退回日期',
      dataIndex: 'return_date',
      key: 'return_date',
      width: 130,
      render: (value: string | null) => formatDate(value),
    },
    {
      title: '经办人',
      dataIndex: 'operator',
      key: 'operator',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '退回产品处理结果',
      dataIndex: 'disposal_result',
      key: 'disposal_result',
      width: 240,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" onClick={() => openEdit(record)}>修改</Button>
          <Popconfirm
            title="确认删除这条退回台账记录？"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void handleDelete(record.record_id)}
          >
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 退货与召回管理 / 退回台账</p>
        <Typography.Title level={3} style={{ margin: 0 }}>退回台账</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <Input.Search
            placeholder="搜索品名、批号、经办人..."
            allowClear
            style={{ width: 320 }}
            value={searchKeyword}
            onChange={(event) => setSearchKeyword(event.target.value)}
          />
          <Space>
            <Button type="primary" onClick={openCreate}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
          <Select allowClear placeholder="品名" style={{ width: 180 }} value={filterProduct} onChange={setFilterProduct} options={productOptions} />
          <Select allowClear placeholder="产品批号" style={{ width: 180 }} value={filterBatch} onChange={setFilterBatch} options={batchOptions} />
          <Button size="small" onClick={clearFilters} disabled={!hasFilters}>清除筛选</Button>
        </div>

        <Table<ReturnLedgerItem>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={pagedItems}
          locale={{
            emptyText: (
              <TableEmptyState hasFilters={Boolean(hasFilters)} hasError={Boolean(error)} />
            ),
          }}
          pagination={{
            current: page,
            pageSize,
            total: filteredItems.length,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
            },
          }}
          scroll={{ x: 1700 }}
        />
      </Card>

      <Modal
        title={editingRecord ? '修改退回台账' : '新增退回台账'}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
        width={760}
      >
        <Form form={form} layout="vertical">
          {editingRecord ? (
            <Form.Item name="serial_number" label="序号">
              <Input placeholder="序号" />
            </Form.Item>
          ) : null}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
            <Form.Item name="product_name" label="品名" rules={[{ required: true, message: '请输入品名' }]}>
              <Input placeholder="请输入品名" />
            </Form.Item>
            <Form.Item name="specification" label="规格">
              <Input placeholder="请输入规格" />
            </Form.Item>
            <Form.Item name="product_batch_number" label="产品批号">
              <Input placeholder="请输入产品批号" />
            </Form.Item>
            <Form.Item name="quantity" label="数量">
              <Input placeholder="请输入数量" />
            </Form.Item>
            <Form.Item name="return_unit_address" label="退货单位及地址">
              <Input placeholder="请输入退货单位及地址" />
            </Form.Item>
            <Form.Item name="return_date" label="退回日期">
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="operator" label="经办人">
              <Select allowClear showSearch placeholder="请选择经办人" options={contactOptions} />
            </Form.Item>
          </div>
          <Form.Item name="disposal_result" label="退回产品处理结果">
            <Input.TextArea placeholder="请输入退回产品处理结果" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
