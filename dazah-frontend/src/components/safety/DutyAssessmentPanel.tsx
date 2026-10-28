'use client'

import { useMemo, useState } from 'react'
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
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createSafetyDutyAssessment,
  deleteSafetyDutyAssessment,
  downloadDutyAssessmentImportTemplate,
  getSafetyDutyAssessmentStats,
  getSafetyDutyAssessments,
  getSafetyDutyAssessmentTemplate,
  importDutyAssessmentResults,
  updateSafetyDutyAssessment,
  type SafetyDutyAssessmentItemData,
  type SafetyDutyAssessmentStatsData,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import PlatformNotice from '@/components/shared/PlatformNotice'
import TargetImportModal from './TargetImportModal'

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
  mint: '#d9f3e1',
  peach: '#ffe8d4',
  rose: '#fde0ec',
  lavender: '#e6e0f5',
  sky: '#dcecfa',
}

const GRADE_META: Record<string, { color: string; bg: string }> = {
  优秀: { color: T.success, bg: T.mint },
  良好: { color: T.primary, bg: T.lavender },
  合格: { color: T.warning, bg: T.peach },
  不合格: { color: T.error, bg: T.rose },
}

const CURRENT_YEAR = new Date().getFullYear()

interface ItemFormValues {
  content: string
  rule?: string
  standard_score: number
  deduction_score: number
  remark?: string
}

interface AssessmentFormValues {
  year: number
  quarter: number
  department: string
  person_name?: string
  assessor?: string
  assessment_date?: string | null
  remark?: string
  items: ItemFormValues[]
}

function gradeForScore(score: number): string {
  if (score >= 95) return '优秀'
  if (score >= 90) return '良好'
  if (score >= 80) return '合格'
  return '不合格'
}

function itemScore(item: ItemFormValues): number {
  return Math.max(0, (item.standard_score || 0) - (item.deduction_score || 0))
}

export default function DutyAssessmentPanel({
  pageKey,
  initialAssessments,
  initialStats,
  initialError,
}: {
  pageKey: string
  initialAssessments: SafetyDutyAssessmentItemData[]
  initialStats: SafetyDutyAssessmentStatsData | null
  initialError: string | null
}) {
  const { canOperate, canDelete } = usePagePermissions(pageKey)
  const { message } = App.useApp()
  const [assessments, setAssessments] =
    useState<SafetyDutyAssessmentItemData[]>(initialAssessments)
  const [total, setTotal] = useState(initialAssessments.length)
  const [stats, setStats] = useState<SafetyDutyAssessmentStatsData | null>(initialStats)
  const [year, setYear] = useState<number>(CURRENT_YEAR)
  const [quarterFilter, setQuarterFilter] = useState<string>('all')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(initialError)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SafetyDutyAssessmentItemData | null>(null)
  const [templateLoading, setTemplateLoading] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importYear, setImportYear] = useState<number>(CURRENT_YEAR)
  const [importQuarter, setImportQuarter] = useState<number>(1)
  const [form] = Form.useForm<AssessmentFormValues>()
  const itemsValue = Form.useWatch('items', form)

  const computedTotal = useMemo(() => {
    const items = (itemsValue as ItemFormValues[] | undefined) ?? []
    return round1(items.reduce((sum, item) => sum + itemScore(item), 0))
  }, [itemsValue])

  const previewGrade = gradeForScore(computedTotal)

  const refresh = async (
    nextYear = year,
    nextQuarter = quarterFilter,
    nextKeyword = keyword
  ) => {
    setLoading(true)
    try {
      const res = await getSafetyDutyAssessments({
        year: nextYear,
        quarter: nextQuarter === 'all' ? undefined : Number(nextQuarter),
        keyword: nextKeyword || undefined,
        page_size: 200,
      })
      if (res.code === 200 && res.data) {
        setAssessments(res.data.items)
        setTotal(res.data.total)
        setError(null)
      } else {
        setError(res.message || '加载考核记录失败')
      }
      const statsRes = await getSafetyDutyAssessmentStats(nextYear)
      if (statsRes.code === 200) setStats(statsRes.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载考核记录失败')
    } finally {
      setLoading(false)
    }
  }

  const toFormItems = (
    items: NonNullable<SafetyDutyAssessmentItemData['items']>
  ): ItemFormValues[] =>
    items.map((item) => ({
      content: item.content,
      rule: item.rule,
      standard_score: item.standard_score,
      deduction_score: item.deduction_score,
      remark: item.remark,
    }))

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      year: CURRENT_YEAR,
      quarter: 1,
      department: '',
      person_name: '',
      assessor: '安全部',
      assessment_date: null,
      remark: '',
      items: [],
    })
    setFormOpen(true)
  }

  const openEdit = (item: SafetyDutyAssessmentItemData) => {
    setEditing(item)
    form.setFieldsValue({
      year: item.year,
      quarter: item.quarter,
      department: item.department,
      person_name: item.person_name,
      assessor: item.assessor,
      assessment_date: item.assessment_date,
      remark: item.remark,
      items: toFormItems(item.items ?? []),
    })
    setFormOpen(true)
  }

  const prefillTemplate = async () => {
    const department = form.getFieldValue('department') as string | undefined
    if (!department || !department.trim()) {
      message.warning('请先填写被考核部门/单位')
      return
    }
    setTemplateLoading(true)
    try {
      const res = await getSafetyDutyAssessmentTemplate(department.trim())
      if (res.code === 200 && res.data) {
        if (!res.data.matched) {
          message.warning(`未找到「${department}」对应的考核表模板，已保持当前明细`)
          return
        }
        const templateItems = res.data.items ?? []
        form.setFieldsValue({
          items: templateItems.map((item) => ({
            content: item.content,
            rule: item.rule,
            standard_score: item.standard_score,
            deduction_score: 0,
            remark: '',
          })),
        })
        message.success(
          `已按「${res.data.name}」考核表模板预填 ${templateItems.length} 项`
        )
      } else {
        message.error(res.message || '获取考核模板失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '获取考核模板失败')
    } finally {
      setTemplateLoading(false)
    }
  }

  const submitForm = async () => {
    const values = await form.validateFields()
    const items = (values.items ?? []).map((item) => ({
      content: item.content,
      rule: item.rule ?? '',
      standard_score: item.standard_score ?? 0,
      deduction_score: item.deduction_score ?? 0,
      remark: item.remark ?? '',
    }))
    const payload = {
      year: values.year,
      quarter: values.quarter,
      department: values.department,
      person_name: values.person_name ?? '',
      assessor: values.assessor ?? '',
      assessment_date: values.assessment_date || null,
      items,
      remark: values.remark ?? '',
    }
    try {
      const res = editing
        ? await updateSafetyDutyAssessment(editing.id, payload)
        : await createSafetyDutyAssessment(payload)
      if (res.code === 200) {
        message.success(
          editing ? '考核记录已更新' : `考核已登记：${res.data?.total_score ?? 0} 分`
        )
        setFormOpen(false)
        await refresh()
      } else {
        message.error(res.message || '保存失败')
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败')
    }
  }

  const handleDelete = async (item: SafetyDutyAssessmentItemData) => {
    const res = await deleteSafetyDutyAssessment(item.id)
    if (res.code === 200) {
      message.success('考核记录已删除')
      await refresh()
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const columns: ColumnsType<SafetyDutyAssessmentItemData> = [
    {
      title: '考核期',
      key: 'period',
      width: 100,
      render: (_, row) => (
        <Text strong style={{ color: T.charcoal }}>{row.year}-Q{row.quarter}</Text>
      ),
    },
    {
      title: '被考核部门/人',
      key: 'assessed',
      width: 190,
      render: (_, row) => (
        <div>
          <Text strong style={{ color: T.charcoal }}>{row.department}</Text>
          {row.person_name && (
            <div>
              <Text style={{ color: T.steel, fontSize: 12 }}>{row.person_name}</Text>
            </div>
          )}
        </div>
      ),
    },
    { title: '考核单位', dataIndex: 'assessor', key: 'assessor', width: 110 },
    {
      title: '考核日期',
      dataIndex: 'assessment_date',
      key: 'assessment_date',
      width: 110,
      render: (v: string | null) => (
        <Text style={{ color: T.steel, fontSize: 12 }}>{v || '—'}</Text>
      ),
    },
    {
      title: '总分',
      dataIndex: 'total_score',
      key: 'total_score',
      width: 80,
      render: (v: number) => (
        <Text strong style={{ color: T.charcoal }}>{v}</Text>
      ),
    },
    {
      title: '等级',
      dataIndex: 'grade',
      key: 'grade',
      width: 90,
      render: (v: string) => {
        const meta = GRADE_META[v] || { color: T.steel, bg: T.surface }
        return (
          <Tag style={{ color: meta.color, backgroundColor: meta.bg, border: 'none', borderRadius: 6, fontWeight: 600 }}>
            {v}
          </Tag>
        )
      },
    },
    {
      title: '评分明细',
      key: 'items',
      ellipsis: true,
      render: (_, row) => (
        <Text style={{ color: T.slate, fontSize: 12 }}>
          {(row.items ?? []).length > 0
            ? `${(row.items ?? []).length} 项 · ${(row.items ?? [])
                .slice(0, 1)
                .map((i) => i.content)
                .join('')}`
            : '—'}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space size={4}>
          <Button type="link" size="small" style={{ padding: 0 }} disabled={!canOperate} onClick={() => openEdit(row)}>
            评分
          </Button>
          <Popconfirm title="确定删除该考核记录？" onConfirm={() => handleDelete(row)} disabled={!canDelete}>
            <Button type="link" size="small" danger style={{ padding: 0 }} disabled={!canDelete}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <Title level={5} className="!mb-1">安全生产责任制考核</Title>
          <Text style={{ color: T.slate, fontSize: 13 }}>
            每季度按考核表百分制评分 · ≥95 优秀 / ≥90 良好 / ≥80 合格 / &lt;80 不合格 · 考核模板来自 2026 责任制考核表
          </Text>
        </div>
        <Space>
          <Button
            disabled={!canOperate}
            onClick={() => {
              setImportYear(year)
              setImportQuarter(quarterFilter === 'all' ? 1 : Number(quarterFilter))
              setImportOpen(true)
            }}
          >
            批量导入
          </Button>
          <Button type="primary" disabled={!canOperate} onClick={openCreate}>
            发起季度考核
          </Button>
        </Space>
      </div>

      {stats && (
        <Card variant="borderless" size="small" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {[
              { label: '考核次数', value: stats.total, color: T.primary },
              { label: '平均分', value: stats.avg_score, color: T.charcoal },
              { label: '优秀', value: stats.excellent, color: T.success },
              { label: '良好', value: stats.good, color: T.primary },
              { label: '合格', value: stats.qualified, color: T.warning },
              { label: '不合格', value: stats.unqualified, color: T.error },
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
        <PlatformNotice
          type="error"
          message="考核记录加载失败"
          description={error}
          showRulesLink={false}
        />
      )}

      <Card variant="borderless" style={{ borderRadius: 12, border: `1px solid ${T.hairline}` }}>
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <Segmented
            value={year}
            onChange={(v) => {
              setYear(v as number)
              refresh(v as number, quarterFilter, keyword)
            }}
            options={[CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1]}
          />
          <Segmented
            value={quarterFilter}
            onChange={(v) => {
              setQuarterFilter(v as string)
              refresh(year, v as string, keyword)
            }}
            options={[
              { label: '全年', value: 'all' },
              { label: 'Q1', value: '1' },
              { label: 'Q2', value: '2' },
              { label: 'Q3', value: '3' },
              { label: 'Q4', value: '4' },
            ]}
          />
          <Input.Search
            placeholder="搜索部门/被考核人"
            allowClear
            style={{ maxWidth: 220 }}
            onSearch={(v) => {
              setKeyword(v)
              refresh(year, quarterFilter, v)
            }}
          />
          <Text style={{ color: T.muted, fontSize: 12, marginLeft: 'auto' }}>共 {total} 条</Text>
        </div>
        <Table<SafetyDutyAssessmentItemData>
          rowKey="id"
          columns={columns}
          dataSource={assessments}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="middle"
        />
      </Card>

      <Modal
        title={editing ? `责任制考核评分 · ${editing.department}` : '发起季度考核'}
        open={formOpen}
        onOk={submitForm}
        onCancel={() => setFormOpen(false)}
        width={960}
        destroyOnHidden
      >
        <Form<AssessmentFormValues> form={form} layout="vertical" className="mt-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4">
            <Form.Item name="year" label="年度" rules={[{ required: true, message: '请填写年度' }]}>
              <InputNumber min={2000} max={2100} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="quarter" label="季度" rules={[{ required: true }]}>
              <Select
                options={[1, 2, 3, 4].map((q) => ({ label: `Q${q}`, value: q }))}
              />
            </Form.Item>
            <Form.Item
              name="department"
              label="被考核部门/单位"
              rules={[{ required: true, message: '请填写被考核部门' }]}
            >
              <Input placeholder="如 安全部 / 101一车间 / 生产总监" />
            </Form.Item>
            <Form.Item name="person_name" label="被考核人">
              <Input placeholder="可空=部门整体" />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4">
            <Form.Item name="assessor" label="考核单位">
              <Input />
            </Form.Item>
            <Form.Item name="assessment_date" label="考核日期">
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="考核表模板">
              <Button disabled={!canOperate} loading={templateLoading} onClick={prefillTemplate}>
                按部门预填考核项
              </Button>
            </Form.Item>
          </div>

          <Form.List name="items">
            {(fields, { add, remove }) => (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Text style={{ color: T.slate, fontSize: 13 }}>
                    评分明细（总分 100 分制，当前合计 {computedTotal} 分 · 预计等级：
                    <Tag style={{ margin: 0, borderRadius: 6, border: 'none', backgroundColor: (GRADE_META[previewGrade] || GRADE_META.不合格).bg, color: (GRADE_META[previewGrade] || GRADE_META.不合格).color }}>
                      {previewGrade}
                    </Tag>
                    ）
                  </Text>
                  <Button size="small" disabled={!canOperate} onClick={() => add({ content: '', rule: '', standard_score: 5, deduction_score: 0, remark: '' })}>
                    添加考核项
                  </Button>
                </div>
                {fields.map((field) => (
                  <ItemRow key={field.key} fieldKey={field.name} onRemove={() => remove(field.name)} />
                ))}
                {fields.length === 0 && (
                  <Text style={{ color: T.muted, fontSize: 12 }}>
                    暂无考核项：填写被考核部门后点击“按部门预填考核项”，或手动添加。
                  </Text>
                )}
              </div>
            )}
          </Form.List>

          <Form.Item name="remark" label="备注" className="mt-3">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <TargetImportModal
        title={`批量导入季度考核（${importYear} 年 Q${importQuarter}）`}
        open={importOpen}
        onClose={() => setImportOpen(false)}
        templateHint="模板按 2026 考核表一个部门一个 sheet 生成：各 sheet 只需填「扣减分」列和表头被考核人/考核日期，只有填了扣减分的部门会导入，重复导入按 部门+被考核人 覆盖"
        downloadLabel={`下载 ${importYear} Q${importQuarter} 考核模板`}
        onDownload={() =>
          downloadDutyAssessmentImportTemplate(importYear, importQuarter)
        }
        extra={
          <Space wrap>
            <Text style={{ fontSize: 13 }}>导入期间：</Text>
            <Select
              value={importYear}
              style={{ width: 110 }}
              onChange={(v) => setImportYear(Number(v))}
              options={[CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1].map(
                (y) => ({ label: `${y} 年`, value: y })
              )}
            />
            <Select
              value={importQuarter}
              style={{ width: 90 }}
              onChange={(v) => setImportQuarter(Number(v))}
              options={[1, 2, 3, 4].map((q) => ({ label: `Q${q}`, value: q }))}
            />
          </Space>
        }
        onImport={async (file) => {
          const res = await importDutyAssessmentResults(
            file,
            importYear,
            importQuarter
          )
          if (res.code === 200 && res.data) {
            const errors = res.data.errors ?? []
            const skipped = res.data.skipped_sheets ?? []
            const lines = [
              `新建 ${res.data.imported} 条，覆盖更新 ${res.data.updated} 条`,
            ]
            if (skipped.length > 0) {
              const shown = skipped.slice(0, 6).join('、')
              lines.push(
                `未导入 ${skipped.length} 个 sheet（未填扣减分）：${shown}${skipped.length > 6 ? ' 等' : ''}`
              )
            }
            for (const err of errors) {
              lines.push(`${err.row}（${err.target}）失败：${err.message}`)
            }
            if (res.data.imported + res.data.updated > 0) await refresh()
            return { ok: errors.length === 0, lines }
          }
          return { ok: false, lines: [res.message || '导入失败'] }
        }}
      />
    </div>
  )
}

function round1(value: number): number {
  return Math.round(value * 10) / 10
}

function ItemRow({ fieldKey, onRemove }: { fieldKey: number; onRemove: () => void }) {
  const values = Form.useWatch(['items', fieldKey]) as ItemFormValues | undefined
  const score = itemScore(values ?? { content: '', standard_score: 0, deduction_score: 0 })
  return (
    <div
      className="rounded-lg p-2"
      style={{ backgroundColor: T.surface, border: `1px solid ${T.hairline}` }}
    >
      <div className="grid grid-cols-12 gap-2 items-start">
        <div className="col-span-6">
          <Form.Item
            name={[fieldKey, 'content']}
            rules={[{ required: true, message: '请填写考核内容' }]}
            className="!mb-1"
          >
            <Input.TextArea rows={2} placeholder="考核内容" style={{ fontSize: 12 }} />
          </Form.Item>
          <Form.Item name={[fieldKey, 'rule']} className="!mb-0">
            <Input placeholder="考核标准/扣分规则" style={{ fontSize: 12 }} />
          </Form.Item>
        </div>
        <div className="col-span-2">
          <Form.Item name={[fieldKey, 'standard_score']} className="!mb-1" label="标准分">
            <InputNumber min={0} max={1000} style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <div className="col-span-2">
          <Form.Item name={[fieldKey, 'deduction_score']} className="!mb-1" label="扣减分">
            <InputNumber min={0} max={1000} style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <div className="col-span-2 flex flex-col items-end gap-1">
          <Text style={{ color: T.slate, fontSize: 12 }}>得分 {score}</Text>
          <Button type="link" size="small" danger style={{ padding: 0 }} onClick={onRemove}>
            移除
          </Button>
        </div>
      </div>
    </div>
  )
}
