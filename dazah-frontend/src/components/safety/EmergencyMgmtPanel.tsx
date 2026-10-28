'use client'

import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  createEmergencyDrill,
  createEmergencyPlan,
  createEmergencySupply,
  deleteEmergencyDrill,
  deleteEmergencyPlan,
  deleteEmergencySupply,
  downloadEmergencyPlanFile,
  getEmergencyDrills,
  getEmergencyPlans,
  getEmergencySupplies,
  updateEmergencyDrill,
  updateEmergencyPlan,
  updateEmergencySupply,
  uploadEmergencyPlanFile,
  type EmergencyDrillItem,
  type EmergencyPlanItem,
  type EmergencySupplyItem,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'

const { Text, Title } = Typography

const T = {
  error: '#E03131',
  warning: '#DD5B00',
  success: '#1AAE39',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  mint: '#d9f3e1',
  rose: '#fde0ec',
  peach: '#ffe8d4',
  lavender: '#e6e0f5',
  primary: '#5645d4',
}

export const PLAN_TYPE_LABELS: Record<string, string> = {
  comprehensive: '综合预案',
  special: '专项预案',
  onsite: '现场处置方案',
}

export const PLAN_STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: '现行', color: T.success, bg: T.mint },
  revising: { label: '修订中', color: T.warning, bg: T.peach },
  obsolete: { label: '废止', color: T.steel, bg: T.surface },
}

export const DRILL_TYPE_LABELS: Record<string, string> = {
  tabletop: '桌面推演',
  practical: '实战演练',
  comprehensive: '综合演练',
}

export const DRILL_STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  planned: { label: '计划', color: T.primary, bg: T.lavender },
  done: { label: '完成', color: T.success, bg: T.mint },
  cancelled: { label: '取消', color: T.steel, bg: T.surface },
}

export const SUPPLY_CATEGORY_LABELS: Record<string, string> = {
  firefighting: '消防',
  protective: '防护',
  medical: '医疗',
  communication: '通讯',
  leak_sealing: '堵漏',
  other: '其他',
}

export const SUPPLY_STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  good: { label: '完好', color: T.success, bg: T.mint },
  repair: { label: '待修', color: T.warning, bg: T.peach },
  scrapped: { label: '报废', color: T.steel, bg: T.surface },
}

type PlanFormValues = {
  name: string
  plan_type: string
  version: string
  issued_at?: string | null
  review_due_date?: string | null
  status: string
  department?: string
  remark?: string
}

type DrillFormValues = {
  name: string
  drill_type: string
  scenario?: string
  plan_name?: string
  planned_date?: string | null
  actual_date?: string | null
  location?: string
  departments?: string
  participants_count?: number | null
  summary?: string
  issues?: string
  status: string
}

type SupplyFormValues = {
  name: string
  category: string
  spec?: string
  location?: string
  department?: string
  quantity: number
  unit: string
  status: string
  expiry_date?: string | null
  last_checked_at?: string | null
  last_check_result?: string
  remark?: string
}

function fmtDate(value?: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleDateString('zh-CN')
}

export default function EmergencyMgmtPanel({
  pageKey,
  initialPlans,
  initialDrills,
  initialSupplies,
  initialError,
}: {
  pageKey: string
  initialPlans: EmergencyPlanItem[]
  initialDrills: EmergencyDrillItem[]
  initialSupplies: EmergencySupplyItem[]
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()

  const [plans, setPlans] = useState<EmergencyPlanItem[]>(initialPlans)
  const [drills, setDrills] = useState<EmergencyDrillItem[]>(initialDrills)
  const [supplies, setSupplies] = useState<EmergencySupplyItem[]>(initialSupplies)
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)

  const [planFormOpen, setPlanFormOpen] = useState(false)
  const [editingPlan, setEditingPlan] = useState<EmergencyPlanItem | null>(null)
  const [planForm] = Form.useForm<PlanFormValues>()

  const [drillFormOpen, setDrillFormOpen] = useState(false)
  const [editingDrill, setEditingDrill] = useState<EmergencyDrillItem | null>(null)
  const [drillForm] = Form.useForm<DrillFormValues>()

  const [supplyFormOpen, setSupplyFormOpen] = useState(false)
  const [editingSupply, setEditingSupply] = useState<EmergencySupplyItem | null>(null)
  const [supplyForm] = Form.useForm<SupplyFormValues>()

  useEffect(() => {
    setPlans(initialPlans)
    setDrills(initialDrills)
    setSupplies(initialSupplies)
    setError(initialError)
  }, [initialPlans, initialDrills, initialSupplies, initialError])

  const refreshAll = async () => {
    setLoading(true)
    try {
      const [plansRes, drillsRes, suppliesRes] = await Promise.all([
        getEmergencyPlans({ page_size: 200 }),
        getEmergencyDrills({ page_size: 200 }),
        getEmergencySupplies({ page_size: 200 }),
      ])
      if (plansRes.code === 200 && plansRes.data) setPlans(plansRes.data.items)
      if (drillsRes.code === 200 && drillsRes.data) setDrills(drillsRes.data.items)
      if (suppliesRes.code === 200 && suppliesRes.data) setSupplies(suppliesRes.data.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载应急管理数据失败')
    } finally {
      setLoading(false)
    }
  }

  // ---------- 应急预案 ----------

  const openPlanCreate = () => {
    setEditingPlan(null)
    planForm.setFieldsValue({
      name: '',
      plan_type: 'onsite',
      version: 'V1.0',
      status: 'active',
      department: '',
      remark: '',
    })
    setPlanFormOpen(true)
  }

  const openPlanEdit = (item: EmergencyPlanItem) => {
    setEditingPlan(item)
    planForm.setFieldsValue({ ...item })
    setPlanFormOpen(true)
  }

  const submitPlan = async () => {
    const values = await planForm.validateFields()
    const payload = {
      name: values.name,
      plan_type: values.plan_type,
      version: values.version ?? 'V1.0',
      issued_at: values.issued_at || null,
      review_due_date: values.review_due_date || null,
      status: values.status,
      department: values.department ?? '',
      remark: values.remark ?? '',
    }
    try {
      const res = editingPlan
        ? await updateEmergencyPlan(editingPlan.id, payload)
        : await createEmergencyPlan(payload)
      if (res.code === 200) {
        message.success(editingPlan ? '预案已更新' : '预案已创建')
        setPlanFormOpen(false)
        await refreshAll()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handlePlanDelete = async (item: EmergencyPlanItem) => {
    const res = await deleteEmergencyPlan(item.id)
    if (res.code === 200) {
      message.success('预案已删除')
      await refreshAll()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const planColumns: ColumnsType<EmergencyPlanItem> = [
    {
      title: '预案名称',
      dataIndex: 'name',
      key: 'name',
      render: (v, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          <div>
            <Text style={{ color: T.steel, fontSize: 12 }}>
              {PLAN_TYPE_LABELS[row.plan_type] || row.plan_type} · {row.version}
              {row.department ? ` · ${row.department}` : ''}
            </Text>
          </div>
        </div>
      ),
    },
    { title: '发布日期', dataIndex: 'issued_at', key: 'issued_at', width: 110, render: (v: string | null) => fmtDate(v) },
    {
      title: '评审到期',
      dataIndex: 'review_due_date',
      key: 'review_due_date',
      width: 120,
      render: (v: string | null) => {
        if (!v) return <Text style={{ color: T.muted }}>-</Text>
        const days = Math.ceil((new Date(v).getTime() - Date.now()) / 86400000)
        const soon = days >= 0 && days <= 30
        return (
          <Tag
            style={{
              borderRadius: 6,
              border: 'none',
              fontWeight: 600,
              backgroundColor: days < 0 ? T.rose : soon ? T.peach : T.surface,
              color: days < 0 ? T.error : soon ? T.warning : T.steel,
            }}
          >
            {fmtDate(v)}（{days < 0 ? '已逾期' : `${days}天`}）
          </Tag>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => {
        const meta = PLAN_STATUS_LABELS[v] || { label: v, color: T.steel, bg: T.surface }
        return (
          <Tag style={{ color: meta.color, backgroundColor: meta.bg, border: 'none', borderRadius: 6, fontWeight: 600 }}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: '文件',
      key: 'file',
      width: 160,
      render: (_, row) =>
        row.file_path ? (
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            style={{ padding: 0 }}
            onClick={() =>
              downloadEmergencyPlanFile(row.id, row.file_name || `${row.name}`).catch((err) =>
                message.error(err instanceof Error ? err.message : '下载失败')
              )
            }
          >
            {row.file_name || '下载'}
          </Button>
        ) : (
          <Upload
            showUploadList={false}
            accept=".pdf,.doc,.docx"
            customRequest={async ({ file, onSuccess, onError }) => {
              try {
                const res = await uploadEmergencyPlanFile(row.id, file as File)
                if (res.code === 200) {
                  message.success('预案文件已上传')
                  onSuccess?.(res)
                  await refreshAll()
                } else {
                  message.error(res.message || '上传失败')
                  onError?.(new Error(res.message))
                }
              } catch (err) {
                message.error(err instanceof Error ? err.message : '上传失败')
                onError?.(err as Error)
              }
            }}
          >
            <Button type="link" size="small" icon={<UploadOutlined />} style={{ padding: 0 }} disabled={!canOperate}>
              上传
            </Button>
          </Upload>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openPlanEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该预案？" onConfirm={() => handlePlanDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // ---------- 应急演练 ----------

  const openDrillCreate = () => {
    setEditingDrill(null)
    drillForm.setFieldsValue({
      name: '',
      drill_type: 'practical',
      scenario: '',
      plan_name: '',
      status: 'planned',
      location: '',
      departments: '',
      summary: '',
      issues: '',
    })
    setDrillFormOpen(true)
  }

  const openDrillEdit = (item: EmergencyDrillItem) => {
    setEditingDrill(item)
    drillForm.setFieldsValue({ ...item })
    setDrillFormOpen(true)
  }

  const submitDrill = async () => {
    const values = await drillForm.validateFields()
    const payload = {
      name: values.name,
      drill_type: values.drill_type,
      scenario: values.scenario ?? '',
      plan_name: values.plan_name ?? '',
      planned_date: values.planned_date || null,
      actual_date: values.actual_date || null,
      location: values.location ?? '',
      departments: values.departments ?? '',
      participants_count: values.participants_count ?? null,
      summary: values.summary ?? '',
      issues: values.issues ?? '',
      status: values.status,
    }
    try {
      const res = editingDrill
        ? await updateEmergencyDrill(editingDrill.id, payload)
        : await createEmergencyDrill(payload)
      if (res.code === 200) {
        message.success(editingDrill ? '演练已更新' : '演练已创建')
        setDrillFormOpen(false)
        await refreshAll()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleDrillDelete = async (item: EmergencyDrillItem) => {
    const res = await deleteEmergencyDrill(item.id)
    if (res.code === 200) {
      message.success('演练记录已删除')
      await refreshAll()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const drillColumns: ColumnsType<EmergencyDrillItem> = [
    {
      title: '演练名称',
      dataIndex: 'name',
      key: 'name',
      render: (v, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          <div>
            <Text style={{ color: T.steel, fontSize: 12 }}>
              {DRILL_TYPE_LABELS[row.drill_type] || row.drill_type}
              {row.scenario ? ` · ${row.scenario}` : ''}
            </Text>
          </div>
        </div>
      ),
    },
    { title: '计划日期', dataIndex: 'planned_date', key: 'planned_date', width: 105, render: (v: string | null) => fmtDate(v) },
    { title: '实际日期', dataIndex: 'actual_date', key: 'actual_date', width: 105, render: (v: string | null) => fmtDate(v) },
    {
      title: '地点/部门',
      key: 'location',
      render: (_, row) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>
          {row.location || '-'}
          {row.departments ? ` · ${row.departments}` : ''}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (v: string) => {
        const meta = DRILL_STATUS_LABELS[v] || { label: v, color: T.steel, bg: T.surface }
        return (
          <Tag style={{ color: meta.color, backgroundColor: meta.bg, border: 'none', borderRadius: 6, fontWeight: 600 }}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openDrillEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该演练记录？" onConfirm={() => handleDrillDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // ---------- 应急物资 ----------

  const openSupplyCreate = () => {
    setEditingSupply(null)
    supplyForm.setFieldsValue({
      name: '',
      category: 'protective',
      spec: '',
      location: '',
      department: '',
      quantity: 0,
      unit: '件',
      status: 'good',
      last_check_result: '',
      remark: '',
    })
    setSupplyFormOpen(true)
  }

  const openSupplyEdit = (item: EmergencySupplyItem) => {
    setEditingSupply(item)
    supplyForm.setFieldsValue({ ...item })
    setSupplyFormOpen(true)
  }

  const submitSupply = async () => {
    const values = await supplyForm.validateFields()
    const payload = {
      name: values.name,
      category: values.category,
      spec: values.spec ?? '',
      location: values.location ?? '',
      department: values.department ?? '',
      quantity: values.quantity,
      unit: values.unit ?? '件',
      status: values.status,
      expiry_date: values.expiry_date || null,
      last_checked_at: values.last_checked_at || null,
      last_check_result: values.last_check_result ?? '',
      remark: values.remark ?? '',
    }
    try {
      const res = editingSupply
        ? await updateEmergencySupply(editingSupply.id, payload)
        : await createEmergencySupply(payload)
      if (res.code === 200) {
        message.success(editingSupply ? '物资已更新' : '物资已创建')
        setSupplyFormOpen(false)
        await refreshAll()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleSupplyDelete = async (item: EmergencySupplyItem) => {
    const res = await deleteEmergencySupply(item.id)
    if (res.code === 200) {
      message.success('物资已删除')
      await refreshAll()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const supplyColumns: ColumnsType<EmergencySupplyItem> = [
    {
      title: '物资名称',
      dataIndex: 'name',
      key: 'name',
      render: (v, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          {row.spec && (
            <div>
              <Text style={{ color: T.steel, fontSize: 12 }}>{row.spec}</Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 90,
      render: (v: string) => (
        <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.surface, color: T.charcoal, fontWeight: 600 }}>
          {SUPPLY_CATEGORY_LABELS[v] || v}
        </Tag>
      ),
    },
    {
      title: '位置/部门',
      key: 'location',
      render: (_, row) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>
          {row.location || '-'}
          {row.department ? ` · ${row.department}` : ''}
        </Text>
      ),
    },
    {
      title: '数量',
      key: 'quantity',
      width: 90,
      render: (_, row) => (
        <Text style={{ color: T.charcoal }}>{row.quantity}{row.unit}</Text>
      ),
    },
    {
      title: '有效期',
      dataIndex: 'expiry_date',
      key: 'expiry_date',
      width: 105,
      render: (v: string | null) => fmtDate(v),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (v: string) => {
        const meta = SUPPLY_STATUS_LABELS[v] || { label: v, color: T.steel, bg: T.surface }
        return (
          <Tag style={{ color: meta.color, backgroundColor: meta.bg, border: 'none', borderRadius: 6, fontWeight: 600 }}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openSupplyEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该物资？" onConfirm={() => handleSupplyDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4 pb-8">
      <div>
        <Title level={4} className="!mb-1">应急管理</Title>
        <Text style={{ color: T.slate, fontSize: 13 }}>
          应急预案台账、演练计划与记录、应急物资管理
        </Text>
      </div>

      {error && (
        <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.error}33` }}>
          <Text style={{ color: T.error }}>{error}</Text>
        </Card>
      )}

      <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
        <Tabs
          defaultActiveKey="plans"
          items={[
            {
              key: 'plans',
              label: '应急预案',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3">
                    <Button type="primary" disabled={!canOperate} onClick={openPlanCreate}>
                      新增预案
                    </Button>
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {plans.length} 项</Text>
                  </div>
                  <Table<EmergencyPlanItem>
                    rowKey="id"
                    columns={planColumns}
                    dataSource={plans}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </>
              ),
            },
            {
              key: 'drills',
              label: '演练计划与记录',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3">
                    <Button type="primary" disabled={!canOperate} onClick={openDrillCreate}>
                      新增演练
                    </Button>
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {drills.length} 项</Text>
                  </div>
                  <Table<EmergencyDrillItem>
                    rowKey="id"
                    columns={drillColumns}
                    dataSource={drills}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </>
              ),
            },
            {
              key: 'supplies',
              label: '应急物资',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3">
                    <Button type="primary" disabled={!canOperate} onClick={openSupplyCreate}>
                      新增物资
                    </Button>
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {supplies.length} 项</Text>
                  </div>
                  <Table<EmergencySupplyItem>
                    rowKey="id"
                    columns={supplyColumns}
                    dataSource={supplies}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editingPlan ? '编辑应急预案' : '新增应急预案'}
        open={planFormOpen}
        onOk={submitPlan}
        onCancel={() => setPlanFormOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form<PlanFormValues> form={planForm} layout="vertical" className="mt-3">
          <Form.Item name="name" label="预案名称" rules={[{ required: true, message: '请填写预案名称' }]}>
            <Input placeholder="如：液氨泄漏专项应急预案" />
          </Form.Item>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="plan_type" label="类型">
              <Select
                options={Object.entries(PLAN_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Form.Item>
            <Form.Item name="version" label="版本号">
              <Input />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                options={Object.entries(PLAN_STATUS_LABELS).map(([value, meta]) => ({
                  value,
                  label: meta.label,
                }))}
              />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="issued_at" label="发布日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="review_due_date" label="下次评审到期日">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="department" label="编制/归口部门">
            <Input />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingDrill ? '编辑演练' : '新增演练'}
        open={drillFormOpen}
        onOk={submitDrill}
        onCancel={() => setDrillFormOpen(false)}
        width={680}
        destroyOnHidden
      >
        <Form<DrillFormValues> form={drillForm} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="name" label="演练名称" rules={[{ required: true, message: '请填写演练名称' }]}>
              <Input />
            </Form.Item>
            <Form.Item name="drill_type" label="类型">
              <Select
                options={Object.entries(DRILL_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="scenario" label="演练情景">
              <Input placeholder="如 液氨泄漏、火灾疏散" />
            </Form.Item>
            <Form.Item name="plan_name" label="对应预案">
              <Input />
            </Form.Item>
          </div>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="planned_date" label="计划日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="actual_date" label="实际日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="participants_count" label="参演人数">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="location" label="演练地点">
              <Input />
            </Form.Item>
            <Form.Item name="departments" label="参演部门">
              <Input placeholder="顿号分隔" />
            </Form.Item>
          </div>
          <Form.Item name="status" label="状态">
            <Select
              options={Object.entries(DRILL_STATUS_LABELS).map(([value, meta]) => ({
                value,
                label: meta.label,
              }))}
            />
          </Form.Item>
          <Form.Item name="summary" label="演练总结">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="issues" label="问题与改进">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingSupply ? '编辑应急物资' : '新增应急物资'}
        open={supplyFormOpen}
        onOk={submitSupply}
        onCancel={() => setSupplyFormOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form<SupplyFormValues> form={supplyForm} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="name" label="物资名称" rules={[{ required: true, message: '请填写物资名称' }]}>
              <Input placeholder="如 正压式空气呼吸器" />
            </Form.Item>
            <Form.Item name="category" label="类别">
              <Select
                options={Object.entries(SUPPLY_CATEGORY_LABELS).map(([value, label]) => ({ value, label }))}
              />
            </Form.Item>
          </div>
          <Form.Item name="spec" label="规格型号">
            <Input />
          </Form.Item>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="location" label="存放位置">
              <Input />
            </Form.Item>
            <Form.Item name="department" label="管理部门">
              <Input />
            </Form.Item>
          </div>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="unit" label="单位">
              <Input />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                options={Object.entries(SUPPLY_STATUS_LABELS).map(([value, meta]) => ({
                  value,
                  label: meta.label,
                }))}
              />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="expiry_date" label="有效期至">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="last_checked_at" label="最近检查日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="last_check_result" label="最近检查结论">
            <Input />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
