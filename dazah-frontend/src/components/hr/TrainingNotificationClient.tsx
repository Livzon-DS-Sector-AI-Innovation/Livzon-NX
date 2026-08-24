'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import {
  App,
  AutoComplete,
  Button,
  DatePicker,
  Form,
  Input,
  Select,
  Space,
  TimePicker,
} from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { generateTrainingNotification } from '@/actions/hr'
import { fetchTrainingDepartments } from '@/lib/api/client/hr'
import { downloadBytes } from '@/lib/download'
import { unify201Dept, ensureDeptMappings } from './trainingDept'
import type { ExportedDoc, TrainingDocExporter, TrainingSessionData } from '@/types/hr'
import TrainingDocStyle from './trainingDocStyle'

// 培训考核方式：下拉可选，也可手动填写
const ASSESS_METHODS = [
  { value: '笔试' },
  { value: '口试' },
  { value: '实操' },
  { value: '写总结' },
]
interface NotificationProps {
  sessionData?: TrainingSessionData
  registerDocBuilder?: (type: string, fn: () => Record<string, unknown> | null) => void
  /** 注册导出器，供顶部"一键导出"聚合调用 */
  registerExporter?: (type: string, fn: TrainingDocExporter) => void
  draft?: Record<string, unknown> | null
  onSessionChange?: (data: TrainingSessionData) => void
  notifyInitialValues?: Record<string, unknown>
}

export default function TrainingNotificationClient({
  sessionData = {},
  onSessionChange = () => undefined,
  notifyInitialValues = {},
  registerDocBuilder,
  registerExporter,
  draft,
}: NotificationProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [exporting, setExporting] = useState(false)
  const [departments, setDepartments] = useState<{ value: string; label: string }[]>([])

  useEffect(() => {
    ensureDeptMappings().catch(() => {})
    fetchTrainingDepartments()
      .then((depts) => {
        setDepartments(depts.map((d) => ({ value: d, label: d })))
      })
      .catch(() => setDepartments([]))
  }, [])

  // 从共享 session 恢复（首次）
  const [notifyInitialized, setNotifyInitialized] = useState(false)
  useEffect(() => {
    if (notifyInitialized) return
    const keys = Object.keys(notifyInitialValues)
    if (keys.length === 0) return
    form.setFieldsValue({ ...notifyInitialValues })
    setNotifyInitialized(true)
  }, [notifyInitialValues, form, notifyInitialized])

  // 实时同步共享 session（签到表编辑的培训内容/对象/时间/地点自动带入通知）
  useEffect(() => {
    const patch: Record<string, unknown> = {}
    if (sessionData.topic) patch.subject = sessionData.topic
    if (sessionData.trainee_departments?.length) patch.trainee_departments = sessionData.trainee_departments
    if (sessionData.training_time_start && sessionData.training_time_end) {
      patch.training_time = [
        dayjs(sessionData.training_time_start, 'HH:mm'),
        dayjs(sessionData.training_time_end, 'HH:mm'),
      ]
    }
    if (sessionData.location) patch.location = sessionData.location
    if (sessionData.assessment_method) patch.training_method = sessionData.assessment_method
    if (Object.keys(patch).length) form.setFieldsValue(patch)
  }, [sessionData.topic, sessionData.trainee_departments, sessionData.training_time_start, sessionData.training_time_end, sessionData.location, sessionData.assessment_method, form])

  // 落款自动填充：部门=编辑信息的部门（公司级固定人事行政部），日期=填写的培训日期（未填则今天）；手动修改后不再覆盖
  const [userDept, setUserDept] = useState('')
  const lastAutoDeptRef = useRef('')
  const lastAutoDateRef = useRef('')
  useEffect(() => {
    fetch('/api/v1/identity/me', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setUserDept(j?.data?.department || ''))
      .catch(() => {})
  }, [])
  useEffect(() => {
    const patch: Record<string, unknown> = {}
    const curDept = form.getFieldValue('issuer_department') || ''
    // 落款部门默认取共享会话部门（公司级固定人事行政部），手动修改后不再覆盖
    const wantDept = sessionData.department || '人事行政部'
    if (wantDept && (!curDept || curDept === lastAutoDeptRef.current)) {
      lastAutoDeptRef.current = wantDept
      patch.issuer_department = wantDept
    }
    const curDate = form.getFieldValue('issue_date')
    const curDateStr = curDate?.format?.('YYYY-MM-DD') || ''
    const wantDate = sessionData.training_date || dayjs().format('YYYY-MM-DD')
    if (!curDateStr || curDateStr === lastAutoDateRef.current) {
      lastAutoDateRef.current = wantDate
      patch.issue_date = dayjs(wantDate)
    }
    if (Object.keys(patch).length) form.setFieldsValue(patch)
  }, [sessionData.department, sessionData.training_date, userDept, form])

  // 注册草稿序列化函数，供顶部"保存"一键调用（时间区间拆成 start/end）
  useEffect(() => {
    registerDocBuilder?.('notification', () => {
      const v = form.getFieldsValue(true)
      const out: Record<string, unknown> = {}
      for (const [k, val] of Object.entries(v)) {
        if (Array.isArray(val) && val[0] && typeof (val[0] as any).format === 'function') {
          out.training_time_start = (val[0] as any).format('HH:mm')
          out.training_time_end = (val[1] as any).format('HH:mm')
        } else {
          out[k] = val && typeof (val as any).format === 'function' ? (val as any).format('YYYY-MM-DD') : val
        }
      }
      return out
    })
  })

  // 恢复草稿（台账"资料"抽屉打开编辑跳转）
  useEffect(() => {
    if (!draft) return
    const patch: Record<string, unknown> = { ...draft }
    if (draft.training_time_start && draft.training_time_end) {
      patch.training_time = [dayjs(draft.training_time_start as string, 'HH:mm'), dayjs(draft.training_time_end as string, 'HH:mm')]
    }
    delete patch.training_time_start
    delete patch.training_time_end
    for (const k of ['training_date', 'issue_date']) {
      if (typeof patch[k] === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(patch[k] as string)) patch[k] = dayjs(patch[k] as string)
    }
    form.setFieldsValue(patch)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  // ── 导出培训通知：页内按钮与顶部"一键导出"共用同一生成逻辑 ──
  const buildNotificationPayload = () => {
    const v = form.getFieldsValue(true)
    const [t0, t1] = v.training_time || []
    return {
      department: unify201Dept(sessionData.department) || '公司',
      training_date: sessionData.training_date!,
      subject: v.subject || sessionData.topic!,
      training_time_start: t0 ? dayjs(t0).format('HH:mm') : sessionData.training_time_start,
      training_time_end: t1 ? dayjs(t1).format('HH:mm') : sessionData.training_time_end,
      location: v.location || sessionData.location,
      trainer: v.trainer || sessionData.instructor,
      content: v.content || sessionData.content,
      trainee_names: v.trainee_departments?.length ? v.trainee_departments : (sessionData.trainee_departments || []),
      issuer_department: v.issuer_department || sessionData.issuer_department || unify201Dept(sessionData.department),
      issue_date: v.issue_date ? dayjs(v.issue_date).format('YYYY-MM-DD') : (sessionData.issue_date || sessionData.training_date!),
      assessment_method: v.training_method || sessionData.assessment_method,
    }
  }

  const buildExportEntries = async (): Promise<ExportedDoc[] | null> => {
    if (!sessionData.training_date || !sessionData.topic) return null
    const { bytes, filename } = await generateTrainingNotification(buildNotificationPayload())
    return [{ name: filename, bytes }]
  }

  useEffect(() => {
    registerExporter?.('notification', buildExportEntries)
  })

  const handleExport = async () => {
    if (!sessionData.training_date) {
      message.warning('请先在培训签到表选择培训日期')
      return
    }
    if (!sessionData.topic) {
      message.warning('请先关联计划项目或填写培训内容')
      return
    }
    setExporting(true)
    try {
      const entries = await buildExportEntries()
      if (!entries) return
      for (const e of entries) downloadBytes(e.bytes, e.name)
      message.success('培训通知已生成')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '生成失败')
    } finally {
      setExporting(false)
    }
  }

  // 上报共享 session（导出/发送按钮在顶部控制条，依赖这些数据）
  const handleNotifyFormChange = useCallback((_changed: any, allValues: any) => {
    const data: TrainingSessionData = {}
    if (allValues.training_date) data.training_date = allValues.training_date.format('YYYY-MM-DD')
    if (allValues.subject) data.topic = allValues.subject
    if (allValues.content) data.content = allValues.content
    // 六、培训考核 = 考核方式，与评估表共用 session.assessment_method 驱动口试/实操联动
    if (allValues.training_method) data.assessment_method = allValues.training_method
    if (allValues.trainer) data.instructor = allValues.trainer
    if (allValues.location) data.location = allValues.location
    if (allValues.department) data.department = allValues.department
    if (allValues.trainee_departments?.length > 0) data.trainee_departments = allValues.trainee_departments
    if (allValues.employee_names?.length > 0) data.employee_names = allValues.employee_names
    if (allValues.issuer_department) data.issuer_department = allValues.issuer_department
    if (allValues.issue_date) data.issue_date = allValues.issue_date.format('YYYY-MM-DD')
    onSessionChange(data)
  }, [onSessionChange])

  return (
    <Form form={form} layout="vertical" onValuesChange={handleNotifyFormChange}>
      <div className="space-y-4">
        <Space className="mb-2 doc-toolbar">
          <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
            导出培训通知
          </Button>
        </Space>

        {/* 培训通知模板文档（与 Word 模板逐行一致） */}
        <div id="print-area">
          <div className="a4-page doc-area" style={{ background: '#fff', padding: '28px 40px', margin: '0 auto' }}>
            <h2 style={{ textAlign: 'center', fontSize: '16pt', fontWeight: 700, letterSpacing: 8, margin: '0 0 24px' }}>
              培 训 通 知
            </h2>

            {/* 一、培训内容：可编辑框 */}
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14, fontSize: '10.5pt', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>一、培训内容：</span>
              <Form.Item name="subject" noStyle rules={[{ required: true, message: '请填写培训内容' }]}>
                <Input placeholder="填写培训内容" style={{ flex: 1 }} />
              </Form.Item>
            </div>

            {/* 二、培训对象 */}
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14, fontSize: '10.5pt', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>二、培训对象：</span>
              <Form.Item name="trainee_departments" noStyle>
                <Select
                  mode="tags"
                  style={{ width: '50%' }}
                  placeholder="选择或输入受训部门"
                  options={departments.map((d) => ({ value: d.value, label: d.label }))}
                />
              </Form.Item>
              <span style={{ color: '#666' }}>（具体人员名单详见培训签到表）</span>
            </div>

            {/* 三、培训时间 */}
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14, fontSize: '10.5pt', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>三、培训时间：</span>
              <Form.Item name="training_time" noStyle initialValue={[dayjs('08:00', 'HH:mm'), dayjs('12:00', 'HH:mm')]}>
                <TimePicker.RangePicker format="HH:mm" style={{ flex: 1 }} />
              </Form.Item>
            </div>

            {/* 四、培训地点 */}
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14, fontSize: '10.5pt', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>四、培训地点：</span>
              <Form.Item name="location" noStyle>
                <Input placeholder="填写培训地点" style={{ flex: 1 }} />
              </Form.Item>
            </div>

            {/* 五、培训要求 */}
            <div style={{ marginBottom: 14, fontSize: '10.5pt' }}>
              <p style={{ fontWeight: 600, margin: '0 0 4px' }}>五、培训要求：</p>
              <p style={{ margin: '2px 0', textIndent: '2em' }}>1.以上课程属于培训课程的重要内容，要求各员工必须参加；</p>
              <p style={{ margin: '2px 0', textIndent: '2em' }}>2.所有参训人员不得以任何理由拒绝参加培训，无故不参加培训的人员，将根据公司的相关规定给予相应的处罚；</p>
              <p style={{ margin: '2px 0', textIndent: '2em' }}>3.在培训过程中所有参训人员不得迟到、早退、交头接耳、不得大声喧哗，把自己的手机调成静音或关机；</p>
              <p style={{ margin: '2px 0', textIndent: '2em' }}>4.每位参训人员在培训时需要带上笔记本做好培训笔记。</p>
            </div>

            {/* 六、培训考核：下拉可编辑 */}
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 28, fontSize: '10.5pt', gap: 8 }}>
              <span style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>六、培训考核：</span>
              <Form.Item name="training_method" noStyle>
                <AutoComplete
                  placeholder="选择或填写考核方式（笔试/口试/实操/写总结）"
                  options={ASSESS_METHODS}
                  allowClear
                  style={{ flex: 1 }}
                  filterOption={(input, option) => (option?.value ?? '').includes(input)}
                />
              </Form.Item>
            </div>

            {/* 特此通知 */}
            <div style={{ textAlign: 'center', fontSize: '10.5pt', fontWeight: 600, margin: '28px 0' }}>
              特此通知！
            </div>

            {/* 落款：单位 + 日期，均可编辑 */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', fontSize: '10.5pt', gap: 8 }}>
              <Form.Item name="issuer_department" noStyle>
                <Input placeholder="落款单位" style={{ width: 220, textAlign: 'center' }} />
              </Form.Item>
              <Form.Item name="issue_date" noStyle>
                <DatePicker format="YYYY年MM月DD日" placeholder="年  月  日" style={{ width: 180 }} />
              </Form.Item>
            </div>
          </div>
        </div>
      </div>

      <TrainingDocStyle />
      <style jsx global>{`
        @media print {
          body * { visibility: hidden; }
          #print-area, #print-area * { visibility: visible; }
          #print-area { position: absolute; left: 0; top: 0; width: 100%; }
        }
      `}</style>
    </Form>
  )
}
