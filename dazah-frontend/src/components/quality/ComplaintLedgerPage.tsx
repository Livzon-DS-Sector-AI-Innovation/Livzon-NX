'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Button, Card, DatePicker, Divider, Form, Input, Modal, Popconfirm, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { pullComplaintLedgerRecords, createComplaintLedgerRecord, updateComplaintLedgerRecord, deleteComplaintLedgerRecord } from '@/actions/quality'
import { fetchComplaintLedgerRecords } from '@/lib/api/client/quality'
import type { ComplaintLedgerItem } from '@/types/quality'

interface FormValues {
  serial_number: string
  complaint_number: string
  complaint_content: string
  cause_analysis: string
  reply_date: Dayjs | null
  closing_deadline: string
  complaint_level: string
  complaint_unit: string
  product_name: string
  quantity: string
  handling_result: string
  capa_result: string
  batch_number: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : value
}

function toDateValue(value: string | null | undefined): Dayjs | null {
  if (!value) return null
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed : null
}

interface ComplaintLedgerPageProps {
  initialItems?: ComplaintLedgerItem[]
}

export default function ComplaintLedgerPage({ initialItems = [] }: ComplaintLedgerPageProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [modalVisible, setModalVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ComplaintLedgerItem | null>(null)
  const [form] = Form.useForm<FormValues>()

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ['quality-complaint', 'list'],
    queryFn: () => fetchComplaintLedgerRecords({ page: '1', page_size: '200' }),
    initialData: initialItems.length ? { data: initialItems } : undefined,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载投诉台账失败'))
    }
  }, [error, message])

  const items = useMemo(() => data?.data ?? [], [data?.data])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result: any = await pullComplaintLedgerRecords()
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-complaint', 'list'] })
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

  const openEdit = useCallback((record: ComplaintLedgerItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      serial_number: record.serial_number ?? '',
      complaint_number: record.complaint_number ?? '',
      complaint_content: record.complaint_content ?? '',
      cause_analysis: record.cause_analysis ?? '',
      reply_date: toDateValue(record.reply_date),
      closing_deadline: record.closing_deadline ?? '',
      complaint_level: record.complaint_level ?? '',
      complaint_unit: record.complaint_unit ?? '',
      product_name: record.product_name ?? '',
      quantity: record.quantity ?? '',
      handling_result: record.handling_result ?? '',
      capa_result: record.capa_result ?? '',
      batch_number: record.batch_number ?? '',
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
        complaint_number: values.complaint_number?.trim() || '',
        complaint_content: values.complaint_content?.trim() || '',
        cause_analysis: values.cause_analysis?.trim() || '',
        reply_date: values.reply_date ? values.reply_date.format('YYYY-MM-DD') : '',
        closing_deadline: values.closing_deadline?.trim() || '',
        complaint_level: values.complaint_level?.trim() || '',
        complaint_unit: values.complaint_unit?.trim() || '',
        product_name: values.product_name?.trim() || '',
        quantity: values.quantity?.trim() || '',
        handling_result: values.handling_result?.trim() || '',
        capa_result: values.capa_result?.trim() || '',
        batch_number: values.batch_number?.trim() || '',
      }
      if (editingRecord) {
        await updateComplaintLedgerRecord(editingRecord.record_id, payload)
        message.success('投诉台账记录已更新')
      } else {
        await createComplaintLedgerRecord(payload)
        message.success('投诉台账记录已创建')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-complaint', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存投诉台账记录失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      await deleteComplaintLedgerRecord(recordId)
      message.success('投诉台账记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-complaint', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除投诉台账记录失败'))
    }
  }, [queryClient, message])

  const filteredItems = useMemo(() => {
    if (!searchKeyword) return items
    const keyword = searchKeyword.toLowerCase()
    return items.filter((item) =>
      [
        item.serial_number,
        item.complaint_number,
        item.complaint_content,
        item.cause_analysis,
        item.closing_deadline,
        item.complaint_level,
        item.complaint_unit,
        item.product_name,
        item.quantity,
        item.handling_result,
        item.capa_result,
        item.batch_number,
      ].some((value) => (value ?? '').toLowerCase().includes(keyword))
    )
  }, [items, searchKeyword])

  const columns: ColumnsType<ComplaintLedgerItem> = [
    {
      title: '序号',
      dataIndex: 'serial_number',
      key: 'serial_number',
      width: 90,
      render: (value: string | null) => value || '-',
    },
    {
      title: '投诉编号',
      dataIndex: 'complaint_number',
      key: 'complaint_number',
      width: 150,
      render: (value: string | null) => value || '-',
    },
    {
      title: '投诉内容',
      dataIndex: 'complaint_content',
      key: 'complaint_content',
      width: 260,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '投诉级别',
      dataIndex: 'complaint_level',
      key: 'complaint_level',
      width: 120,
      render: (value: string | null) => value || '-',
    },
    {
      title: '投诉单位（个人）',
      dataIndex: 'complaint_unit',
      key: 'complaint_unit',
      width: 200,
      ellipsis: true,
      render: (value: string | null) => value || '-',
    },
    {
      title: '品名',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: '批号',
      dataIndex: 'batch_number',
      key: 'batch_number',
      width: 140,
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
      title: '回复日期',
      dataIndex: 'reply_date',
      key: 'reply_date',
      width: 130,
      render: (value: string | null) => formatDate(value),
    },
    {
      title: '处理结果',
      dataIndex: 'handling_result',
      key: 'handling_result',
      width: 220,
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
            title="确认删除这条投诉记录？"
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
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 投诉管理 / 投诉台账</p>
        <Typography.Title level={3} style={{ margin: 0 }}>投诉台账</Typography.Title>
      </div>

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <Input.Search
            placeholder="搜索投诉编号、投诉内容、单位、品名、批号..."
            allowClear
            style={{ width: 360 }}
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
          />
          <Space>
            <Button type="primary" onClick={openCreate}>新增</Button>
            <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
          </Space>
        </div>

        <Table<ComplaintLedgerItem>
          rowKey="record_id"
          loading={loading}
          columns={columns}
          dataSource={filteredItems}
          pagination={false}
          scroll={{ x: 1700 }}
        />
      </Card>

      <Modal
        title={editingRecord ? '修改投诉台账记录' : '新增投诉台账记录'}
        open={modalVisible}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
        width={960}
      >
        <Form form={form} layout="vertical">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16 }}>
            <Form.Item name="serial_number" label="序号">
              <Input placeholder="请输入序号" />
            </Form.Item>
            <Form.Item name="complaint_number" label="投诉编号">
              <Input placeholder="请输入投诉编号" />
            </Form.Item>
            <Form.Item
              name="complaint_level"
              label="投诉级别"
            >
              <Input placeholder="请输入投诉级别" />
            </Form.Item>
            <Form.Item name="reply_date" label="回复日期">
              <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item name="complaint_unit" label="投诉单位（个人）">
              <Input placeholder="请输入投诉单位（个人）" />
            </Form.Item>
            <Form.Item name="closing_deadline" label="关闭时限">
              <Input placeholder="请输入关闭时限" />
            </Form.Item>
            <Form.Item name="product_name" label="品名">
              <Input placeholder="请输入品名" />
            </Form.Item>
            <Form.Item name="batch_number" label="批号">
              <Input placeholder="请输入批号" />
            </Form.Item>
            <Form.Item name="quantity" label="数量">
              <Input placeholder="请输入数量" />
            </Form.Item>
          </div>

          <Form.Item
            name="complaint_content"
            label="投诉内容"
            rules={[{ required: true, message: '请输入投诉内容' }]}
          >
            <Input.TextArea placeholder="请输入投诉内容" rows={4} />
          </Form.Item>

          <Form.Item name="cause_analysis" label="原因分析">
            <Input.TextArea placeholder="请输入原因分析" rows={4} />
          </Form.Item>

          <Divider style={{ margin: '8px 0 16px' }}>处理信息</Divider>

          <Form.Item name="handling_result" label="处理结果">
            <Input.TextArea placeholder="请输入处理结果" rows={3} />
          </Form.Item>

          <Form.Item name="capa_result" label="CAPA实施情况及结果">
            <Input.TextArea placeholder="请输入CAPA实施情况及结果" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
