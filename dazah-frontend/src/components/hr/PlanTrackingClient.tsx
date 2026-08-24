'use client'

/**
 * 培训计划跟踪（APP11-SMP-HR-002-14）
 * 页面按图2结构：序号列跨双行表头 + 培训内容/培训跟踪工作组表头 + 可编辑数据行。
 * 业务规则：
 * - 一行 = 一条年度计划明细（年+月+级别）；公司级/部门级分轨，部门级全部部门汇总；
 * - 自动录入时部门级培训对象前拼接部门（如「QA 全员」）；
 * - 培训内容/培训对象与年度计划保持一致，表内锁定，仅可通过编辑弹窗修改；
 * - 实际培训时间自动汇总关联培训资料的多场时间（日期 时间段，逐行），可手工补充；
 * - 每行提供编辑（全字段弹窗）/删除操作。
 * 导出 Excel 严格沿用桌面 APP11 模板（锁定区不可变）。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  App,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Radio,
  Segmented,
  Spin,
} from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  FileTextOutlined,
  PlusOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { fetchPlanTrackingPeriod } from '@/lib/api/client/hr'
import {
  createPlanTrackingRecord,
  updatePlanTrackingRecord,
  deletePlanTrackingRecord,
} from '@/actions/hr'
import type { PlanTrackingRecord } from '@/types/hr'

// 列宽比例（序号/培训内容或使用教材/实际培训时间/培训对象/培训类型/考核方式/是否按照计划完成/跟踪人/跟踪日期/备注）
const COL_WIDTHS = [4, 20, 11, 15, 9, 11, 12, 7, 8, 8]
const MIN_DATA_ROWS = 7

const HEADERS = [
  '培训内容或使用教材',
  '实际培训时间',
  '培训对象',
  '培训类型',
  '考核方式',
  '是否按照计划完成',
  '跟踪人',
  '跟踪日期',
  '备注',
]

interface RowState {
  record: PlanTrackingRecord | null // null = 未落库的草稿行
  fields: {
    training_content: string
    actual_time: string
    target_audience: string
    training_type: string
    tracking_assessment_method: string
    is_completed: boolean | null
    tracker: string
    track_date: string
    remarks: string
  }
}

function toRowState(record: PlanTrackingRecord): RowState {
  return {
    record,
    fields: {
      training_content: record.training_content || '',
      actual_time: record.actual_time || '',
      target_audience: record.target_audience || '',
      training_type: record.training_type || '',
      tracking_assessment_method: record.tracking_assessment_method || '',
      is_completed: record.is_completed ?? null,
      tracker: record.tracker || '',
      track_date: record.track_date ? String(record.track_date).slice(0, 10) : '',
      remarks: record.remarks || '',
    },
  }
}

function emptyRow(): RowState {
  return {
    record: null,
    fields: {
      training_content: '',
      actual_time: '',
      target_audience: '',
      training_type: '',
      tracking_assessment_method: '',
      is_completed: null,
      tracker: '',
      track_date: '',
      remarks: '',
    },
  }
}

/** 统计卡片 */
function StatCard({
  icon,
  label,
  value,
  accent,
}: {
  icon: React.ReactNode
  label: string
  value: number
  accent: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-[#e8eaef] bg-white px-4 py-3 shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
      <div
        className="flex h-10 w-10 items-center justify-center rounded-lg text-[18px]"
        style={{ background: `${accent}14`, color: accent }}
      >
        {icon}
      </div>
      <div>
        <div className="text-[12px] leading-5 text-[var(--color-steel)]">{label}</div>
        <div className="text-[20px] font-semibold leading-7 text-[var(--color-charcoal)]">
          {value}
        </div>
      </div>
    </div>
  )
}

export default function PlanTrackingClient() {
  const { message } = App.useApp()
  const now = new Date()
  const [year, setYear] = useState<number>(now.getFullYear())
  const [month, setMonth] = useState<number>(now.getMonth() + 1)
  const [planLevel, setPlanLevel] = useState<string>('公司级')
  const [rows, setRows] = useState<RowState[]>([])
  const [loading, setLoading] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editForm] = Form.useForm()
  const saveTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})
  const rowsRef = useRef<RowState[]>([])
  useEffect(() => {
    rowsRef.current = rows
  }, [rows])

  // 组件卸载时清理所有待执行的防抖定时器，防止内存泄漏
  useEffect(() => {
    return () => {
      Object.values(saveTimers.current).forEach((timer) => clearTimeout(timer))
    }
  }, [])

  // 期间变化 → 幂等自动录入并加载（部门级全部部门汇总，无需选部门）
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchPlanTrackingPeriod({ year, month, plan_level: planLevel })
      .then((records) => {
        if (cancelled) return
        const list = records.map(toRowState)
        while (list.length < MIN_DATA_ROWS) list.push(emptyRow())
        setRows(list)
      })
      .catch(() => {
        if (!cancelled) {
          message.error('加载培训计划跟踪数据失败')
          const list: RowState[] = []
          while (list.length < MIN_DATA_ROWS) list.push(emptyRow())
          setRows(list)
        }
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [year, month, planLevel])

  const periodCtx = useMemo(
    () => ({ year, month: String(month), plan_level: planLevel }),
    [year, month, planLevel],
  )

  // 统计
  const stats = useMemo(() => {
    const tracked = rows.filter((r) => r.record)
    const done = tracked.filter((r) => r.fields.is_completed === true).length
    const notDone = tracked.filter((r) => r.fields.is_completed === false).length
    const untracked = tracked.length - done - notDone
    const rate = tracked.length ? Math.round((done / tracked.length) * 100) : 0
    return { total: tracked.length, done, notDone, untracked, rate }
  }, [rows])

  const patchRow = (index: number, patch: Partial<RowState['fields']>) => {
    setRows((prev) =>
      prev.map((r, i) => (i === index ? { ...r, fields: { ...r.fields, ...patch } } : r)),
    )
    if (saveTimers.current[index]) clearTimeout(saveTimers.current[index])
    saveTimers.current[index] = setTimeout(() => {
      persistRow(index)
    }, 800)
  }

  const persistRow = async (index: number) => {
    const row = rowsRef.current[index]
    if (!row) return
    const data = {
      ...row.fields,
      track_date: row.fields.track_date || undefined,
      sort_order: index,
      ...periodCtx,
    }
    try {
      if (row.record) {
        await updatePlanTrackingRecord(row.record.id, data)
      } else {
        // 草稿行：有任意内容才落库
        const hasContent = Object.values(row.fields).some((v) => v !== '' && v !== null)
        if (!hasContent) return
        const res = await createPlanTrackingRecord(data)
        setRows((prev) =>
          prev.map((r, i) => (i === index && !r.record ? { ...r, record: res.data } : r)),
        )
      }
    } catch {
      message.error('保存失败')
    }
  }

  const handleAddRow = () => {
    setRows((prev) => [...prev, emptyRow()])
  }

  const handleDeleteRow = async (index: number) => {
    const row = rows[index]
    if (row?.record) {
      try {
        await deletePlanTrackingRecord(row.record.id)
        message.success('删除成功')
      } catch {
        message.error('删除失败')
        return
      }
    }
    setRows((prev) => {
      const next = prev.filter((_, i) => i !== index)
      while (next.length < MIN_DATA_ROWS) next.push(emptyRow())
      return next
    })
  }

  // ─── 编辑弹窗（全字段可编辑，含锁定的培训内容/对象）───

  const toFormValues = (row: RowState) => ({
    ...row.fields,
    is_completed_opt:
      row.fields.is_completed === true
        ? 'true'
        : row.fields.is_completed === false
          ? 'false'
          : 'null',
    track_date: row.fields.track_date ? dayjs(row.fields.track_date) : null,
  })

  const handleOpenEdit = (index: number) => {
    if (!rows[index]) return
    setEditingIndex(index)
  }

  const handleSaveEdit = async () => {
    if (editingIndex === null) return
    const values = await editForm.validateFields()
    const row = rowsRef.current[editingIndex]
    if (!row) return
    const fields: RowState['fields'] = {
      training_content: values.training_content || '',
      actual_time: values.actual_time || '',
      target_audience: values.target_audience || '',
      training_type: values.training_type || '',
      tracking_assessment_method: values.tracking_assessment_method || '',
      is_completed:
        values.is_completed_opt === 'true' ? true : values.is_completed_opt === 'false' ? false : null,
      tracker: values.tracker || '',
      track_date: values.track_date ? values.track_date.format('YYYY-MM-DD') : '',
      remarks: values.remarks || '',
    }
    const data = { ...fields, track_date: fields.track_date || undefined, sort_order: editingIndex, ...periodCtx }
    try {
      if (row.record) {
        await updatePlanTrackingRecord(row.record.id, data)
      } else {
        const res = await createPlanTrackingRecord(data)
        setRows((prev) =>
          prev.map((r, i) =>
            i === editingIndex ? { fields, record: res.data } : r,
          ),
        )
        setEditingIndex(null)
        message.success('保存成功')
        return
      }
      setRows((prev) => prev.map((r, i) => (i === editingIndex ? { ...r, fields } : r)))
      setEditingIndex(null)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    }
  }

  const handleExport = () => {
    const sp = new URLSearchParams({
      year: String(year),
      month: String(month),
      plan_level: planLevel,
    })
    window.open(`/api/v1/hr/plan-tracking/export?${sp}`, '_blank')
  }

  const colTotal = COL_WIDTHS.reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-4">
      <style>{`
        .pt-card { background: #fff; border: 1px solid #e8eaef; border-radius: 12px; box-shadow: 0 1px 2px rgba(16,24,40,.04); overflow: hidden; }
        .pt-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 14px 16px; border-bottom: 1px solid #eef0f3; }
        .pt-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
        .pt-table th { padding: 10px 8px; text-align: center; font-size: 13px; font-weight: 600; color: var(--color-charcoal); border-bottom: 1px solid #e8eaef; border-right: 1px solid #eef0f3; }
        .pt-table th:last-child { border-right: none; }
        .pt-table th.pt-group { background: #f5f7fb; letter-spacing: 2px; }
        .pt-table th.pt-sub { background: #fafbfd; color: rgba(0,0,0,.65); font-weight: 500; }
        .pt-table td { padding: 0; text-align: center; vertical-align: middle; border-bottom: 1px solid #eef0f3; border-right: 1px solid #f3f4f6; font-size: 13px; color: rgba(0,0,0,.85); }
        .pt-table td:last-child { border-right: none; }
        .pt-table tbody tr { transition: background .15s; }
        .pt-table tbody tr:hover td { background: #f7f9fd; }
        .pt-table tbody tr:last-child td { border-bottom: none; }
        .pt-table td.pt-gutter { border: none; width: 56px; padding: 0 4px; background: transparent !important; }
        .pt-seq { color: var(--color-steel); font-size: 12px; font-variant-numeric: tabular-nums; }
        .pt-in { width: 100%; border: none; outline: none; background: transparent; text-align: center; font-size: 13px; padding: 10px 6px; font-family: inherit; color: inherit; border-radius: 6px; transition: background .15s, box-shadow .15s; }
        textarea.pt-in { resize: none; display: block; line-height: 1.5; }
        .pt-in:focus { background: #fff; box-shadow: inset 0 0 0 1.5px var(--color-primary); }
        .pt-in::placeholder { color: #c3c8d1; }
        .pt-in:disabled { background: #f7f8fa; color: rgba(0,0,0,.55); cursor: not-allowed; }
        .pt-pill { display: inline-flex; align-items: center; gap: 3px; border-radius: 999px; border: 1px solid #e0e3e9; background: #fff; color: #9aa0ab; font-size: 12px; line-height: 1; padding: 5px 10px; cursor: pointer; user-select: none; transition: all .15s; }
        .pt-pill:hover { border-color: #c9ced8; }
        .pt-pill-on-green { background: #f6ffed; border-color: #b7eb8f; color: #389e0d; }
        .pt-pill-on-red { background: #fff1f0; border-color: #ffa39e; color: #cf1322; }
        .pt-op { opacity: 0; transition: opacity .15s; }
        tr:hover > td .pt-op { opacity: 1; }
      `}</style>

      {/* 统计概览 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={<FileTextOutlined />}
          label="本期跟踪项"
          value={stats.total}
          accent="#4060e6"
        />
        <StatCard
          icon={<CheckCircleOutlined />}
          label="已完成"
          value={stats.done}
          accent="#52c41a"
        />
        <StatCard
          icon={<CloseCircleOutlined />}
          label="未完成"
          value={stats.notDone}
          accent="#f5222d"
        />
        <StatCard
          icon={<UnorderedListOutlined />}
          label="未跟踪"
          value={stats.untracked}
          accent="#faad14"
        />
      </div>

      {/* 表格卡片 */}
      <Spin spinning={loading}>
        <div className="pt-card">
          {/* 工具条 */}
          <div className="pt-toolbar">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5">
                <InputNumber
                  controls={false}
                  min={2000}
                  max={2100}
                  value={year}
                  onChange={(v) => v && setYear(v)}
                  style={{ width: 84 }}
                />
                <span className="text-[13px] text-[var(--color-steel)]">年度</span>
              </div>
              <div className="flex items-center gap-1.5">
                <InputNumber
                  controls={false}
                  min={1}
                  max={12}
                  value={month}
                  onChange={(v) => v && setMonth(v)}
                  style={{ width: 56 }}
                />
                <span className="text-[13px] text-[var(--color-steel)]">月</span>
              </div>
              <Segmented
                value={planLevel}
                onChange={(v) => setPlanLevel(String(v))}
                options={['公司级', '部门级']}
              />
              {planLevel === '部门级' && (
                <span className="text-[12px] text-[var(--color-steel)]">
                  全部部门汇总，培训对象前带部门标识
                </span>
              )}
              <div className="hidden items-center gap-2 md:flex">
                <span className="text-[12px] text-[var(--color-steel)]">完成率</span>
                <Progress
                  percent={stats.rate}
                  size="small"
                  style={{ width: 120, marginBottom: 0 }}
                  strokeColor={stats.rate === 100 ? '#52c41a' : undefined}
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button icon={<PlusOutlined />} onClick={handleAddRow}>
                添加行
              </Button>
              <Button type="primary" icon={<ExportOutlined />} onClick={handleExport}>
                导出跟踪表
              </Button>
            </div>
          </div>

          {/* 跟踪表 */}
          <table className="pt-table">
            <colgroup>
              {COL_WIDTHS.map((w, i) => (
                <col key={i} style={{ width: `${(w / colTotal) * 100}%` }} />
              ))}
              <col style={{ width: 56 }} />
            </colgroup>
            <thead>
              <tr>
                <th rowSpan={2} className="pt-sub">
                  序号
                </th>
                <th colSpan={5} className="pt-group">
                  培训内容
                </th>
                <th colSpan={4} className="pt-group">
                  培训跟踪工作
                </th>
                <th className="pt-gutter" rowSpan={2} />
              </tr>
              <tr>
                {HEADERS.map((h, i) => (
                  <th key={i} className="pt-sub">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={row.record?.id ?? `draft-${idx}`}>
                  <td>
                    <span className="pt-seq">{idx + 1}</span>
                  </td>
                  <td>
                    <textarea
                      className="pt-in"
                      rows={2}
                      disabled={!!row.record}
                      title={row.record ? '与年度培训计划一致，如需修改请使用右侧编辑按钮' : undefined}
                      value={row.fields.training_content}
                      onChange={(e) => patchRow(idx, { training_content: e.target.value })}
                    />
                  </td>
                  <td>
                    <textarea
                      className="pt-in"
                      rows={2}
                      placeholder="日期 时间段，多场换行"
                      value={row.fields.actual_time}
                      onChange={(e) => patchRow(idx, { actual_time: e.target.value })}
                    />
                  </td>
                  <td>
                    <textarea
                      className="pt-in"
                      rows={2}
                      disabled={!!row.record}
                      title={row.record ? '与年度培训计划一致，如需修改请使用右侧编辑按钮' : undefined}
                      value={row.fields.target_audience}
                      onChange={(e) => patchRow(idx, { target_audience: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="pt-in"
                      placeholder="内训/外训"
                      value={row.fields.training_type}
                      onChange={(e) => patchRow(idx, { training_type: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="pt-in"
                      placeholder="笔试/口试"
                      value={row.fields.tracking_assessment_method}
                      onChange={(e) =>
                        patchRow(idx, { tracking_assessment_method: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <div className="flex items-center justify-center gap-1.5 py-1">
                      <span
                        className={`pt-pill ${row.fields.is_completed === true ? 'pt-pill-on-green' : ''}`}
                        onClick={() => patchRow(idx, { is_completed: true })}
                      >
                        <CheckCircleOutlined />是
                      </span>
                      <span
                        className={`pt-pill ${row.fields.is_completed === false ? 'pt-pill-on-red' : ''}`}
                        onClick={() => patchRow(idx, { is_completed: false })}
                      >
                        <CloseCircleOutlined />否
                      </span>
                    </div>
                  </td>
                  <td>
                    <input
                      className="pt-in"
                      placeholder="跟踪人"
                      value={row.fields.tracker}
                      onChange={(e) => patchRow(idx, { tracker: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="pt-in"
                      type="date"
                      value={row.fields.track_date}
                      onChange={(e) => patchRow(idx, { track_date: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="pt-in"
                      placeholder="备注"
                      value={row.fields.remarks}
                      onChange={(e) => patchRow(idx, { remarks: e.target.value })}
                    />
                  </td>
                  <td className="pt-gutter">
                    <div className="flex items-center justify-center gap-0.5">
                      <Button
                        className="pt-op"
                        size="small"
                        type="text"
                        icon={<EditOutlined />}
                        title={`编辑第 ${idx + 1} 行`}
                        onClick={() => handleOpenEdit(idx)}
                      />
                      <Button
                        className="pt-op"
                        size="small"
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        title={`删除第 ${idx + 1} 行`}
                        onClick={() => handleDeleteRow(idx)}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Spin>

      {/* 编辑弹窗（全字段可编辑） */}
      <Modal
        title="编辑跟踪记录"
        open={editingIndex !== null}
        onOk={handleSaveEdit}
        onCancel={() => setEditingIndex(null)}
        width={680}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={editForm}
          layout="vertical"
          key={editingIndex ?? -1}
          initialValues={
            editingIndex !== null && rows[editingIndex]
              ? toFormValues(rows[editingIndex])
              : {}
          }
        >
          <Form.Item name="training_content" label="培训内容或使用教材">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="actual_time"
            label="实际培训时间"
            extra="每场一行，格式：日期 时间段（如 8月15日 14:00-16:00），多场换行继续"
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="target_audience" label="培训对象">
            <Input.TextArea rows={2} />
          </Form.Item>
          <div className="grid grid-cols-2 gap-4">
            <Form.Item name="training_type" label="培训类型">
              <Input placeholder="内训/外训" />
            </Form.Item>
            <Form.Item name="tracking_assessment_method" label="考核方式">
              <Input placeholder="笔试/口试/实操" />
            </Form.Item>
          </div>
          <Form.Item name="is_completed_opt" label="是否按照计划完成">
            <Radio.Group
              options={[
                { label: '是', value: 'true' },
                { label: '否', value: 'false' },
                { label: '未跟踪', value: 'null' },
              ]}
              optionType="button"
              buttonStyle="solid"
            />
          </Form.Item>
          <div className="grid grid-cols-2 gap-4">
            <Form.Item name="tracker" label="跟踪人">
              <Input />
            </Form.Item>
            <Form.Item name="track_date" label="跟踪日期">
              <DatePicker className="w-full" />
            </Form.Item>
          </div>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
