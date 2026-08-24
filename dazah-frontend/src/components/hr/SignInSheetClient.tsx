'use client'

import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  App,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  TimePicker,
} from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { Employee } from '@/types/hr'
import type { ExportedDoc, TrainingDocExporter, TrainingSessionData } from '@/types/hr'
import { fetchEmployees } from '@/lib/api/hr'
import { generateTrainingSignInSheet, checkTrainingConflict } from '@/actions/hr'
import { fetchTrainingDepartments } from '@/lib/api/client/hr'
import { downloadBytes } from '@/lib/download'
import InstructorAutoComplete from './InstructorAutoComplete'
import TrainingDocStyle from './trainingDocStyle'
import { resolveTrainingDept, unify201Dept, ensureDeptMappings, useDeptMappings } from './trainingDept'

const PER_PAGE = 42 // 每页 42 人（左 21 + 右 21）
const PER_SIDE = 21

const METHOD_OPTIONS = ['面授', '实操', '函授', '远程教育', '其他']

interface Props {
  sessionData: TrainingSessionData
  onSessionChange: (data: TrainingSessionData) => void
  /** 注册导出器，供顶部"一键导出"聚合调用 */
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
  /** 当前会话 ID，用于冲突检测时排除自身 */
  sessionId?: string
}

export default function SignInSheetClient({ sessionData, onSessionChange, registerExporter, sessionId }: Props) {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [exporting, setExporting] = useState(false)
  const [departments, setDepartments] = useState<{ value: string; label: string }[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [selectedDepts, setSelectedDepts] = useState<string[]>([])
  // 冲突检测 effect：用户修改日期/时间/授课人/参训人员后 500ms 触发检测
  useEffect(() => {
    if (!sessionData.training_date || !sessionData.training_time_start || !sessionData.training_time_end) {
      return
    }

    const timer = setTimeout(async () => {
      try {
        const res = await checkTrainingConflict({
          training_date: sessionData.training_date!,
          time_start: sessionData.training_time_start!,
          time_end: sessionData.training_time_end!,
          instructor: sessionData.instructor || undefined,
          trainees: sessionData.employee_names || [],
          exclude_session_id: sessionId || undefined,
        })
        if (res.data.has_conflict) {
          showConflictModal(res.data)
        }
      } catch {
        // ignore
      }
    }, 500)

    return () => clearTimeout(timer)
  }, [sessionData.training_date, sessionData.training_time_start, sessionData.training_time_end, sessionData.instructor, sessionData.employee_names, sessionId])

  // 使用推荐时间段
  const handleUseSuggestedTime = (slot: { start: string; end: string }) => {
    form.setFieldsValue({
      training_time: [dayjs(slot.start, 'HH:mm'), dayjs(slot.end, 'HH:mm')],
    })
  }

  // 冲突弹窗
  const showConflictModal = (data: {
    instructor_conflicts: { training_name: string; time_range: string; conflict_depts: string[]; conflict_count: number }[]
    trainee_conflicts: { training_name: string; time_range: string; names: string[]; conflict_count: number }[]
    suggested_times: { start: string; end: string }[]
  }) => {
    const parts: React.ReactNode[] = []

    if (data.instructor_conflicts.length > 0) {
      parts.push(
        <div key="inst" className="mb-3">
          <div className="font-medium text-red-600 mb-1">授课人冲突</div>
          {data.instructor_conflicts.map((c, i) => (
            <div key={i} className="text-[13px] text-gray-700">
              {sessionData.instructor} 在 {c.time_range} 与「{c.training_name}」冲突
              {c.conflict_depts.length > 0 && (
                <>（涉及 {c.conflict_count} 个部门：{c.conflict_depts.slice(0, 5).join('、')}{c.conflict_count > 5 ? '...' : ''}）</>
              )}
            </div>
          ))}
        </div>,
      )
    }

    if (data.trainee_conflicts.length > 0) {
      parts.push(
        <div key="trainee" className="mb-3">
          <div className="font-medium text-orange-600 mb-1">参训人员冲突</div>
          {data.trainee_conflicts.map((c, i) => (
            <div key={i} className="text-[13px] text-gray-700">
              {c.conflict_count} 人在 {c.time_range} 正在参加「{c.training_name}」：
              {c.names.slice(0, 5).join('、')}{c.names.length > 5 ? '...' : ''}
            </div>
          ))}
        </div>,
      )
    }

    if (data.suggested_times.length > 0) {
      parts.push(
        <div key="suggest">
          <div className="font-medium text-blue-600 mb-1">推荐时间段</div>
          <div className="flex gap-2">
            {data.suggested_times.map((s, i) => (
              <Button
                key={i}
                size="small"
                type="primary"
                onClick={() => {
                  handleUseSuggestedTime(s)
                  Modal.destroyAll()
                }}
              >
                {s.start}~{s.end}
              </Button>
            ))}
          </div>
        </div>,
      )
    }

    modal.warning({
      title: '存在时间冲突',
      width: 520,
      content: <div>{parts}</div>,
      okText: '知道了',
    })
  }

  // 人员名单由顶部"培训范围"控制条统一提供（配置人员/加载/拉取新员工）
  const employeeNames: string[] = sessionData.employee_names || []
  const trainingMethod: string | undefined = Form.useWatch('training_method', form)

  useEffect(() => {
    ensureDeptMappings().catch(() => {})
    fetchTrainingDepartments()
      .then((depts) => {
        setDepartments(depts.map((d) => ({ value: d, label: d })))
      })
      .catch(() => setDepartments([]))
    fetchEmployees({ page_size: 200 })
      .then((res) => setEmployees(res.data || []))
      .catch(() => setEmployees([]))
  }, [])

  // 部门列取值：优先人员配置自带的部门，其次 HR 员工表（按培训规则解析：一级不在培训部门列表时回退二级）
  const trainingDeptNames = useMemo(() => departments.map((d) => d.value), [departments])
  const { version: mappingVersion } = useDeptMappings()
  const nameToDeptMap = useMemo(() => {
    const raw: Record<string, string> = { ...(sessionData.employee_dept_map || {}) }
    employees.forEach((e) => {
      if (e.name && !raw[e.name]) {
        raw[e.name] = resolveTrainingDept(e.department, e.sub_department, trainingDeptNames)
      }
    })
    // 显示层统一：MC/DR 对外显示为 201二车间（存储的 employee_dept_map 仍保留真实部门）
    const map: Record<string, string> = {}
    for (const [k, v] of Object.entries(raw)) map[k] = unify201Dept(v)
    return map
  }, [employees, sessionData.employee_dept_map, trainingDeptNames, mappingVersion])

  // 行内编辑姓名：空行输入即新增人员；清空保留空行（尾部空行自动收起）
  const handleNameEdit = (idx: number, value: string) => {
    const next = [...employeeNames]
    while (next.length <= idx) next.push('')
    next[idx] = value
    while (next.length && !next[next.length - 1].trim()) next.pop()
    onSessionChange({ employee_names: next })
  }

  // 行内编辑部门
  const handleDeptEdit = (name: string, value: string) => {
    if (!name.trim()) return
    onSessionChange({
      employee_dept_map: { ...(sessionData.employee_dept_map || {}), [name]: value },
    })
  }

  const handleDeptChange = (values: string[]) => {
    setSelectedDepts(values)
    const chosen = employees.filter((e) => {
      const resolved = resolveTrainingDept(e.department, e.sub_department, trainingDeptNames)
      return values.includes(e.department || '') || (resolved !== '' && values.includes(resolved))
    })
    const deptMap: Record<string, string> = {}
    chosen.forEach((e) => {
      const d = resolveTrainingDept(e.department, e.sub_department, trainingDeptNames) || e.department
      if (e.name && d) deptMap[e.name] = d
    })
    onSessionChange({
      trainee_departments: values,
      // 公司级培训落款部门固定人事行政部（不随受训部门变化）；部门级才取第一个受训部门
      department: sessionData.training_level === '部门级' ? values[0] : (sessionData.department || '人事行政部'),
      employee_names: chosen.map((e) => e.name),
      employee_dept_map: deptMap,
    })
  }

  // 从共享 session 恢复（仅首次）
  const [sessionApplied, setSessionApplied] = useState(false)
  useEffect(() => {
    if (sessionApplied || !sessionData.training_date) return
    const fields: Record<string, any> = {}
    if (sessionData.training_date) fields.training_date = dayjs(sessionData.training_date)
    if (sessionData.training_time_start && sessionData.training_time_end) {
      fields.training_time = [dayjs(sessionData.training_time_start, 'HH:mm'), dayjs(sessionData.training_time_end, 'HH:mm')]
    }
    if (sessionData.topic) fields.topic = sessionData.topic
    if (sessionData.training_method) fields.training_method = sessionData.training_method
    if (sessionData.instructor) fields.instructor = sessionData.instructor
    if (sessionData.actual_count != null) fields.actual_count = sessionData.actual_count
    if (sessionData.trainee_departments) {
      const uni = [...new Set(sessionData.trainee_departments.map(unify201Dept))].filter(Boolean)
      fields.departments = uni
      setSelectedDepts(uni)
    }
    form.setFieldsValue(fields)
    setSessionApplied(true)
  }, [sessionData, form, sessionApplied])

  // 顶部加载/变更人员后，受训部门按人员部门自动填充（实时同步，非仅首次）
  const lastDeptsRef = useRef<string[] | undefined>(undefined)
  useEffect(() => {
    const depts = [...new Set((sessionData.trainee_departments || []).map(unify201Dept))].filter(Boolean)
    if (!depts.length) return
    const prev = lastDeptsRef.current
    const same = !!prev && prev.length === depts.length && depts.every((d) => prev.includes(d))
    if (same) return
    lastDeptsRef.current = depts
    setSelectedDepts(depts)
    form.setFieldsValue({ departments: depts })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionData.trainee_departments])

  // 记录本地编辑过的题目，避免外部同步覆盖用户输入时 caret 跳动
  const lastTopicRef = useRef<string | undefined>(undefined)

  // 外部（如勾选培训附件）更新 session.topic 时实时同步到题目输入框
  useEffect(() => {
    if (sessionData.topic !== undefined && sessionData.topic !== lastTopicRef.current) {
      lastTopicRef.current = sessionData.topic
      form.setFieldsValue({ topic: sessionData.topic })
    }
  }, [sessionData.topic, form])

  // 实时同步共享 session（其他表修改的日期/时间/授课人/方式回流）
  // 仅当与当前表单值不同才写入；dayjs 只在此处创建、不进入依赖/状态，避免循环引用告警
  useEffect(() => {
    const cur = form.getFieldsValue()
    const fields: Record<string, any> = {}
    if (sessionData.training_date) {
      const v = dayjs(sessionData.training_date)
      if (!cur.training_date || cur.training_date.format('YYYY-MM-DD') !== v.format('YYYY-MM-DD')) {
        fields.training_date = v
      }
    }
    if (sessionData.training_time_start && sessionData.training_time_end) {
      const t0 = dayjs(sessionData.training_time_start, 'HH:mm')
      const t1 = dayjs(sessionData.training_time_end, 'HH:mm')
      const c = cur.training_time
      if (!c || c[0]?.format('HH:mm') !== sessionData.training_time_start || c[1]?.format('HH:mm') !== sessionData.training_time_end) {
        fields.training_time = [t0, t1]
      }
    }
    if (sessionData.instructor && cur.instructor !== sessionData.instructor) fields.instructor = sessionData.instructor
    if (sessionData.training_method && cur.training_method !== sessionData.training_method) fields.training_method = sessionData.training_method
    if (Object.keys(fields).length) form.setFieldsValue(fields)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionData.training_date, sessionData.training_time_start, sessionData.training_time_end, sessionData.instructor, sessionData.training_method])

  // 上报共享 session
  const handleFormChange = useCallback((_c: any, all: any) => {
    if (all.topic !== undefined) lastTopicRef.current = all.topic
    const data: TrainingSessionData = {}
    if (all.training_date) data.training_date = all.training_date.format('YYYY-MM-DD')
    if (all.training_time?.[0]) {
      data.training_time_start = all.training_time[0].format('HH:mm')
      data.training_time_end = all.training_time[1].format('HH:mm')
    }
    if (all.topic) data.topic = all.topic
    if (all.training_method) data.training_method = all.training_method
    if (all.instructor) data.instructor = all.instructor
    if (all.actual_count != null) data.actual_count = all.actual_count
    if (selectedDepts.length > 0) {
      data.trainee_departments = selectedDepts
      // 公司级培训落款部门固定人事行政部：不覆盖 department（合并更新保持原值）；部门级才取第一个受训部门
      if (sessionData.training_level === '部门级') data.department = selectedDepts[0]
    }
    onSessionChange(data)
  }, [onSessionChange, selectedDepts, sessionData.training_level])

  // ── 导出签到表（APP3）：页内按钮与顶部"一键导出"共用同一生成逻辑 ──
  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    if (!sessionData.training_date || !sessionData.topic) return null
    const { bytes, filename } = await generateTrainingSignInSheet({
      training_date: sessionData.training_date,
      training_time_start: sessionData.training_time_start,
      training_time_end: sessionData.training_time_end,
      department: [...new Set((sessionData.trainee_departments || []).map(unify201Dept))].filter(Boolean).join('、') || unify201Dept(sessionData.department),
      topic: sessionData.topic,
      instructor: sessionData.instructor,
      location: sessionData.location,
      training_method: sessionData.training_method,
      employee_names: sessionData.employee_names || [],
      remarks: form.getFieldValue('remarks') || undefined,
    })
    return [{ name: filename, bytes }]
  }

  useEffect(() => {
    registerExporter?.('sign_in', buildExportEntries)
  })

  const handleExport = async () => {
    if (!sessionData.training_date) {
      message.warning('请先选择培训日期')
      return
    }
    if (!sessionData.topic) {
      message.warning('请先填写培训题目')
      return
    }
    setExporting(true)
    try {
      const entries = await buildExportEntries()
      if (!entries) return
      for (const e of entries) downloadBytes(e.bytes, e.name)
      message.success('培训签到表已生成')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '生成失败')
    } finally {
      setExporting(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(employeeNames.length / PER_PAGE))

  /** 渲染一页 APP3 签到表文档（输入框嵌入单元格） */
  const renderPage = (pageIdx: number) => {
    const start = pageIdx * PER_PAGE
    const pageNames = employeeNames.slice(start, start + PER_PAGE)

    const dataRows = Array.from({ length: PER_SIDE }, (_, i) => {
      const ln = pageNames[i] || ''
      const rn = pageNames[i + PER_SIDE] || ''
      return (
        <tr key={i} className="sign-row" style={{ background: i % 2 === 1 ? '#f7f9fb' : undefined }}>
          <td className="sign-idx">{ln ? start + i + 1 : ''}</td>
          <td className="sign-cell">
            <Input value={ln} onChange={(e) => handleNameEdit(start + i, e.target.value)} style={{ padding: '0 2px' }} />
          </td>
          <td className="sign-cell">
            <Input value={ln ? nameToDeptMap[ln] || '' : ''} onChange={(e) => handleDeptEdit(ln, e.target.value)} style={{ padding: '0 2px' }} />
          </td>
          <td className="sign-cell"></td>
          <td className="sign-idx">{rn ? start + i + PER_SIDE + 1 : ''}</td>
          <td className="sign-cell">
            <Input value={rn} onChange={(e) => handleNameEdit(start + i + PER_SIDE, e.target.value)} style={{ padding: '0 2px' }} />
          </td>
          <td className="sign-cell">
            <Input value={rn ? nameToDeptMap[rn] || '' : ''} onChange={(e) => handleDeptEdit(rn, e.target.value)} style={{ padding: '0 2px' }} />
          </td>
          <td className="sign-cell"></td>
        </tr>
      )
    })

    return (
      <div key={pageIdx} className="signin-doc-page a4-page doc-area">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '9pt', color: '#000', marginBottom: 6 }}>
          <span style={{ letterSpacing: 1 }}>APP3-SMP-HR-002-14</span>
          <span>P{pageIdx + 1}/{totalPages}</span>
        </div>
        <div style={{ textAlign: 'center', fontSize: '16pt', fontWeight: 800, letterSpacing: 4, margin: '4px 0 18px', color: '#000' }}>
          培训签到表
        </div>

        <table className="sign-table sign-doc">
          <colgroup>
            <col style={{ width: '6%' }} />
            <col style={{ width: '22%' }} />
            <col style={{ width: '16%' }} />
            <col style={{ width: '6%' }} />
            <col style={{ width: '6%' }} />
            <col style={{ width: '22%' }} />
            <col style={{ width: '16%' }} />
            <col style={{ width: '6%' }} />
          </colgroup>
          <tbody>
            {/* R0 培训日期 | 受训部门 */}
            <tr>
              <td className="sign-info" colSpan={4}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="sign-lbl">培训日期：</span>
                  <Form.Item name="training_date" noStyle rules={[{ required: true, message: '请选择培训日期' }]}>
                    <DatePicker style={{ flex: 1 }} placeholder="选择日期" />
                  </Form.Item>
                </div>
              </td>
              <td className="sign-info" colSpan={4}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="sign-lbl">受训部门：</span>
                  <Form.Item name="departments" noStyle rules={[{ required: true, message: '请选择受训部门' }]}>
                    <Select
                      mode="tags"
                      style={{ flex: 1 }}
                      placeholder="选择或输入受训部门"
                      options={departments.map((d) => ({ value: d.value, label: d.label }))}
                      onChange={handleDeptChange}
                    />
                  </Form.Item>
                </div>
              </td>
            </tr>
            {/* R1 培训方式（模板原样 □/☑ 勾选） */}
            <tr>
              <td className="sign-info" colSpan={8}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
                  <span className="sign-lbl">培训方式：</span>
                  {METHOD_OPTIONS.map((m) => {
                    const on = trainingMethod === m
                    return (
                      <span
                        key={m}
                        className={`cb-big${on ? ' on' : ''}`}
                        onClick={() => form.setFieldsValue({ training_method: on ? undefined : m })}
                      >
                        <i className="cb-box">{on ? '☑' : '□'}</i>{m}{m === '其他' ? '：' : ''}
                      </span>
                    )
                  })}
                  <Form.Item name="training_method_other" noStyle>
                    <Input placeholder="" style={{ width: 140 }} />
                  </Form.Item>
                  <Form.Item name="training_method" noStyle>
                    <Input type="hidden" />
                  </Form.Item>
                </div>
              </td>
            </tr>
            {/* R2 应受训人数 | 实际受训人数合计 */}
            <tr>
              <td className="sign-info" colSpan={8}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span className="sign-lbl">应受训人数：</span>
                  <strong style={{ color: '#1677ff', fontSize: 15 }}>{employeeNames.filter((n) => n.trim()).length}</strong>
                  <span>人</span>
                  <span className="sign-lbl" style={{ marginLeft: 20 }}>实际受训人数合计：</span>
                  <Form.Item name="actual_count" noStyle>
                    <InputNumber style={{ width: 80 }} min={0} />
                  </Form.Item>
                  <span>人</span>
                </div>
              </td>
            </tr>
            {/* R3 标签行 */}
            <tr className="sign-head">
              <td colSpan={2}>培训时间</td>
              <td colSpan={4}>培训题目或内容概要</td>
              <td colSpan={2}>授课人</td>
            </tr>
            {/* R4 值行 */}
            <tr>
              <td className="sign-info" colSpan={2}>
                <Form.Item name="training_time" noStyle>
                  <TimePicker.RangePicker format="HH:mm" style={{ width: '100%' }} />
                </Form.Item>
              </td>
              <td className="sign-info" colSpan={4}>
                <Form.Item name="topic" noStyle rules={[{ required: true, message: '请填写培训题目' }]}>
                  <Input.TextArea
                    placeholder="培训题目或内容概要"
                    autoSize={{ minRows: 1, maxRows: 8 }}
                    style={{ resize: 'none' }}
                  />
                </Form.Item>
              </td>
              <td className="sign-info" colSpan={2}>
                <Form.Item name="instructor" noStyle>
                  <InstructorAutoComplete placeholder="授课人（拼音/中文选择培训师，可手输）" style={{ width: '100%' }} />
                </Form.Item>
              </td>
            </tr>
            {/* R5 表头 */}
            <tr className="sign-head">
              <td>序号</td>
              <td>受训人员姓名</td>
              <td>受训人员部门</td>
              <td>签到</td>
              <td>序号</td>
              <td>受训人员姓名</td>
              <td>受训人员部门</td>
              <td>签到</td>
            </tr>
            {dataRows}
            {/* 备注 */}
            <tr>
              <td className="sign-info" colSpan={8}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="sign-lbl">备注：（未参加培训人员处理方式）</span>
                  <Form.Item name="remarks" noStyle>
                    <Input placeholder="" style={{ flex: 1 }} />
                  </Form.Item>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <Form form={form} layout="inline" onValuesChange={handleFormChange}>
      <div className="space-y-4" style={{ width: '100%' }}>
        <Space className="mb-2 doc-toolbar">
          <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
            导出签到表
          </Button>
        </Space>

        {/* 冲突提示已改为 Modal 弹窗 */}

        {/* APP3 文档（打印区域） */}
        <div id="print-area">
          {Array.from({ length: totalPages }, (_, i) => renderPage(i))}
        </div>
      </div>

      <TrainingDocStyle />
      <style jsx global>{`
        .sign-table { width: 100%; border-collapse: collapse; font-size: 10.5pt; table-layout: fixed; border: 1.5px solid #000; background: #fff; }
        .sign-table td { border: 1px solid #000; vertical-align: middle; }
        .sign-info { padding: 9px 12px; }
        .sign-lbl { font-weight: 600; color: #000; white-space: nowrap; }
        .sign-head td { background: #fff; font-weight: 700; color: #000; letter-spacing: 1px; text-align: center; padding: 10px 8px; border-top: 1.5px solid #000; border-bottom: 1.5px solid #000; }
        .sign-cell { padding: 6px 10px; height: 34px; color: #000; }
        .sign-idx { text-align: center; color: #000; font-variant-numeric: tabular-nums; padding: 6px 4px; height: 34px; font-weight: 600; }
        .sign-row { transition: background .15s ease; }
        .sign-row:hover td { background: #f0f0f0 !important; }
        .sign-method-opt { cursor: pointer; user-select: none; white-space: nowrap; padding: 6px 18px; border-radius: 16px; border: 1px solid #000; color: #000; transition: all .15s; background: #fff; font-size: 10.5pt; }
        .sign-method-opt:hover { background: #f0f0f0; }
        .sign-method-on { cursor: pointer; user-select: none; white-space: nowrap; padding: 6px 18px; border-radius: 16px; border: 1px solid #000; background: #000; color: #fff; font-weight: 600; transition: all .15s; font-size: 10.5pt; }
        .sign-method-on:hover { background: #333; }
        /* 文档模式：去掉内嵌控件边框，填空用下划线，只保留表格格线 */
        .sign-doc .ant-input, .sign-doc .ant-input-affix-wrapper, .sign-doc .ant-picker,
        .sign-doc .ant-select .ant-select-selector, .sign-doc .ant-input-number,
        .sign-doc .ant-input-number-input, .sign-doc textarea.ant-input {
          border: none !important; box-shadow: none !important; background: transparent !important; border-radius: 0 !important;
        }
        .sign-doc .ant-input:not(textarea), .sign-doc .ant-picker-input > input,
        .sign-doc .ant-input-number-input, .sign-doc .ant-select-selector {
          border-bottom: 1px solid #000 !important;
        }
        /* 人员行内编辑：默认像普通文本，悬停/聚焦时提示可编辑 */
        .sign-doc td.sign-cell .ant-input { border-bottom: none !important; }
        .sign-doc td.sign-cell .ant-input:hover { background: #f0f0f0 !important; }
        .sign-doc td.sign-cell .ant-input:focus { background: #f0f0f0 !important; }
        @media print {
          body * { visibility: hidden; }
          #print-area, #print-area * { visibility: visible; }
          #print-area { position: absolute; left: 0; top: 0; width: 100%; }
          .signin-doc-page { page-break-after: always; box-shadow: none !important; border: none !important; border-radius: 0 !important; padding: 0 !important; margin: 0 0 12px 0 !important; }
          .signin-doc-page:last-child { page-break-after: auto; }
          .sign-table { border: 1px solid #000 !important; }
          .sign-table td { border: 1px solid #000 !important; }
          .sign-head td { background: #fff !important; }
          .sign-row:hover td, .sign-row td { background: transparent !important; }
          .sign-method-on { background: #fff !important; color: #000 !important; border: 1px solid #000 !important; }
          .sign-method-opt { border: 1px solid #000 !important; }
        }
      `}</style>
    </Form>
  )
}
