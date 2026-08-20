'use client'

import { useCallback, useEffect, useState } from 'react'
import {Table,
  Card,
  Select,
  Tag,
  Typography,
  App,
  Tabs,
  Button,
  Modal,
  Form,
  Input,
  InputNumber,
  Space,
  Popconfirm,
  Empty,} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { BarChartOutlined, PlusOutlined } from '@ant-design/icons'
import { getPlans, createPlan, updatePlan, deletePlan } from '@/actions/production'
import type { ProductionPlan, SalesPlanDetail } from '@/types/production'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'

const { Title, Text } = Typography
const PRODUCT_OPTIONS = ['洛伐他汀', '美伐他汀', 'L-苯丙氨酸', '霉酚酸', '多拉菌素']
const WORKSHOP_OPTIONS = ['101-1发酵车间', '101-2发酵车间', '102-1发酵车间', '102-2车间', '103发酵车间', '菌种中心', '203-3车间']

// ═══════════════════════════════════════════
// 表单弹窗
// ═══════════════════════════════════════════
function PlanFormModal({
  open,
  editing,
  onCancel,
  onSuccess,
}: {
  open: boolean
  editing: ProductionPlan | null
  onCancel: () => void
  onSuccess: () => void
}) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const isEdit = !!editing

  useEffect(() => {
    if (open) {
      if (editing) {
        form.setFieldsValue({
          workshop: editing.workshop,
          product_name: editing.product_name,
          plan_date: editing.plan_date || undefined,
          planned_yield: editing.planned_yield,
          unit: editing.unit,
          actual_completion: editing.actual_completion,
          completion_rate: editing.completion_rate,
          safety_status: editing.safety_status,
          quality_status: editing.quality_status,
          remarks: editing.remarks,
        })
      } else {
        form.resetFields()
      }
    }
  }, [open, editing, form])

  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      const data = {
        workshop: values.workshop || undefined,
        product_name: values.product_name,
        plan_date: values.plan_date || undefined,
        planned_yield: values.planned_yield ?? undefined,
        unit: values.unit || undefined,
        actual_completion: values.actual_completion ?? undefined,
        completion_rate: values.completion_rate ?? undefined,
        safety_status: values.safety_status || undefined,
        quality_status: values.quality_status || undefined,
        remarks: values.remarks || undefined,
      }
      let res
      if (isEdit && editing) {
        res = await updatePlan(editing.id, data)
      } else {
        res = await createPlan(data)
      }
      if (res.code === 200) {
        message.success(isEdit ? '更新成功' : '创建成功')
        onSuccess()
      } else {
        message.error(res.message || '操作失败')
      }
    } catch {
      // 表单验证失败
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={isEdit ? '编辑生产计划' : '新建生产计划'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
      width={560}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Space size="middle" wrap>
          <Form.Item name="workshop" label="车间">
            <Select allowClear placeholder="选择车间" style={{ width: 160 }} options={WORKSHOP_OPTIONS.map(w => ({ value: w, label: w }))} />
          </Form.Item>
          <Form.Item name="product_name" label="产品" rules={[{ required: true, message: '请输入产品' }]}>
            <Select allowClear placeholder="选择产品" style={{ width: 140 }} options={PRODUCT_OPTIONS.map(p => ({ value: p, label: p }))} />
          </Form.Item>
          <Form.Item name="plan_date" label="日期">
            <Input placeholder="如 2026-07-01" style={{ width: 130 }} />
          </Form.Item>
        </Space>
        <Space size="middle" wrap>
          <Form.Item name="planned_yield" label="计划产量">
            <InputNumber placeholder="计划产量" min={0} style={{ width: 130 }} />
          </Form.Item>
          <Form.Item name="unit" label="单位">
            <Input placeholder="如 批、KG" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name="actual_completion" label="实际完成">
            <InputNumber placeholder="实际完成" min={0} style={{ width: 130 }} />
          </Form.Item>
          <Form.Item name="completion_rate" label="完成率">
            <InputNumber placeholder="0.00" min={0} max={1} step={0.01} style={{ width: 110 }} />
          </Form.Item>
        </Space>
        <Space size="middle" wrap>
          <Form.Item name="safety_status" label="安环情况">
            <Input placeholder="安环情况" style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="quality_status" label="质量情况">
            <Input placeholder="质量情况" style={{ width: 160 }} />
          </Form.Item>
        </Space>
        <Form.Item name="remarks" label="备注">
          <Input.TextArea rows={2} placeholder="备注信息" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

// ═══════════════════════════════════════════
// Tab 2: 销售计划执行表
// ═══════════════════════════════════════════
function SalesPlanTab() {
  const { message } = App.useApp()
  const [data, setData] = useState<SalesPlanDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<SalesPlanDetail | null>(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const BACKEND = 'http://localhost:8000'
  const API = `${BACKEND}/api/v1/production/sales-plan-details`

  const load = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      const res = await fetch(`${API}?page=${p}&page_size=20`)
      const json = await res.json()
      if (json.code === 200) { setData(json.data); setTotal(json.meta?.total || 0) }
    } catch { message.error('加载失败') } finally { setLoading(false) }
  }, [message])

  useEffect(() => { load(page) }, [page, load])

  const handleDelete = async (id: string) => {
    const res = await fetch(`${API}/${id}`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) { message.success('删除成功'); load(page) }
    else message.error(json.message || '删除失败')
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const isEdit = !!editing
      const url = isEdit ? `${API}/${editing.id}` : API
      const res = await fetch(url, { method: isEdit ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) })
      const json = await res.json()
      if (json.code === 200) { message.success(isEdit ? '更新成功' : '创建成功'); setModalOpen(false); load(page) }
      else message.error(json.message || '操作失败')
    } catch { message.error('保存失败') } finally { setSaving(false) }
  }

  const openForm = (record?: SalesPlanDetail) => {
    setEditing(record || null)
    if (record) form.setFieldsValue(record)
    else form.resetFields()
    setModalOpen(true)
  }

  const columns: ColumnsType<SalesPlanDetail> = [
    { title: '产品名称', dataIndex: 'product_name', width: 100, fixed: 'left', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '单位', dataIndex: 'unit', width: 50, render: (v: string | null) => v || '-' },
    { title: '上月已发货未开票', dataIndex: 'last_month_delivered_uninvoiced', width: 110, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '当年当月发货量', dataIndex: 'current_year_delivered', width: 110, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '本月计划发货量', dataIndex: 'month_planned_delivery', width: 110, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '本月已发货量', dataIndex: 'month_delivered_qty', width: 100, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '未发货量', dataIndex: 'undelivered_qty', width: 80, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '本月预计开票量', dataIndex: 'month_planned_invoice', width: 110, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '已开票量', dataIndex: 'invoiced_qty', width: 80, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '发货完成率(%)', dataIndex: 'delivery_completion_rate', width: 100, render: (v: number | null) => v != null ? `${v}%` : '-' },
    { title: '上月底库存', dataIndex: 'last_month_end_inventory', width: 90, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '本月预计产能', dataIndex: 'month_planned_capacity', width: 100, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '本月底库存', dataIndex: 'month_end_inventory', width: 90, render: (v: number | null) => v != null ? v.toLocaleString() : '-' },
    { title: '备注', dataIndex: 'remarks', width: 100, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'actions', width: 120, fixed: 'right',
      render: (_: any, record: SalesPlanDetail) => (
        <Space size="small">
          <Button size="small" onClick={() => openForm(record)}>编辑</Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <SyncSettingsButton productName="销售计划" syncTarget="sales_plan" />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openForm()}>新建明细</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="id" loading={loading}
        scroll={{ x: 1600 }} size="small"
        pagination={{ current: page, pageSize: 20, total, showSizeChanger: true, showTotal: t => `共 ${t} 条`, onChange: p => setPage(p) }} />
      <Modal title={editing ? '编辑明细' : '新建明细'} open={modalOpen} onCancel={() => setModalOpen(false)}
        onOk={handleSave} confirmLoading={saving} width={700} destroyOnHidden>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Space size="middle" wrap>
            <Form.Item name="product_name" label="产品名称" rules={[{ required: true }]}><Input style={{ width: 140 }} /></Form.Item>
            <Form.Item name="unit" label="单位"><Input style={{ width: 80 }} /></Form.Item>
          </Space>
          <Space size="middle" wrap>
            <Form.Item name="last_month_delivered_uninvoiced" label="上月已发货未开票"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="current_year_delivered" label="当年当月发货量"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="month_planned_delivery" label="本月计划发货量"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
          </Space>
          <Space size="middle" wrap>
            <Form.Item name="month_delivered_qty" label="本月已发货量"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="undelivered_qty" label="未发货量"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="month_planned_invoice" label="本月预计开票量"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
          </Space>
          <Space size="middle" wrap>
            <Form.Item name="invoiced_qty" label="已开票量"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="delivery_completion_rate" label="发货完成率(%)"><InputNumber min={0} max={100} style={{ width: 140 }} /></Form.Item>
          </Space>
          <Space size="middle" wrap>
            <Form.Item name="last_month_end_inventory" label="上月底库存"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="month_planned_capacity" label="本月预计产能"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
            <Form.Item name="month_end_inventory" label="本月底库存"><InputNumber min={0} style={{ width: 140 }} /></Form.Item>
          </Space>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

// ═══════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════
export default function PlanPage() {
  const { message } = App.useApp()

  const [plans, setPlans] = useState<ProductionPlan[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [productFilter, setProductFilter] = useState<string | undefined>()
  const [workshopFilter, setWorkshopFilter] = useState<string | undefined>()

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ProductionPlan | null>(null)

  const load = useCallback(
    async (p = 1) => {
      setLoading(true)
      try {
        const res = await getPlans({
          page: p,
          page_size: 20,
          product_name: productFilter,
          workshop: workshopFilter,
        })
        if (res.code === 200) {
          setPlans(res.data || [])
          setTotal(res.meta?.total || 0)
        }
      } catch {
        message.error('加载失败')
      } finally {
        setLoading(false)
      }
    },
    [productFilter, workshopFilter, message],
  )

  useEffect(() => {
    load(page)
  }, [page, productFilter, workshopFilter, load])

  const handleDelete = async (id: string) => {
    const res = await deletePlan(id)
    if (res.code === 200) {
      message.success('删除成功')
      load(page)
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const columns: ColumnsType<ProductionPlan> = [
    { title: '车间', dataIndex: 'workshop', width: 100, render: (v: string | null) => v || '-' },
    { title: '产品', dataIndex: 'product_name', width: 90, render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '日期', dataIndex: 'plan_date', width: 90, render: (v: string | null) => v || '-' },
    { title: '计划产量', dataIndex: 'planned_yield', width: 80, render: (v: number | null) => (v != null ? v.toLocaleString() : '-') },
    { title: '单位', dataIndex: 'unit', width: 50, render: (v: string | null) => v || '-' },
    { title: '实际完成', dataIndex: 'actual_completion', width: 80, render: (v: number | null) => (v != null ? v.toLocaleString() : '-') },
    {
      title: '完成率', dataIndex: 'completion_rate', width: 70,
      render: (v: number | null) => {
        if (v == null) return '-'
        const pct = (v * 100).toFixed(1)
        const color = v >= 1 ? 'green' : v >= 0.5 ? 'orange' : 'red'
        return <Tag color={color}>{pct}%</Tag>
      },
    },
    { title: '安环情况', dataIndex: 'safety_status', width: 80, render: (v: string | null) => v || '-' },
    { title: '质量情况', dataIndex: 'quality_status', width: 80, render: (v: string | null) => v || '-' },
    { title: '备注', dataIndex: 'remarks', width: 120, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '来源',
      dataIndex: 'source',
      width: 60,
      render: (v: string | null) => (v === 'feishu' ? <Tag color="purple">飞书</Tag> : <Tag>手动</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: ProductionPlan) => (
        <Space size="small">
          <Button size="small" onClick={() => { setEditing(record); setModalOpen(true) }}>编辑</Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const planTab = (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <Space wrap>
          <Select placeholder="产品筛选" allowClear value={productFilter}
            onChange={v => { setProductFilter(v); setPage(1) }} style={{ width: 130 }}
            options={PRODUCT_OPTIONS.map(p => ({ value: p, label: p }))} />
          <Select placeholder="车间筛选" allowClear value={workshopFilter}
            onChange={v => { setWorkshopFilter(v); setPage(1) }} style={{ width: 150 }}
            options={WORKSHOP_OPTIONS.map(w => ({ value: w, label: w }))} />
        </Space>
        <Space>
          <SyncSettingsButton productName="生产计划" syncTarget="production_plan" />
          <Button type="primary" icon={<PlusOutlined />}
            onClick={() => { setEditing(null); setModalOpen(true) }}>
            新建计划
          </Button>
        </Space>
      </div>

      {plans.length === 0 && !loading ? (
        <Card>
          <Empty description="暂无生产计划" image={Empty.PRESENTED_IMAGE_SIMPLE}>
            <Space>
              <Button type="primary" icon={<PlusOutlined />}
                onClick={() => { setEditing(null); setModalOpen(true) }}>
                新建计划
              </Button>
              <SyncSettingsButton productName="生产计划" syncTarget="production_plan" />
            </Space>
          </Empty>
        </Card>
      ) : (
        <Table
          columns={columns}
          dataSource={plans}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            showSizeChanger: true,
            showTotal: t => `共 ${t} 条`,
            onChange: p => setPage(p),
          }}
        />
      )}
    </div>
  )

  return (
    <div className="p-6">
      <div className="mb-4">
        <Title level={4} style={{ margin: 0 }}>
          <BarChartOutlined className="mr-2" />
          产销计划
        </Title>
        <Text type="secondary">生产计划管理与飞书数据同步</Text>
      </div>

      <Tabs
        defaultActiveKey="plan"
        items={[
          { key: 'plan', label: '生产计划', children: planTab },
          { key: 'sales', label: '产销计划（销售执行）', children: <SalesPlanTab /> },
        ]}
      />

      <PlanFormModal
        open={modalOpen}
        editing={editing}
        onCancel={() => { setModalOpen(false); setEditing(null) }}
        onSuccess={() => { setModalOpen(false); setEditing(null); load(page) }}
      />
    </div>
  )
}
