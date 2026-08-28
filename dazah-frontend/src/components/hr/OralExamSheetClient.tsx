'use client'

import { useEffect, useState } from 'react'
import { Alert, App, Button, Input, Space } from 'antd'
import { PlusOutlined, DeleteOutlined, DownloadOutlined, RobotOutlined } from '@ant-design/icons'
import type { ExportedDoc, TrainingDocExporter, TrainingSessionData } from '@/types/hr'
import { upsertTrainingSession, upsertTrainingDocument, generateOralExamResult } from '@/actions/hr'
import { downloadBytes } from '@/lib/download'
import TrainingDocStyle from './trainingDocStyle'
import { unify201Dept, ensureDeptMappings } from './trainingDept'
import OralExamAiModal from './OralExamAiModal'

interface QuestionRow {
  question: string
  answer: string
}

interface PersonRow {
  name: string
  department: string
  question_nos: string
  result: '' | '合格' | '不合格'
  remark: string
  /** 手动添加行（……行点击添加） */
  manual?: boolean
}

export interface OralExamPayload {
  content: string
  training_date: string
  questions: QuestionRow[]
  persons: PersonRow[]
  assessor: string
}

interface Props {
  sessionData: TrainingSessionData
  initialPayload?: OralExamPayload | null
  onSessionIdChange?: (id: string) => void
  /** 评估表考核方式为"口试"时才自动填写 */
  active?: boolean
  assessmentMethod?: string
  registerDocBuilder?: (type: string, fn: () => Record<string, unknown> | null) => void
  /** 注册导出器，供顶部"一键导出"聚合调用 */
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
}

/** 口试培训考核结果表（APP10-SMP-HR-002-14）：页面版式与模板 1:1 */
export default function OralExamSheetClient({ sessionData, initialPayload, onSessionIdChange, active = true, assessmentMethod, registerDocBuilder, registerExporter }: Props) {
  const { message } = App.useApp()
  const [content, setContent] = useState('')
  const [trainingDate, setTrainingDate] = useState('')
  const [assessor, setAssessor] = useState('')
  const [questions, setQuestions] = useState<QuestionRow[]>([{ question: '', answer: '' }, { question: '', answer: '' }, { question: '', answer: '' }])
  const [persons, setPersons] = useState<PersonRow[]>([])
  const [exporting, setExporting] = useState(false)
  const [aiModalOpen, setAiModalOpen] = useState(false)

  // 同步共享 session（培训内容/日期/评估人/人员）
  useEffect(() => {
    if (initialPayload) {
      setContent(initialPayload.content || '')
      setTrainingDate(initialPayload.training_date || '')
      setAssessor(initialPayload.assessor || '')
      if (initialPayload.questions?.length) setQuestions(initialPayload.questions)
      if (initialPayload.persons?.length) setPersons(initialPayload.persons)
      return
    }
    // 仅当考核方式为"口试"时才随签到表自动填充；评估人/日期落款由用户手填，不自动带出
    if (!active) return
    setContent((prev) => prev || sessionData.topic || '')
    setTrainingDate((prev) => prev || sessionData.training_date || '')

  }, [sessionData.topic, sessionData.training_date, sessionData.instructor, initialPayload, active])

  // 人员由共享 session 带出（保留已填内容与手动行）
  useEffect(() => {
    ensureDeptMappings().catch(() => {})
    if (!active) return
    const names = sessionData.employee_names || []
    const deptMap = sessionData.employee_dept_map || {}
    setPersons((prev) => {
      const manual = prev.filter((p) => p.manual)
      return [
        ...names.map((n) => {
          const old = prev.find((p) => p.name === n && !p.manual)
          return (
            old || {
              name: n,
              department: unify201Dept(deptMap[n]),
              question_nos: '',
              result: '' as const,
              remark: '',
            }
          )
        }),
        ...manual,
      ]
    })

  }, [sessionData.employee_names, sessionData.employee_dept_map, active])

  const buildPayload = (): OralExamPayload => ({
    content,
    training_date: trainingDate,
    questions,
    persons,
    assessor,
  })

  const saveSession = async (): Promise<string> => {
    const sessionId = await upsertTrainingSession({
      training_level: sessionData.training_level,
      plan_year: sessionData.plan_year,
      department: sessionData.department,
      trainee_departments: sessionData.trainee_departments,
      topic: sessionData.topic,
      training_date: trainingDate || sessionData.training_date || undefined,
      time_start: sessionData.training_time_start,
      time_end: sessionData.training_time_end,
      training_method: sessionData.training_method,
      instructor: assessor || sessionData.instructor,
      actual_count: sessionData.actual_count,
      employee_names: sessionData.employee_names,
      employee_dept_map: sessionData.employee_dept_map,
    })
    onSessionIdChange?.(sessionId)
    return sessionId
  }

  // 注册草稿序列化函数，供顶部"保存"一键调用（无内容则跳过）
  useEffect(() => {
    registerDocBuilder?.('oral_exam', () => {
      const p = buildPayload()
      const hasContent =
        p.content || p.assessor || p.persons.length > 0 || p.questions.some((q) => q.question || q.answer)
      return hasContent ? (p as unknown as Record<string, unknown>) : null
    })
  })

  // 生成口试考核结果表文档（页内按钮与顶部"一键导出"共用；无内容返回 null 跳过）
  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    const hasContent =
      content || assessor || persons.some((p) => p.name && p.name.trim()) || questions.some((q) => q.question || q.answer)
    if (!hasContent) return null
    const { bytes, filename } = await generateOralExamResult({
      training_content: content,
      training_date: trainingDate,
      questions: questions.map((q, i) => ({ no: String(i + 1), question: q.question, answer: q.answer })),
      persons: persons
        .filter((p) => p.name && p.name.trim())
        .map((p) => ({
          name: p.name,
          department: p.department,
          question_nos: p.question_nos,
          result: p.result || undefined,
          remark: p.remark,
        })),
      assessor,
    })
    return [{ name: filename, bytes }]
  }

  useEffect(() => {
    // 一键导出仅当考核方式为"口试"时才包含口试表；页内手动按钮不受此限
    registerExporter?.('oral_exam', async () => (active ? buildExportEntries() : null))
  })

  const handleExport = async () => {
    setExporting(true)
    try {
      const sessionId = await saveSession()
      await upsertTrainingDocument({
        session_id: sessionId,
        doc_type: 'oral_exam',
        title: `口试培训考核结果表_${content || trainingDate}`,
        payload: buildPayload() as unknown as Record<string, unknown>,
      })
      const entries = await buildExportEntries()
      if (!entries) return
      for (const e of entries) downloadBytes(e.bytes, e.name)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="doc-area">
      <TrainingDocStyle />
      {!active && (
        <Alert
          type="info"
          showIcon
          className="mb-3"
          title={`评估表当前考核方式为"${assessmentMethod || '未选择'}"，口试评估表仅在考核方式选择"口试"时自动填写培训信息。`}
        />
      )}
      <Space className="mb-2 doc-toolbar">
        <Button icon={<PlusOutlined />} onClick={() => setQuestions((q) => [...q, { question: '', answer: '' }])}>
          增加问题行
        </Button>
        <Button icon={<DeleteOutlined />} disabled={questions.length <= 1} onClick={() => setQuestions((q) => q.slice(0, -1))}>
          删除问题行
        </Button>
        <Button
          type="primary"
          icon={<RobotOutlined />}
          disabled={!active}
          onClick={() => setAiModalOpen(true)}
          title={active ? '根据培训文件内容 AI 生成问答题（问题+参考答案）' : '仅在考核方式选择"口试"时可用'}
        >
          AI 出题
        </Button>
        <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
          导出口试考核结果表
        </Button>
      </Space>

      <OralExamAiModal
        open={aiModalOpen}
        onClose={() => setAiModalOpen(false)}
        sourceFiles={sessionData.checked_content}
        contentText={content}
        onConfirm={(qs) => {
          // 追加回填：优先填充已有空行（空行不算已有内容），不够再追加新行
          setQuestions((prev) => {
            const next = [...prev]
            let emptyIdx = 0
            for (const q of qs) {
              while (
                emptyIdx < next.length &&
                (next[emptyIdx].question.trim() || next[emptyIdx].answer.trim())
              ) {
                emptyIdx++
              }
              if (emptyIdx < next.length) {
                next[emptyIdx] = { question: q.question, answer: q.answer }
                emptyIdx++
              } else {
                next.push({ question: q.question, answer: q.answer })
              }
            }
            return next
          })
          message.success(`已回填 ${qs.length} 道口试问答题`)
        }}
      />

      <div className="a4-page">
      <div className="doc-bar"><span className="doc-no">APP10-SMP-HR-002-14</span><span>P1/1</span></div>
      <table className="doc-table">
        <colgroup>
          <col style={{ width: '12%' }} />
          <col style={{ width: '14%' }} />
          <col style={{ width: '13%' }} />
          <col style={{ width: '13%' }} />
          <col style={{ width: '12%' }} />
          <col style={{ width: '12%' }} />
          <col style={{ width: '12%' }} />
          <col style={{ width: '12%' }} />
        </colgroup>
        <tbody>
          <tr>
            <td colSpan={8} style={{ textAlign: 'center', fontWeight: 700, fontSize: '16pt', padding: '10px 0', letterSpacing: 2 }}>
              口试培训考核结果表
            </td>
          </tr>
          <tr>
            <td className="doc-lbl">培训内容</td>
            <td colSpan={3}>
              <Input value={content} onChange={(e) => setContent(e.target.value)} />
            </td>
            <td className="doc-lbl">培训日期</td>
            <td colSpan={3}>
              <Input value={trainingDate} onChange={(e) => setTrainingDate(e.target.value)} placeholder="YYYY.MM.DD" />
            </td>
          </tr>
          <tr>
            <td colSpan={8} className="doc-lbl" style={{ textAlign: 'center', padding: '8px 0' }}>
              培训考核问题及参考答案
            </td>
          </tr>
          <tr className="doc-head">
            <td>题号</td>
            <td colSpan={3}>考核问题</td>
            <td colSpan={4}>参考答案</td>
          </tr>
          {questions.map((q, i) => (
            <tr key={i}>
              <td className="doc-idx">{i + 1}</td>
              <td colSpan={3}>
                <Input.TextArea autoSize value={q.question} onChange={(e) => setQuestions((arr) => arr.map((x, j) => (j === i ? { ...x, question: e.target.value } : x)))} />
              </td>
              <td colSpan={4}>
                <Input.TextArea autoSize value={q.answer} onChange={(e) => setQuestions((arr) => arr.map((x, j) => (j === i ? { ...x, answer: e.target.value } : x)))} />
              </td>
            </tr>
          ))}
          <tr
            style={{ cursor: 'pointer' }}
            title="点击添加问题行"
            onClick={() => setQuestions((q) => [...q, { question: '', answer: '' }])}
          >
            <td className="doc-idx">……</td>
            <td colSpan={3} style={{ textAlign: 'center', color: '#64748b' }}>……（点击添加问题行）</td>
            <td colSpan={4} style={{ textAlign: 'center', color: '#64748b' }}>……</td>
          </tr>
          <tr className="doc-head">
            <td>序号</td>
            <td>姓名</td>
            <td>部门/班组</td>
            <td>考核题号</td>
            <td colSpan={2}>考核结果</td>
            <td colSpan={2}>备注</td>
          </tr>
          {persons.map((p, i) => (
            <tr key={`${p.name}-${i}`}>
              <td className="doc-idx">{i + 1}</td>
              <td>
                {p.manual ? (
                  <Input value={p.name} placeholder="姓名" onChange={(e) => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                ) : (
                  p.name
                )}
              </td>
              <td>
                {p.manual ? (
                  <Input value={p.department} placeholder="部门/班组" onChange={(e) => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, department: e.target.value } : x)))} />
                ) : (
                  p.department
                )}
              </td>
              <td>
                <Input value={p.question_nos} onChange={(e) => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, question_nos: e.target.value } : x)))} />
              </td>
              <td colSpan={2} style={{ whiteSpace: 'nowrap' }}>
                <span
                  className={`cb-big${p.result === '合格' ? ' on' : ''}`}
                  style={{ marginRight: 10 }}
                  onClick={() => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, result: x.result === '合格' ? '' : '合格' } : x)))}
                >
                  <i className="cb-box">{p.result === '合格' ? '☑' : '□'}</i>合格
                </span>
                <span
                  className={`cb-big${p.result === '不合格' ? ' on' : ''}`}
                  onClick={() => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, result: x.result === '不合格' ? '' : '不合格' } : x)))}
                >
                  <i className="cb-box">{p.result === '不合格' ? '☑' : '□'}</i>不合格
                </span>
              </td>
              <td colSpan={2}>
                <Input value={p.remark} onChange={(e) => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, remark: e.target.value } : x)))} />
              </td>
            </tr>
          ))}
          <tr
            style={{ cursor: 'pointer' }}
            title="点击添加人员行"
            onClick={() => setPersons((arr) => [...arr, { name: '', department: '', question_nos: '', result: '', remark: '', manual: true }])}
          >
            <td className="doc-idx">……</td>
            <td colSpan={6} style={{ textAlign: 'center', color: '#64748b' }}>……（点击添加人员行）</td>
          </tr>
          <tr>
            <td colSpan={4} />
            <td colSpan={4}>
              评估人/日期：
              <Input style={{ width: 200 }} value={assessor} onChange={(e) => setAssessor(e.target.value)} />
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>
  )
}
