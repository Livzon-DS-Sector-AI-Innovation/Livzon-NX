'use client'

import { useEffect, useState } from 'react'
import { App, Button, Card, Form, Input, InputNumber, Modal, Space, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'

import {
  createSalesPlanDetail,
  deleteSalesPlanDetail,
  getSalesPlanDetails,
  updateSalesPlanDetail,
} from '@/actions/production'
import type { components } from '@/types/generated/schema'

type SalesPlanDetail = components['schemas']['SalesPlanDetailResponse']
type SalesPlanDetailCreate = components['schemas']['SalesPlanDetailCreate']
type SalesPlanDetailUpdate = components['schemas']['SalesPlanDetailUpdate']

const metricFields: Array<{ name: keyof SalesPlanDetailCreate; label: string }> = [
  { name: 'last_month_delivered_uninvoiced', label: '上月已发货未开票' },
  { name: 'current_year_delivered', label: '当年当月发货量' },
  { name: 'month_planned_delivery', label: '本月计划发货量' },
  { name: 'month_delivered_qty', label: '本月已发货量' },
  { name: 'undelivered_qty', label: '未发货量' },
  { name: 'month_planned_invoice', label: '本月预计开票量' },
  { name: 'invoiced_qty', label: '已开票量' },
  { name: 'delivery_completion_rate', label: '本月发货完成率(%)' },
  { name: 'last_month_end_inventory', label: '上月底库存' },
  { name: 'month_planned_capacity', label: '本月预计产能' },
  { name: 'month_end_inventory', label: '本月底库存' },
]

export function SalesPlanDetailTab() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm<SalesPlanDetailCreate>()
  const [rows, setRows] = useState<SalesPlanDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [editing, setEditing] = useState<SalesPlanDetail | null>(null)
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const loadRows = async (targetPage = page, productName = keyword) => {
    setLoading(true)
    try {
      const response = await getSalesPlanDetails({
        page: targetPage,
        page_size: 20,
        product_name: productName || undefined,
      })
      if (response.code !== 200) {
        message.error(response.message || '加载销售执行明细失败')
        return
      }
      setRows(response.data || [])
      setTotal(response.meta?.total || 0)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRows()
  }, [page])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldValue('source', 'manual')
    setVisible(true)
  }

  const openEdit = (record: SalesPlanDetail) => {
    setEditing(record)
    form.setFieldsValue(record)
    setVisible(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    const response = editing
      ? await updateSalesPlanDetail(editing.id, values as SalesPlanDetailUpdate)
      : await createSalesPlanDetail(values as SalesPlanDetailCreate)
    if (response.code !== 200) {
      message.error(response.message || '保存失败')
      return
    }
    message.success('保存成功')
    setVisible(false)
    await loadRows()
  }

  const remove = (record: SalesPlanDetail) => {
    modal.confirm({
      title: '确认删除销售执行明细？',
      content: `产品：${record.product_name}`,
      okButtonProps: { danger: true },
      onOk: async () => {
        const response = await deleteSalesPlanDetail(record.id)
        if (response.code !== 200) {
          message.error(response.message || '删除失败')
          return
        }
        message.success('删除成功')
        await loadRows(rows.length === 1 && page > 1 ? page - 1 : page)
      },
    })
  }

  const columns: ColumnsType<SalesPlanDetail> = [
    { title: '产品名称', dataIndex: 'product_name', width: 160, fixed: 'left' },
    { title: '单位', dataIndex: 'unit', width: 80 },
    { title: '计划发货', dataIndex: 'month_planned_delivery', width: 110 },
    { title: '已发货', dataIndex: 'month_delivered_qty', width: 100 },
    { title: '未发货', dataIndex: 'undelivered_qty', width: 100 },
    { title: '预计开票', dataIndex: 'month_planned_invoice', width: 110 },
    { title: '已开票', dataIndex: 'invoiced_qty', width: 100 },
    { title: '月底库存', dataIndex: 'month_end_inventory', width: 100 },
    { title: '完成率', dataIndex: 'delivery_completion_rate', width: 100, render: (value) => value == null ? '-' : `${value}%` },
    { title: '来源', dataIndex: 'source', width: 90 },
    {
      title: '操作',
      width: 130,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => remove(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="销售执行计划"
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增明细</Button>}
    >
      <Space className="mb-4" wrap>
        <Input
          allowClear
          placeholder="搜索产品名称"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onPressEnter={() => { setPage(1); void loadRows(1) }}
          style={{ width: 240 }}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={() => { setPage(1); void loadRows(1) }}>
          查询
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={rows}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1300 }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showSizeChanger: false,
          showTotal: (count) => `共 ${count} 条`,
          onChange: setPage,
        }}
      />

      <Modal
        title={editing ? '编辑销售执行明细' : '新增销售执行明细'}
        open={visible}
        onOk={() => void submit()}
        onCancel={() => setVisible(false)}
        width={760}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Space size="middle" className="w-full" align="start">
            <Form.Item name="product_name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]} className="flex-1">
              <Input maxLength={128} />
            </Form.Item>
            <Form.Item name="unit" label="单位" className="w-32">
              <Input maxLength={32} />
            </Form.Item>
          </Space>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            {metricFields.map((field) => (
              <Form.Item key={field.name} name={field.name} label={field.label}>
                <InputNumber className="w-full" precision={2} />
              </Form.Item>
            ))}
          </div>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
