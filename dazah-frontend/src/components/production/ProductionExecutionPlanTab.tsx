'use client'

import { useEffect, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import {
  App,
  Button,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'

import {
  createProductionExecutionPlan,
  deleteProductionExecutionPlan,
  getProductionExecutionPlans,
  updateProductionExecutionPlan,
} from '@/actions/production'
import type { components } from '@/types/generated/schema'

type ExecutionPlan = components['schemas']['ProductionExecutionPlanResponse']
type ExecutionPlanCreate = components['schemas']['ProductionExecutionPlanCreate']
type ExecutionPlanUpdate = components['schemas']['ProductionExecutionPlanUpdate']

interface FormValues extends Omit<ExecutionPlanCreate, 'plan_date'> {
  plan_date?: Dayjs
}

const WORKSHOPS = [
  '101-1', '101-2', '102-1', '102-2', '103', '201-1', '201-2', '201-3', '202', '203', '203-3',
]

export function ProductionExecutionPlanTab() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [rows, setRows] = useState<ExecutionPlan[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<ExecutionPlan | null>(null)
  const [workshop, setWorkshop] = useState<string>()
  const [productName, setProductName] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const response = await getProductionExecutionPlans({
        page_size: 200,
        workshop,
        product_name: productName.trim() || undefined,
      })
      if (response.code === 200) setRows(response.data || [])
      else message.error(response.message || '加载生产执行计划失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [workshop])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ source: 'manual', unit: 'kg', plan_date: dayjs() })
    setDrawerOpen(true)
  }

  const openEdit = (record: ExecutionPlan) => {
    setEditing(record)
    form.setFieldsValue({
      ...record,
      plan_date: record.plan_date ? dayjs(record.plan_date) : undefined,
    })
    setDrawerOpen(true)
  }

  const save = async () => {
    const values = await form.validateFields()
    const payload = {
      ...values,
      plan_date: values.plan_date?.format('YYYY-MM-DD') || null,
    }
    setSaving(true)
    try {
      const response = editing
        ? await updateProductionExecutionPlan(editing.id, payload satisfies ExecutionPlanUpdate)
        : await createProductionExecutionPlan(payload satisfies ExecutionPlanCreate)
      if (response.code !== 200) {
        message.error(response.message || '保存生产执行计划失败')
        return
      }
      message.success(editing ? '生产执行计划已更新' : '生产执行计划已创建')
      setDrawerOpen(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  const remove = async (record: ExecutionPlan) => {
    const response = await deleteProductionExecutionPlan(record.id)
    if (response.code !== 200) {
      message.error(response.message || '删除生产执行计划失败')
      return
    }
    message.success('生产执行计划已删除')
    await load()
  }

  const columns: ColumnsType<ExecutionPlan> = [
    { title: '车间', dataIndex: 'workshop', width: 90, fixed: 'left', render: value => value || '-' },
    { title: '产品', dataIndex: 'product_name', width: 150, fixed: 'left' },
    { title: '日期', dataIndex: 'plan_date', width: 110, render: value => value || '-' },
    { title: '单位', dataIndex: 'unit', width: 70, render: value => value || '-' },
    { title: '计划产量', dataIndex: 'planned_yield', width: 110, render: value => value ?? '-' },
    { title: '实际完成', dataIndex: 'actual_completion', width: 110, render: value => value ?? '-' },
    {
      title: '完成率',
      dataIndex: 'completion_rate',
      width: 100,
      render: value => value == null ? '-' : <Tag color={value >= 100 ? 'success' : 'processing'}>{value}%</Tag>,
    },
    { title: '安环情况', dataIndex: 'safety_status', width: 140, ellipsis: true, render: value => value || '-' },
    { title: '质量情况', dataIndex: 'quality_status', width: 140, ellipsis: true, render: value => value || '-' },
    { title: '备注', dataIndex: 'remarks', width: 180, ellipsis: true, render: value => value || '-' },
    {
      title: '来源',
      dataIndex: 'source',
      width: 90,
      render: value => <Tag>{value === 'manual' ? '手工' : value}</Tag>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="删除这条生产执行计划？" onConfirm={() => remove(record)}>
            <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除生产执行计划" />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Typography.Title level={4} className="!mb-1">车间生产执行计划</Typography.Title>
          <Typography.Text type="secondary">按车间、产品和日期跟踪计划产量、实际完成及安环质量情况</Typography.Text>
        </div>
        <Space wrap>
          <Select
            allowClear
            placeholder="全部车间"
            value={workshop}
            onChange={setWorkshop}
            options={WORKSHOPS.map(value => ({ value, label: value }))}
            style={{ width: 140 }}
          />
          <Input.Search
            allowClear
            placeholder="搜索产品"
            value={productName}
            onChange={event => setProductName(event.target.value)}
            onSearch={() => void load()}
            style={{ width: 200 }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增计划</Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        scroll={{ x: 1450 }}
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: total => `共 ${total} 条` }}
        locale={{ emptyText: '暂无生产执行计划，新增第一条计划后可跟踪完成情况' }}
      />

      <Drawer
        title={editing ? '编辑生产执行计划' : '新增生产执行计划'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={560}
        extra={<Button type="primary" loading={saving} onClick={() => void save()}>保存</Button>}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" requiredMark="optional">
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            <Form.Item name="workshop" label="车间">
              <Select showSearch allowClear options={WORKSHOPS.map(value => ({ value, label: value }))} />
            </Form.Item>
            <Form.Item name="product_name" label="产品" rules={[{ required: true, message: '请输入产品名称' }]}>
              <Input maxLength={128} />
            </Form.Item>
            <Form.Item name="plan_date" label="计划日期"><DatePicker className="w-full" /></Form.Item>
            <Form.Item name="unit" label="单位"><Input maxLength={32} /></Form.Item>
            <Form.Item name="planned_yield" label="计划产量"><InputNumber min={0} className="!w-full" /></Form.Item>
            <Form.Item name="actual_completion" label="实际完成"><InputNumber min={0} className="!w-full" /></Form.Item>
          </div>
          <Form.Item name="safety_status" label="安环情况"><Input maxLength={128} /></Form.Item>
          <Form.Item name="quality_status" label="质量情况"><Input maxLength={128} /></Form.Item>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="source" hidden><Input /></Form.Item>
        </Form>
      </Drawer>
    </div>
  )
}
