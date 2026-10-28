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
  createSafetyTarget,
  deleteSafetyTarget,
  deleteSafetyTargetRecord,
  getSafetyTargets,
  getSafetyTargetStats,
  updateSafetyTarget,
  upsertSafetyTargetRecord,
  type SafetyDutyAssessmentItemData,
  type SafetyDutyAssessmentStatsData,
  type SafetyTargetAgreementItem,
  type SafetyTargetAgreementStatsData,
  type SafetyTargetItem,
  type SafetyTargetStatsData,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import TargetAgreementPanel from './TargetAgreementPanel'
import DutyAssessmentPanel from './DutyAssessmentPanel'

const { Text, Title } = Typography

const T = {
  primary: '#5645d4',
  error: '#E03131',
  warning: '#DD5B00',
  success: '#1AAE39',
  charcoal: '#37352f',
  slate: '#5d5b54',
  steel: '#787671',
  muted: '#bbb8b1',
  hairline: '#e5e3df',
  surface: '#f6f5f4',
  canvas: '#ffffff',
  mint: '#d9f3e1',
  peach: '#ffe8d4',
  rose: '#fde0ec',
  lavender: '#e6e0f5',
  sky: '#dcecfa',
}

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  in_progress: { label: '进行中', color: T.primary, bg: T.lavender },
  achieved: { label: '已达成', color: T.success, bg: T.mint },
  not_achieved: { label: '未达成', color: T.error, bg: T.rose },
}

const CATEGORY_OPTIONS = [
  '事故控制',
  '隐患治理',
  '培训教育',
  '职业健康',
  '消防应急',
  '设备设施',
  '其他',
]

const CURRENT_YEAR = new Date().getFullYear()

interface FormValues {
  year: number
  title: string
  category: string
  metric?: string
  target_value?: string
  unit?: string
  owner_department?: string
  owner_name?: string
  deadline?: string | null
  status: string
  remark?: string
}

interface RecordFormValues {
  period: string
  actual_value?: string
  completion_pct?: number | null
  note?: string
}

export default function TargetPerformancePanel({
  pageKey,
  initialTargets,
  initialStats,
  initialAgreements,
  initialAgreementStats,
  initialAssessments,
  initialAssessmentStats,
  initialError,
}: {
  pageKey: string
  initialTargets: SafetyTargetItem[]
  initialStats: SafetyTargetStatsData | null
  initialAgreements: SafetyTargetAgreementItem[]
  initialAgreementStats: SafetyTargetAgreementStatsData | null
  initialAssessments: SafetyDutyAssessmentItemData[]
  initialAssessmentStats: SafetyDutyAssessmentStatsData | null
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()
  const [targets, setTargets] = useState<SafetyTargetItem[]>(initialTargets)
  const [total, setTotal] = useState(initialTargets.length)
  const [stats, setStats] = useState<SafetyTargetStatsData | null>(initialStats)
  const [year, setYear] = useState<number>(CURRENT_YEAR)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(initialError)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SafetyTargetItem | null>(null)
  const [targetForm] = Form.useForm<FormValues>()
  const [recordForm] = Form.useForm<RecordFormValues>()
  const [recordTarget, setRecordTarget] = useState<SafetyTargetItem | null>(null)

  useEffect(() => {
    setTargets(initialTargets)
    setTotal(initialTargets.length)
    setStats(initialStats)
    setError(initialError)
  }, [initialTargets, initialStats, initialError])

  const refresh = async (nextYear = year, nextStatus = statusFilter, nextKeyword = keyword) => {
    setLoading(true)
    try {
      const res = await getSafetyTargets({
        year: nextYear,
        status: nextStatus === 'all' ? undefined : nextStatus,
        keyword: nextKeyword || undefined,
        page_size: 200,
      })
      if (res.code === 200 && res.data) {
        setTargets(res.data.items)
        setTotal(res.data.total)
        setError(null)
      } else {
        setError(res.message || '加载安全目标失败')
      }
      const statsRes = await getSafetyTargetStats(nextYear)
      if (statsRes.code === 200) setStats(statsRes.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载安全目标失败')
    } finally {
      setLoading(false)
    }
  }

  const openCreate = () => {
    setEditing(null)
    targetForm.setFieldsValue({
      year: CURRENT_YEAR,
      title: '',
      category: '事故控制',
      metric: '',
      target_value: '',
      unit: '',
      owner_department: '',
      owner_name: '',
      status: 'in_progress',
      remark: '',
    })
    setFormOpen(true)
  }

  const openEdit = (item: SafetyTargetItem) => {
    setEditing(item)
    targetForm.setFieldsValue({ ...item })
    setFormOpen(true)
  }

  const submitForm = async () => {
    const values = await targetForm.validateFields()
    const payload = {
      year: values.year,
      title: values.title,
      category: values.category,
      metric: values.metric ?? '',
      target_value: values.target_value ?? '',
      unit: values.unit ?? '',
      owner_department: values.owner_department ?? '',
      owner_name: values.owner_name ?? '',
      deadline: values.deadline || null,
      status: values.status,
      remark: values.remark ?? '',
    }
    try {
      const res = editing
        ? await updateSafetyTarget(editing.id, payload)
        : await createSafetyTarget(payload)
      if (res.code === 200) {
        message.success(editing ? '目标已更新' : '目标已创建')
        setFormOpen(false)
        await refresh()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const submitRecord = async () => {
    if (!recordTarget) return
    const values = await recordForm.validateFields()
    try {
      const res = await upsertSafetyTargetRecord(recordTarget.id, values.period, {
        actual_value: values.actual_value || '',
        completion_pct: values.completion_pct ?? null,
        note: values.note || '',
      })
      if (res.code === 200) {
        message.success('进度已保存')
        setRecordTarget(null)
        await refresh()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleDelete = async (item: SafetyTargetItem) => {
    const res = await deleteSafetyTarget(item.id)
    if (res.code === 200) {
      message.success('目标已删除')
      await refresh()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const handleDeleteRecord = async (targetId: string, period: string) => {
    const res = await deleteSafetyTargetRecord(targetId, period)
    if (res.code === 200) {
      message.success('进度记录已删除')
      await refresh()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const columns: ColumnsType<SafetyTargetItem> = [
    { title: '年度', dataIndex: 'year', key: 'year', width: 70 },
    {
      title: '目标名称',
      dataIndex: 'title',
      key: 'title',
      render: (v, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{v}</Text>
          <div>
            <Text style={{ color: T.steel, fontSize: 12 }}>
              {row.category}
              {row.target_value ? ` · 目标 ${row.target_value}${row.unit}` : ''}
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: '责任部门/人',
      key: 'owner',
      width: 150,
      render: (_, row) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>
          {row.owner_department || '-'}
          {row.owner_name ? ` / ${row.owner_name}` : ''}
        </Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
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
      title: '进度记录',
      key: 'records',
      width: 220,
      render: (_, row) => (
        <div className="space-y-0.5">
          {(row.records ?? []).length === 0 && (
            <Text style={{ color: T.muted, fontSize: 12 }}>暂无录入</Text>
          )}
          {(row.records ?? []).slice(-2).map((rec) => (
            <div key={rec.id} className="flex items-center gap-2">
              <Text style={{ color: T.steel, fontSize: 12 }}>{rec.period}</Text>
              <Text style={{ color: T.charcoal, fontSize: 12 }}>{rec.actual_value || '-'}</Text>
              {rec.completion_pct !== null && rec.completion_pct !== undefined && (
                <Tag style={{ fontSize: 11, borderRadius: 6, border: 'none', backgroundColor: T.sky, color: T.primary, margin: 0 }}>
                  {rec.completion_pct}%
                </Tag>
              )}
              {canOperate && (
                <Popconfirm
                  title="删除该条进度记录？"
                  onConfirm={() => handleDeleteRecord(row.id, rec.period)}
                >
                  <Button type="link" size="small" danger disabled={!canDelete} style={{ padding: 0, fontSize: 11 }}>
                    删
                  </Button>
                </Popconfirm>
              )}
            </div>
          ))}
        </div>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, row) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            style={{ padding: 0 }}
            disabled={!canOperate}
            onClick={() => {
              setRecordTarget(row)
              recordForm.setFieldsValue({ period: `${CURRENT_YEAR}-Q1`, actual_value: '', completion_pct: null, note: '' })
            }}
          >
            录入进度
          </Button>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该安全目标？" onConfirm={() => handleDelete(row)} disabled={!canDelete}>
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
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title level={4} className="!mb-1">目标责任与绩效</Title>
          <Text style={{ color: T.slate, fontSize: 13 }}>
            年度安全目标台账 · 安全目标责任书逐级签订 · 安全生产责任制季度考核（依据 2026 安全目标责任书与责任制考核表）
          </Text>
        </div>
      </div>

      <Tabs
        defaultActiveKey="targets"
        items={[
          {
            key: 'targets',
            label: '安全目标台账',
            children: (
              <div className="space-y-4">
                <div className="flex justify-end">
                  <Button type="primary" disabled={!canOperate} onClick={openCreate}>
                    新增安全目标
                  </Button>
                </div>
                {stats && (
                  <Card variant="borderless" size="small" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {[
                        { label: '目标总数', value: stats.total, color: T.primary },
                        { label: '已达成', value: stats.achieved, color: T.success },
                        { label: '进行中', value: stats.in_progress, color: T.warning },
                        { label: '未达成', value: stats.not_achieved, color: T.error },
                      ].map((item) => (
                        <div key={item.label} className="rounded-lg p-3" style={{ backgroundColor: T.surface }}>
                          <Text style={{ color: T.slate, fontSize: 12 }}>{item.label}</Text>
                          <div className="text-2xl font-semibold" style={{ color: item.color }}>{item.value}</div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {error && (
                  <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.error}33` }}>
                    <Text style={{ color: T.error }}>{error}</Text>
                  </Card>
                )}

                <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
                  <div className="flex items-center gap-3 mb-3 flex-wrap">
                    <Segmented
                      value={year}
                      onChange={(v) => {
                        setYear(v as number)
                        refresh(v as number, statusFilter, keyword)
                      }}
                      options={[CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1]}
                    />
                    <Segmented
                      value={statusFilter}
                      onChange={(v) => {
                        setStatusFilter(v as string)
                        refresh(year, v as string, keyword)
                      }}
                      options={[
                        { label: '全部', value: 'all' },
                        { label: '进行中', value: 'in_progress' },
                        { label: '已达成', value: 'achieved' },
                        { label: '未达成', value: 'not_achieved' },
                      ]}
                    />
                    <Input.Search
                      placeholder="搜索目标名称/指标"
                      allowClear
                      style={{ maxWidth: 260 }}
                      onSearch={(v) => {
                        setKeyword(v)
                        refresh(year, statusFilter, v)
                      }}
                    />
                    <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {total} 条</Text>
                  </div>
                  <Table<SafetyTargetItem>
                    rowKey="id"
                    columns={columns}
                    dataSource={targets}
                    loading={loading}
                    pagination={{ pageSize: 20, showSizeChanger: false }}
                    size="middle"
                  />
                </Card>
              </div>
            ),
          },
          {
            key: 'agreements',
            label: '责任书签订',
            children: (
              <TargetAgreementPanel
                pageKey={pageKey}
                initialAgreements={initialAgreements}
                initialStats={initialAgreementStats}
                initialError={initialError}
              />
            ),
          },
          {
            key: 'assessments',
            label: '季度考核',
            children: (
              <DutyAssessmentPanel
                pageKey={pageKey}
                initialAssessments={initialAssessments}
                initialStats={initialAssessmentStats}
                initialError={initialError}
              />
            ),
          },
        ]}
      />

      <Modal
        title={editing ? '编辑安全目标' : '新增安全目标'}
        open={formOpen}
        onOk={submitForm}
        onCancel={() => setFormOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form<FormValues> form={targetForm} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="year" label="年度" rules={[{ required: true, message: '请填写年度' }]}>
              <InputNumber min={2000} max={2100} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="category" label="目标类别" rules={[{ required: true }]}>
              <Select options={CATEGORY_OPTIONS.map((c) => ({ label: c, value: c }))} />
            </Form.Item>
          </div>
          <Form.Item name="title" label="目标名称" rules={[{ required: true, message: '请填写目标名称' }]}>
            <Input placeholder="如：杜绝重伤及以上人身事故" />
          </Form.Item>
          <div className="grid grid-cols-3 gap-x-4">
            <Form.Item name="target_value" label="目标值">
              <Input placeholder="如：0" />
            </Form.Item>
            <Form.Item name="unit" label="单位">
              <Input placeholder="起 / % / 项" />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                options={[
                  { label: '进行中', value: 'in_progress' },
                  { label: '已达成', value: 'achieved' },
                  { label: '未达成', value: 'not_achieved' },
                ]}
              />
            </Form.Item>
          </div>
          <Form.Item name="metric" label="考核指标说明">
            <Input.TextArea rows={2} placeholder="如何量化考核" />
          </Form.Item>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item name="owner_department" label="责任部门">
              <Input />
            </Form.Item>
            <Form.Item name="owner_name" label="责任人">
              <Input />
            </Form.Item>
          </div>
          <Form.Item name="deadline" label="完成时限">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`录入进度 · ${recordTarget?.title ?? ''}`}
        open={recordTarget !== null}
        onOk={submitRecord}
        onCancel={() => setRecordTarget(null)}
        destroyOnHidden
      >
        <Form<RecordFormValues> form={recordForm} layout="vertical" className="mt-3">
          <Form.Item
            name="period"
            label="考核期"
            rules={[{ required: true, message: '如 2026-Q1 或 2026-03' }]}
            extra="同一考核期重复保存将覆盖原记录"
          >
            <Input placeholder="2026-Q1 / 2026-03" />
          </Form.Item>
          <Form.Item name="actual_value" label="实际完成值">
            <Input placeholder="如：0 起 / 96%" />
          </Form.Item>
          <Form.Item name="completion_pct" label="完成率（%）">
            <InputNumber min={0} max={1000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="情况说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
