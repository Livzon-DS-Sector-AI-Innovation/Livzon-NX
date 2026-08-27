'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Divider, Form, Input, Modal, Popconfirm, Select, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullReturnApplicationRecords, createReturnApplicationRecord, updateReturnApplicationRecord, deleteReturnApplicationRecord } from '@/actions/quality'
import { fetchReturnApplicationRecords, fetchDepartmentContacts } from '@/lib/api/client/quality'
import type { ReturnApplicationItem } from '@/types/quality'
import ReturnApplicationCreateSheet, { type ReturnApplicationFormValues as FormValues } from './ReturnApplicationCreateSheet'

interface ReturnApplicationPageProps {
  initialItems?: ReturnApplicationItem[]
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

export default function ReturnApplicationPage({
  initialItems = [],
}: ReturnApplicationPageProps) {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterProduct, setFilterProduct] = useState<string | undefined>()
  const [filterBatch, setFilterBatch] = useState<string | undefined>()
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ReturnApplicationItem | null>(null)
  const [form] = Form.useForm<FormValues>()
  const { data: contacts = [] } = useQuery({
    queryKey: ['quality-department-contacts'],
    queryFn: fetchDepartmentContacts,
  })

  const queryClient = useQueryClient()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-return', 'applications'],
    queryFn: () => fetchReturnApplicationRecords({ page: '1', page_size: '200' }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载退货申请失败'))
    }
  }, [error, message])

  const items: ReturnApplicationItem[] = data?.data ?? initialItems


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
    const values = [...new Set(items.map((item) => item.batch_number).filter(Boolean))]
    return values.map((value) => ({ label: value!, value: value! })).sort((a, b) => a.label.localeCompare(b.label))
  }, [items])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullReturnApplicationRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-return', 'applications'] })
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

  const openEdit = useCallback((record: ReturnApplicationItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      serial_number: record.serial_number ?? '',
      product_name: record.product_name ?? '',
      return_total: record.return_total ?? '',
      specification: record.specification ?? '',
      batch_number: record.batch_number ?? '',
      quantity: record.quantity ?? '',
      production_date: record.production_date ?? '',
      expiry_date: record.expiry_date ?? '',
      batch_number1: record.batch_number1 ?? '',
      quantity1: record.quantity1 ?? '',
      production_date1: record.production_date1 ?? '',
      expiry_date1: record.expiry_date1 ?? '',
      batch_number2: record.batch_number2 ?? '',
      quantity2: record.quantity2 ?? '',
      production_date2: record.production_date2 ?? '',
      expiry_date2: record.expiry_date2 ?? '',
      return_unit_address: record.return_unit_address ?? '',
      return_reason: record.return_reason ?? '',
      applicant: record.applicant ?? '',
      application_date: toDateValue(record.application_date),
      qa_head_opinion: record.qa_head_opinion ?? '',
      qa_head: record.qa_head ?? '',
      qa_head_date: toDateValue(record.qa_head_date),
      quality_manager_suggestion: record.quality_manager_suggestion ?? '',
      quality_manager: record.quality_manager ?? '',
      quality_manager_date: toDateValue(record.quality_manager_date),
      remark: record.remark ?? '',
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
        return_total: values.return_total?.trim() || '',
        specification: values.specification?.trim() || '',
        batch_number: values.batch_number?.trim() || '',
        quantity: values.quantity?.trim() || '',
        production_date: values.production_date?.trim() || '',
        expiry_date: values.expiry_date?.trim() || '',
        batch_number1: values.batch_number1?.trim() || '',
        quantity1: values.quantity1?.trim() || '',
        production_date1: values.production_date1?.trim() || '',
        expiry_date1: values.expiry_date1?.trim() || '',
        batch_number2: values.batch_number2?.trim() || '',
        quantity2: values.quantity2?.trim() || '',
        production_date2: values.production_date2?.trim() || '',
        expiry_date2: values.expiry_date2?.trim() || '',
        return_unit_address: values.return_unit_address?.trim() || '',
        return_reason: values.return_reason?.trim() || '',
        applicant: values.applicant || '',
        application_date: values.application_date ? values.application_date.format('YYYY-MM-DD') : '',
        qa_head_opinion: values.qa_head_opinion?.trim() || '',
        qa_head: values.qa_head || '',
        qa_head_date: values.qa_head_date ? values.qa_head_date.format('YYYY-MM-DD') : '',
        quality_manager_suggestion: values.quality_manager_suggestion?.trim() || '',
        quality_manager: values.quality_manager || '',
        quality_manager_date: values.quality_manager_date
          ? values.quality_manager_date.format('YYYY-MM-DD')
          : '',
        remark: values.remark?.trim() || '',
      }
      if (editingRecord) {
        await updateReturnApplicationRecord(editingRecord.record_id, payload)
        message.success('退货申请已更新')
      } else {
        await createReturnApplicationRecord(payload)
        message.success('退货申请已创建')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-return', 'applications'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存退货申请失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteReturnApplicationRecord(recordId)
      message.success('退货申请已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-return', 'applications'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除退货申请失败'))
    }
  }, [queryClient, message])

  const hasFilters = filterProduct || filterBatch
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
        (item.batch_number ?? '').toLowerCase().includes(keyword) ||
        (item.return_unit_address ?? '').toLowerCase().includes(keyword) ||
        (item.return_reason ?? '').toLowerCase().includes(keyword) ||
        (item.applicant ?? '').toLowerCase().includes(keyword)
      )
    }
    if (filterProduct) result = result.filter((item) => item.product_name === filterProduct)
    if (filterBatch) result = result.filter((item) => item.batch_number === filterBatch)
    return result
  })()

  const columns: ColumnsType<ReturnApplicationItem> = [
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
      title: '批号',
      dataIndex: 'batch_number',
      key: 'batch_number',
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
      title: '退货总量',
      dataIndex: 'return_total',
      key: 'return_total',
      width: 110,
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
      title: '退货原因',
      dataIndex: 'return_reason',
      key: 'return_reason',
      width: 220,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '申请人',
      dataIndex: 'applicant',
      key: 'applicant',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '申请日期',
      dataIndex: 'application_date',
      key: 'application_date',
      width: 130,
      render: (value: string | null) => formatDate(value),
    },
    {
      title: 'QA负责人',
      dataIndex: 'qa_head',
      key: 'qa_head',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '质量管理负责人',
      dataIndex: 'quality_manager',
      key: 'quality_manager',
      width: 150,
      render: (value: string | null) => value || '-',
    },
    {
      title: '备注',
      dataIndex: 'remark',
      key: 'remark',
      width: 180,
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
            title="确认删除这条退货申请？"
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
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 退货与召回管理 / 退货申请表</p>
        <Typography.Title level={3} style={{ margin: 0 }}>退货申请表</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <Input.Search
            placeholder="搜索品名、批号、退货原因..."
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
          <Select allowClear placeholder="批号" style={{ width: 180 }} value={filterBatch} onChange={setFilterBatch} options={batchOptions} />
          <Button size="small" onClick={clearFilters} disabled={!hasFilters}>清除筛选</Button>
        </div>

        <Table<ReturnApplicationItem>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={filteredItems}
          pagination={false}
          scroll={{ x: 2000 }}
        />
      </Card>

      <Modal
        title={editingRecord ? '修改退货申请' : '新增退货申请单'}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
        forceRender
        width={editingRecord ? 880 : 1240}
      >
        {editingRecord ? (
          <Form form={form} layout="vertical">
            <Form.Item name="serial_number" label="序号">
              <Input placeholder="序号" />
            </Form.Item>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
              <Form.Item name="product_name" label="品名" rules={[{ required: true, message: '请输入品名' }]}>
                <Input placeholder="请输入品名" />
              </Form.Item>
              <Form.Item name="specification" label="规格">
                <Input placeholder="请输入规格" />
              </Form.Item>
              <Form.Item name="batch_number" label="批号">
                <Input placeholder="请输入批号" />
              </Form.Item>
              <Form.Item name="quantity" label="数量">
                <Input placeholder="请输入数量" />
              </Form.Item>
              <Form.Item name="return_total" label="退货总量">
                <Input placeholder="请输入退货总量" />
              </Form.Item>
              <Form.Item name="return_unit_address" label="退货单位及地址">
                <Input placeholder="请输入退货单位及地址" />
              </Form.Item>
              <Form.Item name="production_date" label="生产日期">
                <Input placeholder="请输入生产日期" />
              </Form.Item>
              <Form.Item name="expiry_date" label="有效期/复验期">
                <Input placeholder="请输入有效期/复验期" />
              </Form.Item>
            </div>

            <Divider style={{ margin: '12px 0' }}>扩展批次</Divider>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
              <Form.Item name="batch_number1" label="批号1">
                <Input placeholder="请输入批号1" />
              </Form.Item>
              <Form.Item name="quantity1" label="数量1">
                <Input placeholder="请输入数量1" />
              </Form.Item>
              <Form.Item name="production_date1" label="生产日期1">
                <Input placeholder="请输入生产日期1" />
              </Form.Item>
              <Form.Item name="expiry_date1" label="有效期/复验期1">
                <Input placeholder="请输入有效期/复验期1" />
              </Form.Item>
              <Form.Item name="batch_number2" label="批号2">
                <Input placeholder="请输入批号2" />
              </Form.Item>
              <Form.Item name="quantity2" label="数量2">
                <Input placeholder="请输入数量2" />
              </Form.Item>
              <Form.Item name="production_date2" label="生产日期2">
                <Input placeholder="请输入生产日期2" />
              </Form.Item>
              <Form.Item name="expiry_date2" label="有效期/复验期2">
                <Input placeholder="请输入有效期/复验期2" />
              </Form.Item>
            </div>

            <Form.Item name="return_reason" label="退货原因">
              <Input.TextArea placeholder="请输入退货原因" rows={2} />
            </Form.Item>

            <Divider style={{ margin: '12px 0' }}>审批信息</Divider>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
              <Form.Item name="applicant" label="申请人">
                <Select allowClear showSearch placeholder="请选择申请人" options={contactOptions} />
              </Form.Item>
              <Form.Item name="application_date" label="申请日期">
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item name="qa_head" label="QA负责人">
                <Select allowClear showSearch placeholder="请选择QA负责人" options={contactOptions} />
              </Form.Item>
              <Form.Item name="qa_head_date" label="QA负责人日期">
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
              </Form.Item>
              <Form.Item name="quality_manager" label="质量管理负责人">
                <Select allowClear showSearch placeholder="请选择质量管理负责人" options={contactOptions} />
              </Form.Item>
              <Form.Item name="quality_manager_date" label="质量管理负责人日期">
                <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
              </Form.Item>
            </div>

            <Form.Item name="qa_head_opinion" label="QA负责人意见">
              <Input.TextArea placeholder="请输入QA负责人意见" rows={2} />
            </Form.Item>
            <Form.Item name="quality_manager_suggestion" label="质量管理负责人建议">
              <Input.TextArea placeholder="请输入质量管理负责人建议" rows={2} />
            </Form.Item>
            <Form.Item name="remark" label="备注">
              <Input.TextArea placeholder="请输入备注" rows={2} />
            </Form.Item>
          </Form>
        ) : (
          <ReturnApplicationCreateSheet form={form} contactOptions={contactOptions} />
        )}
      </Modal>
    </div>
  )
}
