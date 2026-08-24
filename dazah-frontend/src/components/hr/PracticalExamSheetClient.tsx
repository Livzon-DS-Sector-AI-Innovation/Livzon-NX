'use client'

import { useEffect, useState } from 'react'
import { Alert, App, Button, Input, Space, Upload } from 'antd'
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import type { ExportedDoc, TrainingDocExporter, TrainingSessionData } from '@/types/hr'
import { upsertTrainingSession, upsertTrainingDocument, generatePracticalExamResult, importPracticalExamQuestions } from '@/actions/hr'
import { downloadBytes } from '@/lib/download'
import TrainingDocStyle from './trainingDocStyle'
import { unify201Dept, ensureDeptMappings } from './trainingDept'

interface PersonSheet {
  name: string
  department: string
  description: string
}

export interface PracticalExamPayload {
  content: string
  training_date: string
  persons: PersonSheet[]
  assessor: string
}

interface Props {
  sessionData: TrainingSessionData
  initialPayload?: PracticalExamPayload | null
  onSessionIdChange?: (id: string) => void
  /** 评估表考核方式为"实操"时才自动填写 */
  active?: boolean
  assessmentMethod?: string
  registerDocBuilder?: (type: string, fn: () => Record<string, unknown> | null) => void
  /** 注册导出器，供顶部"一键导出"聚合调用 */
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
}

/** 实操培训考核结果表（APP13-SMP-HR-002-14）：每人一张，版式与模板 1:1 */
export default function PracticalExamSheetClient({ sessionData, initialPayload, onSessionIdChange, active = true, assessmentMethod, registerDocBuilder, registerExporter }: Props) {
  const { message } = App.useApp()
  const [content, setContent] = useState('')
  const [trainingDate, setTrainingDate] = useState('')
  const [assessor, setAssessor] = useState('')
  const [persons, setPersons] = useState<PersonSheet[]>([])
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  // 导入的实操试题（R3 共用内容）
  const [examContent, setExamContent] = useState('')

  // 导入实操试题：解析 APP13 格式 docx，把"实操考核情况描述"应用为所有人员的共用试题，并更新培训日期
  const handleImport = async (file: File) => {
    setImporting(true)
    try {
      const res = await importPracticalExamQuestions(file)
      const desc = res.data?.description ?? ''
      const date = res.data?.training_date ?? ''
      setExamContent(desc)
      if (date) setTrainingDate(date)
      if (desc) {
        setPersons((prev) => prev.map((p) => ({ ...p, description: desc })))
      }
      message.success('实操试题已导入')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导入实操试题失败')
    } finally {
      setImporting(false)
    }
  }

  useEffect(() => {
    if (initialPayload) {
      setContent(initialPayload.content || '')
      setTrainingDate(initialPayload.training_date || '')
      setAssessor(initialPayload.assessor || '')
      if (initialPayload.persons?.length) setPersons(initialPayload.persons)
      return
    }
    // 仅当考核方式为"实操"时才随签到表自动填充
    if (!active) return
    setContent((prev) => prev || sessionData.topic || '')
    setTrainingDate((prev) => prev || sessionData.training_date || '')
    setAssessor((prev) => prev || sessionData.instructor || '')

  }, [sessionData.topic, sessionData.training_date, sessionData.instructor, initialPayload, active])

  // 每人一张：由共享 session 人员带出（保留已填描述；session 无人员时保留手动填写）
  useEffect(() => {
    ensureDeptMappings().catch(() => {})
    if (!active) return
    const names = sessionData.employee_names || []
    if (names.length === 0) return
    const deptMap = sessionData.employee_dept_map || {}
    setPersons((prev) =>
      names.map((n) => {
        const old = prev.find((p) => p.name === n)
        return old || { name: n, department: unify201Dept(deptMap[n]), description: '' }
      }),
    )

  }, [sessionData.employee_names, sessionData.employee_dept_map, active])

  const buildPayload = (): PracticalExamPayload => ({ content, training_date: trainingDate, persons, assessor })

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
    registerDocBuilder?.('practical_exam', () => {
      const p = buildPayload()
      const hasContent = p.content || p.assessor || p.persons.length > 0
      return hasContent ? (p as unknown as Record<string, unknown>) : null
    })
  })

  // 生成实操考核结果表文档（页内按钮与顶部"一键导出"共用；无内容返回 null 跳过）
  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    const hasContent = content || assessor || persons.some((p) => p.name && p.name.trim())
    if (!hasContent) return null
    const { bytes, filename } = await generatePracticalExamResult({
      training_content: content,
      training_date: trainingDate,
      persons: persons.filter((p) => p.name.trim()).map((p) => ({ name: p.name, department: p.department, description: p.description || examContent })),
      assessor,
    })
    return [{ name: filename, bytes }]
  }

  useEffect(() => {
    // 一键导出仅当考核方式为"实操"时才包含实操表；页内手动按钮不受此限
    registerExporter?.('practical_exam', async () => (active ? buildExportEntries() : null))
  })

  const handleExport = async () => {
    setExporting(true)
    try {
      const sessionId = await saveSession()
      await upsertTrainingDocument({
        session_id: sessionId,
        doc_type: 'practical_exam',
        title: `实操培训考核结果表_${content || trainingDate}`,
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
          title={`评估表当前考核方式为"${assessmentMethod || '未选择'}"，实操评估表仅在考核方式选择"实操"时自动填写培训信息。`}
        />
      )}
      <Space className="mb-2 doc-toolbar">
        <Upload
          accept=".docx,.doc"
          showUploadList={false}
          beforeUpload={(file) => {
            handleImport(file as unknown as File)
            return false
          }}
        >
          <Button icon={<UploadOutlined />} loading={importing}>导入实操试题</Button>
        </Upload>
        <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
          导出实操考核结果表（每人一页）
        </Button>
      </Space>

      {/* 无受训人员时也显示一张空白页，可手动填姓名/部门 */}
      {(persons.length ? persons : [{ name: '', department: '', description: '' }]).map((p, i) => (
        <div key={i} className="a4-page">
        <div className="doc-bar"><span className="doc-no">APP13-SMP-HR-002-14</span><span>P{i + 1}/{Math.max(1, persons.length)}</span></div>
        <table className="doc-table">
          <colgroup>
            <col style={{ width: '12%' }} />
            <col style={{ width: '21%' }} />
            <col style={{ width: '21%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '11%' }} />
          </colgroup>
          <tbody>
            <tr>
              <td colSpan={7} style={{ textAlign: 'center', fontWeight: 700, fontSize: '16pt', padding: '10px 0', letterSpacing: 2 }}>
                实操培训考核结果表
              </td>
            </tr>
            <tr>
              <td className="doc-lbl">部门</td>
              <td colSpan={2}>{p.department}</td>
              <td className="doc-lbl">姓名</td>
              <td colSpan={3}>{p.name}</td>
            </tr>
            <tr>
              <td className="doc-lbl">培训内容</td>
              <td colSpan={2}>
                <Input value={content} onChange={(e) => setContent(e.target.value)} />
              </td>
              <td className="doc-lbl">培训日期</td>
              <td colSpan={3}>
                <Input value={trainingDate} onChange={(e) => setTrainingDate(e.target.value)} placeholder="YYYY.MM.DD" />
              </td>
            </tr>
            <tr>
              <td colSpan={7} style={{ height: 220, verticalAlign: 'top', padding: 8 }}>
                <Input.TextArea
                  autoSize={{ minRows: 8, maxRows: 16 }}
                  placeholder="实操考核情况描述"
                  value={p.description || examContent}
                  onChange={(e) => setPersons((arr) => arr.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))}
                />
              </td>
            </tr>
            <tr>
              <td colSpan={4} />
              <td colSpan={3}>
                评估人/日期：
                <Input style={{ width: 160 }} value={assessor} onChange={(e) => setAssessor(e.target.value)} />
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      ))}
    </div>
  )
}
