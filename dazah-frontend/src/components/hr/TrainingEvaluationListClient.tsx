'use client'

import { useEffect, useRef, useState } from 'react'
import {
  App,
  Button, Space, Card, Form, Input, InputNumber,
  DatePicker,
} from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { ExportedDoc, TrainingDocExporter, TrainingSessionData } from '@/types/hr'
import { generateTrainingEvaluation } from '@/actions/hr'
import { downloadBytes } from '@/lib/download'
import TrainingDocStyle from './trainingDocStyle'
import dayjs from 'dayjs'
import InstructorAutoComplete from './InstructorAutoComplete'

const METHOD_OPTIONS = ['面授', '实操', '函授', '远程教育', '其他']
const ASSESS_OPTIONS = ['笔试', '口试', '实操', '写总结']
const EVAL_RESULTS = ['经考核，基本达到培训效果。', '经考核，不能达到预期培训效果。']
const ATTACHMENTS = [
  { name: 'has_notification', label: '1、培训通知（需包含培训内容、时间、地点、培训对象名单、培训方式）' },
  { name: 'has_signin_sheet', label: '2、培训签到表' },
  { name: 'has_textbook', label: '3、培训使用教材（若培训教材非SOP，需作为附件入档）' },
  { name: 'has_exam_paper', label: '4、考核试题、试卷、问卷等' },
  { name: 'has_score_summary', label: '5、考核成绩汇总表、补考成绩汇总表' },
]

// APP4 模板单元格样式（纯黑边框，表头白底保真）
const eB = '1px solid #000'
const eTd: React.CSSProperties = { border: eB, padding: '5px 8px', verticalAlign: 'middle', fontSize: '10.5pt' }
const eTdLabel: React.CSSProperties = { ...eTd, background: '#fff', textAlign: 'center', whiteSpace: 'nowrap', fontWeight: 600 }
/** 放大勾选框样式类（globals.css .cb-big） */
const cbCls = (on: boolean) => `cb-big${on ? ' on' : ''}`

interface EvaluationProps {
  sessionData: TrainingSessionData
  onSessionChange?: (data: Partial<TrainingSessionData>) => void
  registerDocBuilder?: (type: string, fn: () => Record<string, unknown> | null) => void
  /** 注册导出器，供顶部"一键导出"聚合调用 */
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
  initialDraft?: Record<string, unknown> | null
}

export default function TrainingEvaluationListClient({ sessionData, onSessionChange, registerDocBuilder, registerExporter, initialDraft }: EvaluationProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [exporting, setExporting] = useState(false)
  // 用 onValuesChange 维护表单值快照，渲染 □/☑ 勾选状态（兼容性最好）
  const [fv, setFv] = useState<any>({})
  const syncFv = () => setFv(form.getFieldsValue(true))

  const setSingle = (field: string, value: string) => {
    const next = fv[field] === value ? undefined : value
    form.setFieldsValue({ [field]: next })
    syncFv()
    // 考核方式联动：口试→口试评估表，实操→实操评估表
    if (field === 'assessment_method') onSessionChange?.({ assessment_method: next })
  }
  const setBool = (field: string, value: boolean) => {
    form.setFieldsValue({ [field]: fv[field] === value ? undefined : value })
    syncFv()
  }

  // 附件默认"有"、数量 1 + 红框字段默认"—"：仅当字段未被设置（undefined）时填充，不覆盖用户手动修改或草稿恢复
  useEffect(() => {
    const patch: Record<string, unknown> = {}
    ATTACHMENTS.forEach((att) => {
      if (form.getFieldValue(att.name) === undefined) patch[att.name] = true
      if (form.getFieldValue(`${att.name}_qty`) === undefined) patch[`${att.name}_qty`] = '1'
    })
    // 默认填充（与纸质模板填写规范一致）：处理方式类字段为"—"，是否再培训默认 No
    const defaults: Record<string, unknown> = {
      absent_handling: '—',
      need_retraining: false,
      retraining_info: '—',
      fail_handling: '—',
      makeup_fail_handling: '—',
      other_attachment: '—',
    }
    for (const [k, v] of Object.entries(defaults)) {
      if (form.getFieldValue(k) === undefined) patch[k] = v
    }
    if (Object.keys(patch).length) {
      form.setFieldsValue(patch)
      syncFv()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 恢复草稿（台账"资料"抽屉打开编辑跳转 / 上次保存的会话恢复）
  useEffect(() => {
    if (!initialDraft) return
    const patch: Record<string, unknown> = { ...initialDraft }
    for (const k of ['training_date', 'evaluate_date']) {
      if (typeof patch[k] === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(patch[k] as string)) patch[k] = dayjs(patch[k] as string)
    }
    form.setFieldsValue(patch)
    syncFv()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialDraft])

  // 课时/教材自动带入的触发键（仅当时间或培训内容变化时覆盖，允许手动修改）
  const lastTimesRef = useRef('')
  const lastContentRef = useRef('')

  // 实时同步共享 session（签到表编辑的培训日期/内容/方式/授课人/部门/人数自动带入）
  useEffect(() => {
    const patch: Record<string, unknown> = {}
    if (sessionData.training_date) patch.training_date = dayjs(sessionData.training_date)
    if (sessionData.topic) patch.training_content = sessionData.topic
    if (sessionData.training_method) patch.training_method = sessionData.training_method
    if (sessionData.instructor) patch.instructor = sessionData.instructor
    if (sessionData.trainee_departments?.length || sessionData.department) {
      patch.target_dept_person = sessionData.trainee_departments?.join('、') || sessionData.department
    }
    const cnt = (sessionData.employee_names || []).filter((n) => n && n.trim()).length
    if (cnt) patch.expected_count = cnt
    // 考核方式与通知"六、培训考核"共用 session.assessment_method
    if (sessionData.assessment_method) patch.assessment_method = sessionData.assessment_method
    // 课时 = 培训时间自动计算（h），时间变化才覆盖手动值
    const t0 = sessionData.training_time_start
    const t1 = sessionData.training_time_end
    if (t0 && t1) {
      const key = `${t0}-${t1}`
      if (key !== lastTimesRef.current) {
        lastTimesRef.current = key
        const [h0, m0] = t0.split(':').map(Number)
        const [h1, m1] = t1.split(':').map(Number)
        const hrs = Math.round((h1 * 60 + m1 - (h0 * 60 + m0)) / 6) / 10
        if (hrs > 0) patch.duration_hours = hrs
      }
    }
    // 培训教材 = 培训内容（同一来源，内容变化才覆盖手动值）
    if (sessionData.topic && sessionData.topic !== lastContentRef.current) {
      lastContentRef.current = sessionData.topic
      patch.textbook = sessionData.topic
    }
    if (Object.keys(patch).length) {
      form.setFieldsValue(patch)
      syncFv()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionData])

  // ── 表单值序列化（dayjs → 字符串，供草稿保存与导出共用）──
  const serializeForm = (): Record<string, unknown> => {
    const v = form.getFieldsValue(true)
    const out: Record<string, unknown> = {}
    for (const [k, val] of Object.entries(v)) {
      out[k] = val && typeof (val as any).format === 'function' ? (val as any).format('YYYY-MM-DD') : val
    }
    return out
  }

  // 注册草稿序列化函数，供顶部"保存"一键调用（补上此前缺失的 evaluation 草稿）
  useEffect(() => {
    registerDocBuilder?.('evaluation', () => {
      const v = form.getFieldsValue(true)
      const hasContent = v.training_content || v.instructor || v.textbook || v.evaluation_comment
      return hasContent ? serializeForm() : null
    })
  })

  // ── 导出评估表（APP4）：按当前表单内容生成，页内按钮与顶部"一键导出"共用 ──
  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    const v = form.getFieldsValue(true)
    if (!v.training_content) return null
    const { bytes, filename } = await generateTrainingEvaluation({
      subject: v.training_content,
      training_date: v.training_date ? dayjs(v.training_date).format('YYYY-MM-DD') : sessionData.training_date,
      training_time_start: sessionData.training_time_start,
      training_time_end: sessionData.training_time_end,
      duration_hours: v.duration_hours,
      training_method: v.training_method,
      is_exam: false,
      other_method: v.other_method,
      instructor: v.instructor,
      target_dept_person: v.target_dept_person,
      expected_count: v.expected_count,
      actual_count: v.actual_count,
      absent_count: v.absent_count,
      textbook: v.textbook,
      absent_handling: v.absent_handling,
      need_retraining: v.need_retraining,
      retraining_info: v.retraining_info,
      assessment_method: v.assessment_method,
      excellent_count: v.excellent_count,
      good_count: v.good_count,
      pass_count: v.pass_count,
      fail_count: v.fail_count,
      absent_exam_count: v.absent_exam_count,
      fail_handling: v.fail_handling,
      makeup_count: v.makeup_count,
      makeup_pass_count: v.makeup_pass_count,
      makeup_fail_count: v.makeup_fail_count,
      makeup_fail_handling: v.makeup_fail_handling,
      evaluation_result: v.evaluation_result,
      evaluation_comment: v.evaluation_comment,
      evaluator: v.evaluator,
      evaluate_date: v.evaluate_date ? dayjs(v.evaluate_date).format('YYYY-MM-DD') : undefined,
      has_notification: v.has_notification,
      has_signin_sheet: v.has_signin_sheet,
      has_textbook: v.has_textbook,
      has_exam_paper: v.has_exam_paper,
      has_score_summary: v.has_score_summary,
      has_notification_qty: v.has_notification_qty,
      has_signin_sheet_qty: v.has_signin_sheet_qty,
      has_textbook_qty: v.has_textbook_qty,
      has_exam_paper_qty: v.has_exam_paper_qty,
      has_score_summary_qty: v.has_score_summary_qty,
      other_attachment: v.other_attachment,
    })
    return [{ name: filename, bytes }]
  }

  useEffect(() => {
    registerExporter?.('evaluation', buildExportEntries)
  })

  const handleExport = async () => {
    if (!form.getFieldValue('training_content')) {
      message.warning('请先填写培训内容')
      return
    }
    setExporting(true)
    try {
      const entries = await buildExportEntries()
      if (!entries) return
      for (const e of entries) downloadBytes(e.bytes, e.name)
      message.success('培训评估表已生成')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '生成失败')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* 导出按钮置于页面顶部，与其他 Tab（签到表/通知/口试/实操）位置一致 */}
      <Space className="mb-2 doc-toolbar">
        <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
          导出评估表
        </Button>
      </Space>

      <Card size="small" title="培训评估表（APP4-SMP-HR-002-14）">
        <Form form={form} onValuesChange={(_c, all) => setFv(all)}>
          <div className="a4-page doc-area">
          <div className="doc-bar"><span className="doc-no">APP4-SMP-HR-002-14</span><span>P1/1</span></div>
          <div className="doc-title">培训评估表</div>
          <table className="eval-doc doc-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '10.5pt', tableLayout: 'fixed' }}>
            <tbody>
              {/* R0 培训内容 */}
              <tr>
                <td style={eTd} colSpan={7}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, width: '100%' }}>
                    <span style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>培训内容：</span>
                    <Form.Item name="training_content" noStyle rules={[{ required: true, message: '请填写培训内容' }]}>
                      <Input.TextArea rows={1} autoSize style={{ flex: 1, width: '100%' }} placeholder="培训内容" />
                    </Form.Item>
                  </div>
                </td>
              </tr>
              {/* R1 培训日期 | 课时 */}
              <tr>
                <td style={eTdLabel} width="12%">培训日期</td>
                <td style={eTd} colSpan={2}><Form.Item name="training_date" noStyle><DatePicker style={{ width: '100%' }} /></Form.Item></td>
                <td style={eTdLabel} width="10%">课时</td>
                <td style={eTd} colSpan={3}><Form.Item name="duration_hours" noStyle><InputNumber style={{ width: '100%' }} min={0} step={0.5} /></Form.Item></td>
              </tr>
              {/* R2 培训方式(勾选) | 授课人 */}
              <tr>
                <td style={eTdLabel}>培训方式</td>
                <td style={eTd} colSpan={2}>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                    {METHOD_OPTIONS.map((m) => (
                      <span key={m} className={cbCls(fv.training_method === m)} onClick={() => setSingle('training_method', m)}>
                        <i className="cb-box">{fv.training_method === m ? '☑' : '□'}</i>{m}{m === '其他' ? '：' : ''}
                      </span>
                    ))}
                    <Form.Item name="other_method" noStyle><Input style={{ width: 90 }} placeholder="" /></Form.Item>
                    {/* 培训方式注册进表单（勾选为自定义控件，需 Form.Item 才能被 getFieldsValue/onValuesChange 可靠跟踪，供 session 同步） */}
                    <Form.Item name="training_method" noStyle><Input type="hidden" /></Form.Item>
                  </div>
                </td>
                <td style={eTdLabel}>授课人</td>
                <td style={eTd} colSpan={3}><Form.Item name="instructor" noStyle><InstructorAutoComplete placeholder="授课人（拼音/中文选择培训师，可手输）" /></Form.Item></td>
              </tr>
              {/* R3 培训对象 部门/班组/人员 */}
              <tr>
                <td style={eTdLabel} rowSpan={2}>培训对象</td>
                <td style={eTd} colSpan={6}>
                  <Space size={6} style={{ width: '100%' }}>
                    <span style={{ whiteSpace: 'nowrap' }}>部门/班组/人员：</span>
                    <Form.Item name="target_dept_person" noStyle><Input style={{ flex: 1 }} placeholder="部门/班组/人员" /></Form.Item>
                  </Space>
                </td>
              </tr>
              {/* R4 应到/实到/缺席 */}
              <tr>
                <td style={eTd} colSpan={6}>
                  <Space size={6} wrap>
                    <span>应到：</span><Form.Item name="expected_count" noStyle><InputNumber style={{ width: 60 }} min={0} /></Form.Item><span>人，</span>
                    <span>实到：</span><Form.Item name="actual_count" noStyle><InputNumber style={{ width: 60 }} min={0} /></Form.Item><span>人，</span>
                    <span>缺席：</span><Form.Item name="absent_count" noStyle><InputNumber style={{ width: 60 }} min={0} /></Form.Item><span>人。</span>
                  </Space>
                </td>
              </tr>
              {/* R5 培训教材 */}
              <tr>
                <td style={eTdLabel}>培训教材</td>
                <td style={eTd} colSpan={6}><Form.Item name="textbook" noStyle><Input placeholder="培训使用教材" /></Form.Item></td>
              </tr>
              {/* R6 缺席处理 + 再培训(□No □Yes) */}
              <tr>
                <td style={eTd} colSpan={7}>
                  <div className="space-y-1">
                    <Space size={6} style={{ width: '100%' }} align="start">
                      <span style={{ whiteSpace: 'nowrap' }}>缺席人员处理方式：</span>
                      <Form.Item name="absent_handling" noStyle><Input.TextArea rows={1} autoSize style={{ flex: 1 }} /></Form.Item>
                    </Space>
                    <Space size={6}>
                      <span>是否进行再培训：</span>
                      <span className={cbCls(fv.need_retraining === false)} onClick={() => setBool('need_retraining', false)}><i className="cb-box">{fv.need_retraining === false ? '☑' : '□'}</i>No</span>
                      <span className={cbCls(fv.need_retraining === true)} onClick={() => setBool('need_retraining', true)}><i className="cb-box">{fv.need_retraining === true ? '☑' : '□'}</i>Yes</span>
                      <Form.Item name="need_retraining" noStyle><Input type="hidden" /></Form.Item>
                      <span style={{ color: '#999' }}>（若再培训，请填写以下资料）</span>
                    </Space>
                    <Space size={6} style={{ width: '100%' }}>
                      <span style={{ whiteSpace: 'nowrap' }}>再培训（时间、地点、方式等）：</span>
                      <Form.Item name="retraining_info" noStyle><Input style={{ flex: 1 }} /></Form.Item>
                    </Space>
                  </div>
                </td>
              </tr>
              {/* R7 考核方式(勾选) */}
              <tr>
                <td style={eTdLabel} colSpan={2}>考核方式</td>
                <td style={eTd} colSpan={5}>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {ASSESS_OPTIONS.map((m) => (
                      <span key={m} className={cbCls(fv.assessment_method === m)} onClick={() => setSingle('assessment_method', m)}>
                        <i className="cb-box">{fv.assessment_method === m ? '☑' : '□'}</i>{m}
                      </span>
                    ))}
                    {/* 考核方式注册进表单（同样为自定义勾选，需 Form.Item 才能可靠同步） */}
                    <Form.Item name="assessment_method" noStyle><Input type="hidden" /></Form.Item>
                  </div>
                </td>
              </tr>
              {/* R8 考核标准及结果 */}
              <tr>
                <td style={eTdLabel} colSpan={2}>考核标准<br />及结果</td>
                <td style={eTd} colSpan={5}>
                  <Space size={6} wrap>
                    <span>优:</span><Form.Item name="excellent_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人；</span>
                    <span>良好:</span><Form.Item name="good_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人；</span>
                    <span>合格:</span><Form.Item name="pass_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人；</span>
                    <span>不合格:</span><Form.Item name="fail_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人；</span>
                    <span>缺考:</span><Form.Item name="absent_exam_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人。</span>
                  </Space>
                </td>
              </tr>
              {/* R9 缺考及不合格处理 */}
              <tr>
                <td style={eTdLabel} colSpan={2}>缺考及不合格人员处理方式</td>
                <td style={eTd} colSpan={5}><Form.Item name="fail_handling" noStyle><Input.TextArea rows={1} autoSize /></Form.Item></td>
              </tr>
              {/* R10 补考结果 */}
              <tr>
                <td style={eTdLabel} colSpan={2}>补考结果</td>
                <td style={eTd} colSpan={5}>
                  <Space size={6} wrap>
                    <span>补考:</span><Form.Item name="makeup_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人；</span>
                    <span>合格:</span><Form.Item name="makeup_pass_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人；</span>
                    <span>不合格:</span><Form.Item name="makeup_fail_count" noStyle><InputNumber style={{ width: 55 }} min={0} /></Form.Item><span>人。</span>
                  </Space>
                </td>
              </tr>
              {/* R11 缺考及补考不合格处理 */}
              <tr>
                <td style={eTdLabel} colSpan={2}>缺考及补考不合格人员处理方式</td>
                <td style={eTd} colSpan={5}><Form.Item name="makeup_fail_handling" noStyle><Input.TextArea rows={1} autoSize /></Form.Item></td>
              </tr>
              {/* R12 培训效果评估及其他(两行勾选) */}
              <tr>
                <td style={eTd} colSpan={7}>
                  <div className="space-y-1">
                    <p style={{ margin: 0, fontWeight: 600 }}>培训效果评估及其他：</p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {EVAL_RESULTS.map((r) => (
                        <span key={r} className={cbCls(fv.evaluation_result === r)} onClick={() => setSingle('evaluation_result', r)}>
                          <i className="cb-box">{fv.evaluation_result === r ? '☑' : '□'}</i>{r}
                        </span>
                      ))}
                      <Form.Item name="evaluation_result" noStyle><Input type="hidden" /></Form.Item>
                    </div>
                    <Form.Item name="evaluation_comment" noStyle><Input.TextArea rows={2} placeholder="培训效果评估及其他" /></Form.Item>
                    <Space size={6}>
                      <span>培训评估人：</span><Form.Item name="evaluator" noStyle><Input style={{ width: 120 }} /></Form.Item>
                      <span>日期：</span><Form.Item name="evaluate_date" noStyle><DatePicker style={{ width: 130 }} /></Form.Item>
                    </Space>
                  </div>
                </td>
              </tr>
              {/* R13 附件表头 */}
              <tr>
                <td style={eTdLabel} colSpan={5}>附件：</td>
                <td style={{ ...eTdLabel, textAlign: 'center' }}>有 无</td>
                <td style={{ ...eTdLabel, textAlign: 'center' }}>数量</td>
              </tr>
              {/* R14-R18 附件清单（有无=勾选，数量=填空） */}
              {ATTACHMENTS.map((att) => (
                <tr key={att.name}>
                  <td style={eTd} colSpan={5}>{att.label}</td>
                  <td style={{ ...eTd, textAlign: 'center' }}>
                    <span className={cbCls(fv[att.name] === true)} onClick={() => setBool(att.name, true)} title="有">
                      <i className="cb-box">{fv[att.name] === true ? '☑' : '□'}</i>有
                    </span>
                    <span className={cbCls(fv[att.name] === false)} onClick={() => setBool(att.name, false)} title="无">
                      <i className="cb-box">{fv[att.name] === false ? '☑' : '□'}</i>无
                    </span>
                    <Form.Item name={att.name} noStyle><Input type="hidden" /></Form.Item>
                  </td>
                  <td style={eTd}><Form.Item name={`${att.name}_qty`} noStyle><Input placeholder="" /></Form.Item></td>
                </tr>
              ))}
              {/* R19 其他 */}
              <tr>
                <td style={eTd} colSpan={7}>
                  <Space size={6} style={{ width: '100%' }}>
                    <span style={{ whiteSpace: 'nowrap' }}>其他：</span>
                    <Form.Item name="other_attachment" noStyle><Input style={{ flex: 1 }} placeholder="其他附件说明" /></Form.Item>
                  </Space>
                </td>
              </tr>
            </tbody>
          </table>
          </div>
        </Form>
      </Card>

      <TrainingDocStyle />
      <style jsx global>{`
        .eval-doc .ant-input, .eval-doc .ant-input-affix-wrapper, .eval-doc .ant-picker,
        .eval-doc .ant-select .ant-select-selector, .eval-doc .ant-input-number,
        .eval-doc .ant-input-number-input, .eval-doc textarea.ant-input {
          border: none !important; box-shadow: none !important; background: transparent !important; border-radius: 0 !important;
        }
        .eval-doc .ant-input:not(textarea),
        .eval-doc .ant-picker-input > input,
        .eval-doc .ant-input-number-input,
        .eval-doc .ant-select-selector {
          border-bottom: 1px solid #000 !important;
        }
      `}</style>
    </div>
  )
}
