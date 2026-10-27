'use client'

import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Segmented,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createSafetyFacility,
  deleteSafetyFacility,
  getSafetyFacilities,
  getSafetyFacilityChecklist,
  getSafetyFacilityInspections,
  getSafetyFacilityStats,
  submitSafetyFacilityInspection,
  updateSafetyFacility,
  type SafetyFacilityChecklistData,
  type SafetyFacilityInspectionItem,
  type SafetyFacilityItem,
  type SafetyFacilityStatsData,
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
  yellow: '#fef7d6',
}

export const FACILITY_CATEGORY_LABELS: Record<string, string> = {
  eyewash: '洗眼器',
  gas_detector: '气体检测仪',
  protective: '防护设施',
  other: '其他',
}

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  normal: { label: '完好', color: T.success, bg: T.mint },
  damaged: { label: '损坏', color: T.error, bg: T.rose },
  scrapped: { label: '报废', color: T.steel, bg: T.surface },
}

interface FormValues {
  category: string
  facility_no?: string
  name: string
  model_spec?: string
  department?: string
  location?: string
  installed_at?: string | null
  expiry_date?: string | null
  status: string
  remark?: string
}

interface InspectionFormValues {
  answers: Record<string, { result: 'ok' | 'fail'; remark?: string }>
  abnormal_action?: string
  inspector_name?: string
}

function fmtDate(value?: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleDateString('zh-CN')
}

export default function SafetyFacilityPanel({
  pageKey,
  initialFacilities,
  initialStats,
  initialRecords,
  initialError,
}: {
  pageKey: string
  initialFacilities: SafetyFacilityItem[]
  initialStats: SafetyFacilityStatsData | null
  initialRecords: SafetyFacilityInspectionItem[]
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()

  const [facilities, setFacilities] = useState<SafetyFacilityItem[]>(initialFacilities)
  const [total, setTotal] = useState(initialFacilities.length)
  const [stats, setStats] = useState<SafetyFacilityStatsData | null>(initialStats)
  const [records, setRecords] = useState<SafetyFacilityInspectionItem[]>(initialRecords)
  const [error, setError] = useState<string | null>(initialError)
  const [loading, setLoading] = useState(false)

  const [category, setCategory] = useState<string>('all')
  const [expiryStatus, setExpiryStatus] = useState<string>('all')
  const [keyword, setKeyword] = useState('')

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SafetyFacilityItem | null>(null)
  const [form] = Form.useForm<FormValues>()

  const [inspectionTarget, setInspectionTarget] = useState<SafetyFacilityItem | null>(null)
  const [checklist, setChecklist] = useState<SafetyFacilityChecklistData | null>(null)
  const [answers, setAnswers] = useState<Record<string, 'ok' | 'fail'>>({})
  const [abnormalAction, setAbnormalAction] = useState('')
  const [detailTarget, setDetailTarget] = useState<SafetyFacilityItem | null>(null)
  const [detailRecords, setDetailRecords] = useState<SafetyFacilityInspectionItem[]>([])

  useEffect(() => {
    setFacilities(initialFacilities)
    setTotal(initialFacilities.length)
    setStats(initialStats)
    setRecords(initialRecords)
    setError(initialError)
  }, [initialFacilities, initialStats, initialRecords, initialError])

  const refresh = async (
    nextCategory = category,
    nextExpiry = expiryStatus,
    nextKeyword = keyword
  ) => {
    setLoading(true)
    try {
      const res = await getSafetyFacilities({
        category: nextCategory === 'all' ? undefined : nextCategory,
        expiry_status: nextExpiry === 'all' ? undefined : nextExpiry,
        keyword: nextKeyword || undefined,
        page_size: 200,
      })
      if (res.code === 200 && res.data) {
        setFacilities(res.data.items)
        setTotal(res.data.total)
        setError(null)
      } else {
        setError(res.message || '加载安全设施失败')
      }
      const statsRes = await getSafetyFacilityStats()
      if (statsRes.code === 200) setStats(statsRes.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载安全设施失败')
    } finally {
      setLoading(false)
    }
  }

  const refreshRecords = async () => {
    const res = await getSafetyFacilityInspections({ page_size: 50 })
    if (res.code === 200 && res.data) setRecords(res.data.items)
  }

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      category: 'eyewash',
      facility_no: '',
      name: '',
      model_spec: '',
      department: '',
      location: '',
      status: 'normal',
      remark: '',
    })
    setFormOpen(true)
  }

  const openEdit = (item: SafetyFacilityItem) => {
    setEditing(item)
    form.setFieldsValue({ ...item })
    setFormOpen(true)
  }

  const submitForm = async () => {
    const values = await form.validateFields()
    const payload = {
      category: values.category,
      facility_no: values.facility_no ?? '',
      name: values.name,
      model_spec: values.model_spec ?? '',
      department: values.department ?? '',
      location: values.location ?? '',
      installed_at: values.installed_at || null,
      expiry_date: values.expiry_date || null,
      status: values.status,
      remark: values.remark ?? '',
    }
    try {
      const res = editing
        ? await updateSafetyFacility(editing.id, payload)
        : await createSafetyFacility(payload)
      if (res.code === 200) {
        message.success(editing ? '设施已更新' : '设施已创建')
        setFormOpen(false)
        await refresh()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const openInspection = async (item: SafetyFacilityItem) => {
    setInspectionTarget(item)
    setAnswers({})
    setAbnormalAction('')
    const res = await getSafetyFacilityChecklist(item.category)
    if (res.code === 200 && res.data) setChecklist(res.data)
    else message.error(res.message || '获取点检卡失败')
  }

  const submitInspection = async () => {
    if (!inspectionTarget || !checklist) return
    const checklistItems = checklist.items ?? []
    const items = checklistItems.map((item) => ({
      key: item.key,
      label: item.label,
      result: answers[item.key] ?? 'ok',
      remark: '',
    }))
    const missing = checklistItems.filter((item) => !answers[item.key])
    if (missing.length > 0) {
      message.warning(`还有 ${missing.length} 项未选择结论`)
      return
    }
    try {
      const res = await submitSafetyFacilityInspection(inspectionTarget.id, {
        items,
        abnormal_action: abnormalAction,
        inspector_name: '',
      })
      if (res.code === 200) {
        message.success('点检已提交')
        setInspectionTarget(null)
        await refresh()
        await refreshRecords()
      } else {
        message.error(res.message || '提交失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '提交失败')
    }
  }

  const handleDelete = async (item: SafetyFacilityItem) => {
    const res = await deleteSafetyFacility(item.id)
    if (res.code === 200) {
      message.success('设施已删除')
      await refresh()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const openDetail = async (item: SafetyFacilityItem) => {
    setDetailTarget(item)
    const res = await getSafetyFacilityInspections({ facility_id: item.id, page_size: 20 })
    if (res.code === 200 && res.data) setDetailRecords(res.data.items)
    else setDetailRecords([])
  }

  const columns: ColumnsType<SafetyFacilityItem> = [
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (v: string) => (
        <Tag style={{ borderRadius: 6, border: 'none', backgroundColor: T.surface, color: T.charcoal, fontWeight: 600 }}>
          {FACILITY_CATEGORY_LABELS[v] || v}
        </Tag>
      ),
    },
    {
      title: '编号/名称',
      key: 'name',
      render: (_, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{row.name}</Text>
          {row.facility_no && (
            <div>
              <Text style={{ color: T.steel, fontSize: 12, fontFamily: 'monospace' }}>{row.facility_no}</Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '部门/位置',
      key: 'location',
      render: (_, row) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>
          {row.department || '-'} · {row.location || '-'}
        </Text>
      ),
    },
    {
      title: '到期日',
      dataIndex: 'expiry_date',
      key: 'expiry_date',
      width: 110,
      render: (v: string | null) => {
        if (!v) return <Text style={{ color: T.muted }}>-</Text>
        const days = Math.ceil((new Date(v).getTime() - Date.now()) / 86400000)
        const expired = days < 0
        const soon = days >= 0 && days <= 90
        return (
          <Tag
            style={{
              borderRadius: 6,
              border: 'none',
              fontWeight: 600,
              backgroundColor: expired ? T.rose : soon ? T.yellow : T.surface,
              color: expired ? T.error : soon ? T.warning : T.steel,
            }}
          >
            {fmtDate(v)}（{expired ? '已过期' : `${days}天`}）
          </Tag>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (v: string) => {
        const meta = STATUS_META[v] || { label: v, color: T.steel, bg: T.surface }
        return (
          <Tag style={{ color: meta.color, backgroundColor: meta.bg, border: 'none', borderRadius: 6, fontWeight: 600 }}>
            {meta.label}
          </Tag>
        )
      },
    },
    {
      title: '最近点检',
      key: 'last_inspection',
      width: 130,
      render: (_, row) =>
        row.last_inspected_at ? (
          <div>
            <Text style={{ fontSize: 12, color: T.charcoal }}>{fmtDate(row.last_inspected_at)}</Text>
            <div>
              <Text style={{ fontSize: 11, color: row.last_inspection_result === 'fail' ? T.error : T.success }}>
                {row.last_inspection_result === 'fail' ? '存在异常' : '正常'}
              </Text>
            </div>
          </div>
        ) : (
          <Text style={{ color: T.muted, fontSize: 12 }}>未点检</Text>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 210,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => openDetail(row)}>
            明细
          </Button>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openInspection(row)}>
            点检
          </Button>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该设施？" onConfirm={() => handleDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const recordColumns: ColumnsType<SafetyFacilityInspectionItem> = [
    { title: '设施', dataIndex: 'facility_name', key: 'facility_name' },
    {
      title: '结论',
      dataIndex: 'result',
      key: 'result',
      width: 90,
      render: (v: string) => (
        <Tag
          style={{
            borderRadius: 6,
            border: 'none',
            fontWeight: 600,
            backgroundColor: v === 'pass' ? T.mint : T.rose,
            color: v === 'pass' ? T.success : T.error,
          }}
        >
          {v === 'pass' ? '正常' : '异常'}
        </Tag>
      ),
    },
    { title: '点检人', dataIndex: 'inspector_name', key: 'inspector_name', width: 100 },
    {
      title: '时间',
      dataIndex: 'inspected_at',
      key: 'inspected_at',
      width: 150,
      render: (v: string) => new Date(v).toLocaleString('zh-CN'),
    },
    {
      title: '异常处理',
      dataIndex: 'abnormal_action',
      key: 'abnormal_action',
      ellipsis: true,
    },
  ]

  return (
    <div className="space-y-4 pb-8">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title level={4} className="!mb-1">安全设施台账</Title>
          <Text style={{ color: T.slate, fontSize: 13 }}>
            洗眼器 / 气体检测仪 / 防护设施等安全设备设施台账、点检与到期管理
          </Text>
        </div>
        <Button type="primary" disabled={!canOperate} onClick={openCreate}>
          新增安全设施
        </Button>
      </div>

      {stats && (
        <Card variant="borderless" size="small" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-lg p-3" style={{ backgroundColor: T.surface }}>
              <Text style={{ color: T.slate, fontSize: 12 }}>设施总数</Text>
              <div className="text-2xl font-semibold" style={{ color: T.charcoal }}>{stats.total}</div>
            </div>
            <div className="rounded-lg p-3" style={{ backgroundColor: T.surface }}>
              <Text style={{ color: T.slate, fontSize: 12 }}>90 天内到期</Text>
              <div className="text-2xl font-semibold" style={{ color: T.warning }}>{stats.expiring_in_90d}</div>
            </div>
            <div className="rounded-lg p-3" style={{ backgroundColor: T.surface }}>
              <Text style={{ color: T.slate, fontSize: 12 }}>最近点检异常</Text>
              <div className="text-2xl font-semibold" style={{ color: T.error }}>{stats.failed_recent}</div>
            </div>
            <div className="rounded-lg p-3" style={{ backgroundColor: T.surface }}>
              <Text style={{ color: T.slate, fontSize: 12 }}>损坏/报废</Text>
              <div className="text-2xl font-semibold" style={{ color: T.steel }}>
                {(stats.by_status?.damaged ?? 0) + (stats.by_status?.scrapped ?? 0)}
              </div>
            </div>
          </div>
        </Card>
      )}

      {error && (
        <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.error}33` }}>
          <Text style={{ color: T.error }}>{error}</Text>
        </Card>
      )}

      <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
        <Tabs
          defaultActiveKey="facilities"
          items={[
            {
              key: 'facilities',
              label: '设施台账',
              children: (
                <>
                  <div className="flex items-center gap-3 mb-3 flex-wrap">
                    <Segmented
                      value={category}
                      onChange={(v) => {
                        setCategory(v as string)
                        refresh(v as string, expiryStatus, keyword)
                      }}
                      options={[
                        { label: '全部', value: 'all' },
                        { label: '洗眼器', value: 'eyewash' },
                        { label: '气体检测仪', value: 'gas_detector' },
                        { label: '防护设施', value: 'protective' },
                        { label: '其他', value: 'other' },
                      ]}
                    />
                    <Segmented
                      value={expiryStatus}
                      onChange={(v) => {
                        setExpiryStatus(v as string)
                        refresh(category, v as string, keyword)
                      }}
                      options={[
                        { label: '全部', value: 'all' },
                        { label: '90天内到期', value: 'expiring' },
                        { label: '已过期', value: 'expired' },
                      ]}
                    />
                    <Input.Search
                      placeholder="搜索名称/编号/位置"
                      allowClear
                      style={{ maxWidth: 240 }}
                      onSearch={(v) => {
                        setKeyword(v)
                        refresh(category, expiryStatus, v)
                      }}
                    />
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {total} 台</Text>
                  </div>
                  <Table<SafetyFacilityItem>
                    rowKey="id"
                    columns={columns}
                    dataSource={facilities}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </>
              ),
            },
            {
              key: 'records',
              label: '点检记录',
              children: (
                <Table<SafetyFacilityInspectionItem>
                  rowKey="id"
                  columns={recordColumns}
                  dataSource={records}
                  pagination={{ pageSize: 20, showSizeChanger: false }}
                  size="middle"
                  expandable={{
                    expandedRowRender: (record) => (
                      <div className="space-y-1 pl-2">
                        {(record.items ?? []).map((item) => (
                          <div key={item.key} className="flex items-center gap-2">
                            <Tag
                              style={{
                                margin: 0,
                                borderRadius: 6,
                                border: 'none',
                                fontSize: 11,
                                fontWeight: 600,
                                backgroundColor: item.result === 'ok' ? T.mint : T.rose,
                                color: item.result === 'ok' ? T.success : T.error,
                              }}
                            >
                              {item.result === 'ok' ? '正常' : '异常'}
                            </Tag>
                            <Text style={{ fontSize: 12, color: T.charcoal }}>{item.label}</Text>
                            {item.remark && (
                              <Text style={{ fontSize: 12, color: T.steel }}>{item.remark}</Text>
                            )}
                          </div>
                        ))}
                      </div>
                    ),
                  }}
                />
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? '编辑安全设施' : '新增安全设施'}
        open={formOpen}
        onOk={submitForm}
        onCancel={() => setFormOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form<FormValues> form={form} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="category" label="类别" rules={[{ required: true }]}>
              <Select
                options={Object.entries(FACILITY_CATEGORY_LABELS).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
            </Form.Item>
            <Form.Item name="facility_no" label="设施编号">
              <Input placeholder="如 EYW-101-001" />
            </Form.Item>
          </div>
          <Form.Item name="name" label="设施名称" rules={[{ required: true, message: '请填写设施名称' }]}>
            <Input />
          </Form.Item>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="department" label="所属部门/车间">
              <Input />
            </Form.Item>
            <Form.Item name="location" label="安装位置">
              <Input />
            </Form.Item>
          </div>
          <Form.Item name="model_spec" label="型号规格">
            <Input />
          </Form.Item>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="installed_at" label="投用日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="expiry_date" label="校准/报废到期日">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                options={[
                  { label: '完好', value: 'normal' },
                  { label: '损坏', value: 'damaged' },
                  { label: '报废', value: 'scrapped' },
                ]}
              />
            </Form.Item>
          </div>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`设施点检 · ${inspectionTarget?.name ?? ''}`}
        open={inspectionTarget !== null}
        onOk={submitInspection}
        onCancel={() => setInspectionTarget(null)}
        width={560}
        destroyOnHidden
      >
        <div className="mt-3 space-y-3">
          {(checklist?.items ?? []).map((item) => (
            <div
              key={item.key}
              className="flex items-center justify-between rounded-lg px-3 py-2"
              style={{ backgroundColor: T.surface }}
            >
              <Text style={{ color: T.charcoal }}>{item.label}</Text>
              <Radio.Group
                size="small"
                value={answers[item.key]}
                onChange={(e) =>
                  setAnswers((prev) => ({ ...prev, [item.key]: e.target.value }))
                }
                options={[
                  { label: '正常', value: 'ok' },
                  { label: '异常', value: 'fail' },
                ]}
                optionType="button"
              />
            </div>
          ))}
          <div>
            <Text style={{ color: T.slate, fontSize: 12 }}>异常处理措施（有异常时必填说明）</Text>
            <Input.TextArea
              rows={2}
              value={abnormalAction}
              onChange={(e) => setAbnormalAction(e.target.value)}
              placeholder="如：已报修/更换探头/停用待检"
              className="mt-1"
            />
          </div>
        </div>
      </Modal>

      <Drawer
        title={detailTarget ? `${detailTarget.name} 点检明细` : null}
        placement="right"
        width={560}
        open={detailTarget !== null}
        onClose={() => setDetailTarget(null)}
      >
        {detailTarget && (
          <div className="space-y-4">
            <Card variant="borderless" size="small" style={{ backgroundColor: T.surface, borderRadius: 10 }}>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <Text style={{ color: T.slate }}>编号</Text>
                <Text style={{ color: T.charcoal }}>{detailTarget.facility_no || '-'}</Text>
                <Text style={{ color: T.slate }}>位置</Text>
                <Text style={{ color: T.charcoal }}>{detailTarget.location || '-'}</Text>
                <Text style={{ color: T.slate }}>投用日期</Text>
                <Text style={{ color: T.charcoal }}>{fmtDate(detailTarget.installed_at)}</Text>
                <Text style={{ color: T.slate }}>到期日期</Text>
                <Text style={{ color: T.charcoal }}>{fmtDate(detailTarget.expiry_date)}</Text>
              </div>
            </Card>
            <Table<SafetyFacilityInspectionItem>
              rowKey="id"
              columns={recordColumns}
              dataSource={detailRecords}
              pagination={false}
              size="small"
            />
          </div>
        )}
      </Drawer>
    </div>
  )
}
