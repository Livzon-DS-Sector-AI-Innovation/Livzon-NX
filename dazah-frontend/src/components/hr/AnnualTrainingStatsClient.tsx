'use client'

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Drawer, Modal, Popconfirm, Spin, Table, Descriptions, Form, Input, Select, DatePicker, Tag, Space, Tooltip, Switch } from 'antd'
import { EditOutlined, DeleteOutlined, EyeOutlined, FolderOpenOutlined, DownloadOutlined, FileExcelOutlined, PlusOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT, fmtTrainingDatetime } from '@/lib/dayjs-config'
import type { TrainingLedgerRecord } from '@/types/hr'
import { fetchTrainingLedgersByDept } from '@/lib/api/hr'
import { fetchSessionDocuments, fetchTrainingSession } from '@/lib/api/client/hr'
import { updateTrainingLedger, deleteTrainingLedger, createSecondLevelTraining, generateOralExamResult, generatePracticalExamResult, createTrainingLedger } from '@/actions/hr'
import { downloadBytes } from '@/lib/download'
import ImportExamScoresModal from './ImportExamScoresModal'

const DOC_TYPE_LABELS: Record<string, string> = {
  sign_in: '培训签到表',
  evaluation: '培训评估表',
  notification: '培训通知',
  oral_exam: '口试评估表',
  practical_exam: '实操评估表',
}

interface Props {
  department: string
  dateFrom: string
  dateTo: string
  periodLabel: string
  printRequest: number
}

// 与后端导出 Excel 一致的列（15 列，年度培训统计表 SMP-HR-002-14）
const PRINT_HEADERS = [
  '培训时间', '培训日期', '培训时长（h）', '培训内容', '授课部门',
  '授课人', '一级/二级', '涉及部门', '培训对象', '培训类型', '考核方式',
  '部门/公司计划', '人药/兽药', '成绩汇总', '是否呈现',
]
const PRINT_FIELDS: (keyof TrainingLedgerRecord)[] = [
  'training_datetime', 'training_date', 'duration_hours', 'training_content',
  'teaching_dept', 'instructor', 'level_category', 'involved_depts',
  'trainees', 'training_type', 'ledger_assessment_method',
  'plan_source', 'drug_category', 'score_summary', 'is_presented',
]

// 拉取某部门筛选范围内的全量台账（循环分页直到取完），供打印使用
async function fetchAllLedgers(
  dept: string,
  dateFrom: string,
  dateTo: string
): Promise<TrainingLedgerRecord[]> {
  const all: TrainingLedgerRecord[] = []
  const pageSize = 1000
  let p = 1
  for (;;) {
    const res = await fetchTrainingLedgersByDept(
      dept,
      p,
      pageSize,
      dateFrom || undefined,
      dateTo || undefined
    )
    const rows = res.data || []
    all.push(...rows)
    const total = res.meta?.total ?? all.length
    if (all.length >= total || rows.length === 0) break
    p += 1
  }
  return all
}

export default function AnnualTrainingStatsClient({ department, dateFrom, dateTo, periodLabel, printRequest }: Props) {
  const { message } = App.useApp()
  const [records, setRecords] = useState<TrainingLedgerRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [detailRecord, setDetailRecord] = useState<TrainingLedgerRecord | null>(null)
  const [editingRecord, setEditingRecord] = useState<TrainingLedgerRecord | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [form] = Form.useForm()
  const [createForm] = Form.useForm()
  const router = useRouter()

  // ── 培训资料 Drawer（台账行 → 会话五类资料） ──
  const [docsRecord, setDocsRecord] = useState<TrainingLedgerRecord | null>(null)
  const [docs, setDocs] = useState<{ id: string; session_id: string; doc_type: string; title?: string | null; payload: any; updated_at?: string | null }[]>([])
  const [docsLoading, setDocsLoading] = useState(false)

  // ── 笔试成绩导入弹窗 ──
  const [examScoreRecordId, setExamScoreRecordId] = useState<string | null>(null)
  // ── 权限控制：只有主办部门（落款部门）的用户才能导入成绩 ──
  const [sessionDept, setSessionDept] = useState<string | null>(null)
  const [userDept, setUserDept] = useState<string>('')

  // 获取当前用户部门（组件挂载时一次）
  useEffect(() => {
    fetch('/api/v1/identity/me', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setUserDept(j?.data?.department || ''))
      .catch(() => {})
  }, [])

  const openDocs = async (record: TrainingLedgerRecord) => {
    setDocsRecord(record)
    setDocsLoading(true)
    setSessionDept(null)
    try {
      const [docsData, sessionData] = await Promise.all([
        fetchSessionDocuments(record.session_id!),
        fetchTrainingSession(record.session_id!),
      ])
      setDocs(docsData)
      setSessionDept(sessionData.department || null)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '加载培训资料失败')
    } finally {
      setDocsLoading(false)
    }
  }

  const exportDocFromDrawer = async (doc: (typeof docs)[number]) => {
    try {
      if (doc.doc_type === 'oral_exam') {
        const r = await generateOralExamResult(doc.payload)
        downloadBytes(r.bytes, r.filename)
      } else if (doc.doc_type === 'practical_exam') {
        const r = await generatePracticalExamResult(doc.payload)
        downloadBytes(r.bytes, r.filename)
      }
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '导出失败')
    }
  }

  const loadData = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      const res = await fetchTrainingLedgersByDept(
        department,
        p,
        pageSize,
        dateFrom || undefined,
        dateTo || undefined
      )
      setRecords(res.data || [])
      setTotal(res.meta?.total ?? (res.data?.length || 0))
      setPage(p)
    } catch (e) {
      message.error('加载数据失败: ' + ((e instanceof Error ? e.message : '') || '未知错误'))
    } finally {
      setLoading(false)
    }
  }, [department, dateFrom, dateTo, pageSize, message])

  // 部门或筛选日期变化 → 回到第一页重新加载（服务端分页 + 服务端日期过滤）
  useEffect(() => {
    // 依赖变化时同步回到第一页加载：loadData 内部 setLoading 为首个同步步骤
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(1)
  }, [loadData])

  // 按导出内容打印：新窗口渲染与导出 Excel 一致的表格后调起打印
  const doPrint = async () => {
    const all = await fetchAllLedgers(department, dateFrom, dateTo)
    if (all.length === 0) {
      message.warning('当前筛选范围内没有数据')
      return
    }
    const title = `${department} 年度培训统计表${periodLabel ? `（${periodLabel}）` : ''}`
    const esc = (v: unknown) =>
      String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const headerHtml = PRINT_HEADERS.map((h) => `<th>${esc(h)}</th>`).join('')
    const bodyHtml = all
      .map((r) => `<tr>${PRINT_FIELDS.map((f) => `<td>${esc(r[f] ?? '')}</td>`).join('')}</tr>`)
      .join('')
    const w = window.open('', '_blank')
    if (!w) {
      message.error('浏览器拦截了弹出窗口，请允许后重试')
      return
    }
    w.document.write(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>
  @page { size: A4 landscape; margin: 10mm; }
  body { font-family: "Microsoft YaHei", sans-serif; font-size: 11px; }
  h2 { text-align: center; font-size: 16px; margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #000; padding: 4px 5px; text-align: center; word-break: break-all; }
  th { background: #f0f0f0; font-weight: bold; }
</style></head><body>
<h2>${esc(title)}</h2>
<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>
</body></html>`)
    w.document.close()
    w.focus()
    w.print()
  }

  useEffect(() => {
    if (printRequest > 0) void doPrint()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [printRequest])

  const handleEdit = (record: TrainingLedgerRecord) => {
    setEditingRecord(record)
    form.setFieldsValue({
      ...record,
      training_date: record.training_date ? dayjs(record.training_date) : null,
    })
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await updateTrainingLedger(editingRecord!.id, {
        ...values,
        training_date: values.training_date ? values.training_date.format('YYYY-MM-DD') : undefined,
      })
      message.success('更新成功')
      setEditingRecord(null)
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteTrainingLedger(id)
      message.success('删除成功')
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '删除失败')
    }
  }

  const handleCreateOpen = () => {
    createForm.resetFields()
    setCreateModalOpen(true)
  }

  const handleCreateSave = async () => {
    const values = await createForm.validateFields()
    setCreating(true)
    try {
      await createTrainingLedger({
        ...values,
        source_type: 'manual',
        training_date: values.training_date ? values.training_date.format('YYYY-MM-DD') : undefined,
      })
      message.success('创建成功')
      setCreateModalOpen(false)
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '创建失败')
    } finally {
      setCreating(false)
    }
  }

  // 二级培训确认：已完成二级 / 不需二级 → 消除淡黄底色
  const handleSetSecondLevel = async (record: TrainingLedgerRecord, status: 'done' | 'not_needed') => {
    try {
      await updateTrainingLedger(record.id, { second_level_status: status })
      message.success(status === 'done' ? '已确认完成二级培训' : '已确认无需二级培训')
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '操作失败')
    }
  }

  // 是否呈现切换：直接更新 is_presented 并刷新
  const handleTogglePresented = async (record: TrainingLedgerRecord, checked: boolean) => {
    try {
      await updateTrainingLedger(record.id, { is_presented: checked })
      message.success(checked ? '已设为呈现' : '已设为不呈现（不进入员工培训清单）')
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '切换失败')
    }
  }

  // 从台账副本一键创建部门级二级培训会话并带入上级试卷，跳转到培训资料页
  const handleCreateSecondLevel = async (record: TrainingLedgerRecord) => {
    try {
      const res = await createSecondLevelTraining(record.id)
      message.success(`已创建二级培训会话（带入 ${res.copied_doc_types.length} 类试卷）`)
      router.push(`/hr/training/sign-in?session=${res.id}&doc=ai_written_exam&parent_record=${res.parent_record_id}`)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '创建二级培训失败')
    }
  }

  const columns = [
    { title: '培训时间', dataIndex: 'training_datetime', width: 160, ellipsis: true, render: (v: string) => fmtTrainingDatetime(v) },
    { title: '培训日期', dataIndex: 'training_date', width: 110, render: (v: string) => v ? dayjs(v).format(HR_DISPLAY_DATE_FORMAT) : '-' },
    { title: '培训时长（h）', dataIndex: 'duration_hours', width: 90 },
    {
      title: '培训内容', dataIndex: 'training_content', width: 300,
      render: (v: string, record: TrainingLedgerRecord) =>
        record.owner_deleted ? (
          <Tooltip title="该记录已被主办方删除，请注意">
            <span style={{ cursor: 'help' }}>{v || '-'}</span>
          </Tooltip>
        ) : (v ?? '-'),
    },
    { title: '授课部门', dataIndex: 'teaching_dept', width: 120 },
    { title: '授课人', dataIndex: 'instructor', width: 90 },
    { title: '一级/二级', dataIndex: 'level_category', width: 80 },
    { title: '涉及部门', dataIndex: 'involved_depts', width: 140, ellipsis: true },
    { title: '培训对象', dataIndex: 'trainees', width: 200, ellipsis: true },
    { title: '培训类型', dataIndex: 'training_type', width: 100 },
    { title: '考核方式', dataIndex: 'ledger_assessment_method', width: 90 },
    {
      title: '是否呈现', dataIndex: 'is_presented', width: 90, fixed: 'right' as const,
      render: (v: boolean | null | undefined, record: TrainingLedgerRecord) => (
        <Switch
          size="small"
          checked={v !== false}
          onChange={(checked) => handleTogglePresented(record, checked)}
          checkedChildren="是"
          unCheckedChildren="否"
        />
      ),
    },
    {
      title: '操作', width: 330, fixed: 'right' as const,
      render: (_: unknown, record: TrainingLedgerRecord) => (
        <div className="no-print flex gap-2">
          {record.second_level_status === 'pending' && record.session_id && (
            <Button size="small" type="primary" ghost onClick={() => handleCreateSecondLevel(record)}>
              做二级培训
            </Button>
          )}
          {record.second_level_status === 'pending' && (
            <>
              <Popconfirm title="确认已完成二级培训？" onConfirm={() => handleSetSecondLevel(record, 'done')}>
                <Button size="small" type="primary">已完成二级</Button>
              </Popconfirm>
              <Popconfirm title="确认无需开展二级培训？" onConfirm={() => handleSetSecondLevel(record, 'not_needed')}>
                <Button size="small">不需二级</Button>
              </Popconfirm>
            </>
          )}
          {record.session_id && (
            <Button size="small" icon={<FolderOpenOutlined />} onClick={() => openDocs(record)}>资料</Button>
          )}
          <Button size="small" icon={<EyeOutlined />} onClick={() => setDetailRecord(record)}>详情</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确定删除?" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </div>
      ),
    },
  ]

  if (loading) return <div className="flex justify-center py-20"><Spin size="large" /></div>

  return (
    <>
      <Space className="mb-3">
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateOpen}>
          新增台账记录
        </Button>
      </Space>
      <Table
        rowKey="id"
        dataSource={records}
        columns={columns}
        scroll={{ x: 1400 }}
        size="small"
        pagination={{
          current: page,
          pageSize,
          total,
          showTotal: (t: number) => `共 ${t} 条`,
          showSizeChanger: false,
          onChange: (p: number) => loadData(p),
        }}
        rowClassName={(record) => {
          if (record.owner_deleted) return 'print-row ledger-owner-deleted-row'
          if (record.second_level_status === 'pending') return 'print-row ledger-pending-row'
          return 'print-row'
        }}
      />

      {/* 详情抽屉 */}
      <Drawer
        title="培训记录详情"
        open={!!detailRecord}
        onClose={() => setDetailRecord(null)}
        size={600}
      >
        {detailRecord && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="培训时间">{fmtTrainingDatetime(detailRecord.training_datetime)}</Descriptions.Item>
            <Descriptions.Item label="培训日期">{detailRecord.training_date ? dayjs(detailRecord.training_date).format(HR_DISPLAY_DATE_FORMAT) : '-'}</Descriptions.Item>
            <Descriptions.Item label="培训时长（h）">{detailRecord.duration_hours ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="培训内容">{detailRecord.training_content || '-'}</Descriptions.Item>
            <Descriptions.Item label="授课部门">{detailRecord.teaching_dept || '-'}</Descriptions.Item>
            <Descriptions.Item label="授课人">{detailRecord.instructor || '-'}</Descriptions.Item>
            <Descriptions.Item label="一级/二级">{detailRecord.level_category || '-'}</Descriptions.Item>
            <Descriptions.Item label="涉及部门">{detailRecord.involved_depts || '-'}</Descriptions.Item>
            <Descriptions.Item label="培训对象">{detailRecord.trainees || '-'}</Descriptions.Item>
            <Descriptions.Item label="培训类型">{detailRecord.training_type || '-'}</Descriptions.Item>
            <Descriptions.Item label="考核方式">{detailRecord.ledger_assessment_method || '-'}</Descriptions.Item>
            <Descriptions.Item label="部门/公司计划">{detailRecord.plan_source || '-'}</Descriptions.Item>
            <Descriptions.Item label="人药/兽药">{detailRecord.drug_category || '-'}</Descriptions.Item>
            <Descriptions.Item label="成绩汇总">{detailRecord.score_summary || '-'}</Descriptions.Item>
            <Descriptions.Item label="备注">{detailRecord.remarks || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      {/* 培训资料抽屉：台账行 → 会话五类资料 */}
      <Drawer
        title={`培训资料${docsRecord ? ` — ${docsRecord.training_subject}` : ''}`}
        open={!!docsRecord}
        onClose={() => setDocsRecord(null)}
        size={520}
      >
        {docsLoading ? (
          <div className="flex justify-center py-10"><Spin /></div>
        ) : (
          <div className="flex flex-col gap-3">
            {Object.entries(DOC_TYPE_LABELS).map(([type, label]) => {
              const doc = docs.find((d) => d.doc_type === type)
              return (
                <div key={type} className="flex items-center justify-between border rounded px-3 py-2">
                  <span>
                    {label}
                    {doc ? (
                      <Tag color="green" style={{ marginLeft: 8 }}>已保存 {(doc.updated_at || '').slice(0, 10)}</Tag>
                    ) : (
                      <Tag style={{ marginLeft: 8 }}>未保存</Tag>
                    )}
                  </span>
                  {doc && (
                    <Space>
                      {(type === 'oral_exam' || type === 'practical_exam') && (
                        <Button size="small" icon={<DownloadOutlined />} onClick={() => exportDocFromDrawer(doc)}>
                          导出
                        </Button>
                      )}
                      <Button
                        size="small"
                        type="primary"
                        onClick={() => router.push(`/hr/training/sign-in?session=${doc.session_id}&doc=${type}`)}
                      >
                        打开编辑
                      </Button>
                    </Space>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* 笔试成绩导入：仅主办部门（落款部门）用户可操作 */}
        {docsRecord?.session_id && (!sessionDept || sessionDept === userDept) && (
          <div className="mt-4 border-t pt-3">
            <Button
              type="primary"
              icon={<FileExcelOutlined />}
              onClick={() => setExamScoreRecordId(docsRecord.id)}
            >
              导入笔试成绩
            </Button>
          </div>
        )}
      </Drawer>

      {/* 编辑 Modal */}
      <Modal
        title="编辑培训记录"
        open={!!editingRecord}
        onCancel={() => setEditingRecord(null)}
        onOk={handleSave}
        confirmLoading={saving}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="training_datetime" label="培训时间（日期+时间）">
            <Input placeholder="如 2026.01.06 09:00~10:00" />
          </Form.Item>
          <Form.Item name="training_date" label="培训日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="duration_hours" label="培训时长（h）">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="training_content" label="培训内容">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="teaching_dept" label="授课部门">
            <Input />
          </Form.Item>
          <Form.Item name="instructor" label="授课人">
            <Input />
          </Form.Item>
          <Form.Item name="level_category" label="一级/二级">
            <Select options={[{ value: '一级', label: '一级' }, { value: '二级', label: '二级' }]} />
          </Form.Item>
          <Form.Item name="involved_depts" label="涉及部门">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="trainees" label="培训对象">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="training_type" label="培训类型">
            <Select options={[
              { value: '管理类', label: '管理类' },
              { value: 'EHS培训', label: 'EHS培训' },
              { value: '质量培训', label: '质量培训' },
              { value: '质量类', label: '质量类' },
              { value: '数据安全、隐私保护', label: '数据安全、隐私保护' },
              { value: '领导力培训', label: '领导力培训' },
              { value: '多元化', label: '多元化' },
              { value: '反贪腐类', label: '反贪腐类' },
              { value: '负责任营销', label: '负责任营销' },
            ]} />
          </Form.Item>
          <Form.Item name="ledger_assessment_method" label="考核方式">
            <Select options={[{ value: '口试', label: '口试' }, { value: '笔试', label: '笔试' }]} />
          </Form.Item>
          <Form.Item name="plan_source" label="部门/公司计划">
            <Select options={[
              { value: '部门级计划', label: '部门级计划' },
              { value: '公司级计划', label: '公司级计划' },
            ]} />
          </Form.Item>
          <Form.Item name="drug_category" label="人药/兽药">
            <Select options={[
              { value: '人药', label: '人药' },
              { value: '兽药', label: '兽药' },
              { value: '人药、兽药', label: '人药、兽药' },
            ]} />
          </Form.Item>
          <Form.Item name="score_summary" label="成绩汇总">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="is_presented" label="是否呈现" valuePropName="checked">
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新增 Modal */}
      <Modal
        title="新增培训记录"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={handleCreateSave}
        confirmLoading={creating}
        width={640}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="training_datetime" label="培训时间（日期+时间）">
            <Input placeholder="如 2026.01.06 09:00~10:00" />
          </Form.Item>
          <Form.Item name="training_date" label="培训日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="training_subject" label="培训课程/主题">
            <Input />
          </Form.Item>
          <Form.Item name="duration_hours" label="培训时长（h）">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="training_content" label="培训内容">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="training_method" label="培训方式">
            <Select options={[{ value: '线上', label: '线上' }, { value: '线下', label: '线下' }]} />
          </Form.Item>
          <Form.Item name="teaching_dept" label="授课部门">
            <Input />
          </Form.Item>
          <Form.Item name="instructor" label="授课人">
            <Input />
          </Form.Item>
          <Form.Item name="location" label="培训地点">
            <Input />
          </Form.Item>
          <Form.Item name="trainer" label="培训单位/培训师">
            <Input />
          </Form.Item>
          <Form.Item name="level_category" label="一级/二级">
            <Select options={[{ value: '一级', label: '一级' }, { value: '二级', label: '二级' }]} />
          </Form.Item>
          <Form.Item name="involved_depts" label="涉及部门">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="trainees" label="培训对象">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="training_type" label="培训类型">
            <Select options={[
              { value: '管理类', label: '管理类' },
              { value: 'EHS培训', label: 'EHS培训' },
              { value: '质量培训', label: '质量培训' },
              { value: '质量类', label: '质量类' },
              { value: '数据安全、隐私保护', label: '数据安全、隐私保护' },
              { value: '领导力培训', label: '领导力培训' },
              { value: '多元化', label: '多元化' },
              { value: '反贪腐类', label: '反贪腐类' },
              { value: '负责任营销', label: '负责任营销' },
            ]} />
          </Form.Item>
          <Form.Item name="ledger_assessment_method" label="考核方式">
            <Select options={[{ value: '口试', label: '口试' }, { value: '笔试', label: '笔试' }]} />
          </Form.Item>
          <Form.Item name="plan_source" label="部门/公司计划">
            <Select options={[
              { value: '部门级计划', label: '部门级计划' },
              { value: '公司级计划', label: '公司级计划' },
            ]} />
          </Form.Item>
          <Form.Item name="drug_category" label="人药/兽药">
            <Select options={[
              { value: '人药', label: '人药' },
              { value: '兽药', label: '兽药' },
              { value: '人药、兽药', label: '人药、兽药' },
            ]} />
          </Form.Item>
          <Form.Item name="assessment_result" label="考核成绩">
            <Input />
          </Form.Item>
          <Form.Item name="score_summary" label="成绩汇总">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="ledger_department" label="部门">
            <Input defaultValue={department} />
          </Form.Item>
          <Form.Item name="is_presented" label="是否呈现" valuePropName="checked">
            <Switch checkedChildren="是" unCheckedChildren="否" defaultChecked />
          </Form.Item>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 笔试成绩导入弹窗 */}
      <ImportExamScoresModal
        open={!!examScoreRecordId}
        recordId={examScoreRecordId || ''}
        onClose={() => setExamScoreRecordId(null)}
        onSuccess={() => {
          loadData(page)
          // 同步刷新资料 Drawer 中的数据
          if (docsRecord) openDocs(docsRecord)
        }}
      />

      <style jsx global>{`
        /* 多部门培训待二级确认：淡黄底色 */
        .ledger-pending-row > td { background: #fffbe6 !important; }
        /* 主办方已删除（其他部门副本）：淡红底色 */
        .ledger-owner-deleted-row > td { background: #fff1f0 !important; }
      `}</style>
    </>
  )
}
