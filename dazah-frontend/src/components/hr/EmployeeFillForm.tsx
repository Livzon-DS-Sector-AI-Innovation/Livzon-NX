'use client'

import { useState, useEffect } from 'react'
import { App, Form, Input, Select, DatePicker, Button, Collapse, AutoComplete, Result, Spin } from 'antd'
import dayjs from 'dayjs'
import { fetchOnboardingNames } from '@/lib/api/client/hr'
import { createEmployeePublicAction } from '@/actions/hr'

const { TextArea } = Input

const DEPARTMENT_OPTIONS = [
  '总经办', '财务部', '安全部', '质量管理部', '生产管理部',
  '201车间', '103车间', '设备管理部', '行政管理部', '人力资源部',
  '研发部', '采购部', '仓储部', '销售部',
].map(d => ({ value: d, label: d }))

const GENDER_OPTIONS = [
  { value: '男', label: '男' },
  { value: '女', label: '女' },
]

const ETHNIC_OPTIONS = ['汉族', '回族', '蒙古族', '壮族', '藏族', '满族', '白族', '土族', '瑶族'].map(e => ({ value: e, label: e }))

const POLITICAL_OPTIONS = ['群众', '预备党员', '中共党员', '党员', '团员', '共青团员'].map(p => ({ value: p, label: p }))

const MARITAL_OPTIONS = ['已婚', '离异', '未婚'].map(m => ({ value: m, label: m }))

const HOUSEHOLD_OPTIONS = ['城镇', '农业'].map(h => ({ value: h, label: h }))

const STATUS_CATEGORY_OPTIONS = ['职能管理', '后勤服务', '生产辅助', '生产一线', '技术一线', '研发一线'].map(s => ({ value: s, label: s }))

const EDUCATION_OPTIONS = ['大专', '高中', '本科', '中专', '中技', '高中以下', '函授本科', '硕士研究生'].map(e => ({ value: e, label: e }))

const CLASSIFICATION_OPTIONS = ['全日制', '非全日制'].map(c => ({ value: c, label: c }))

const JOB_CATEGORY_OPTIONS = ['管理', '技术', '操作', '职能'].map(j => ({ value: j, label: j }))

export default function EmployeeFillForm() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [nameOptions, setNameOptions] = useState<{ value: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [initLoading, setInitLoading] = useState(true)

  useEffect(() => {
    fetchOnboardingNames()
      .then(names => setNameOptions(names.map(n => ({ value: n }))))
      .catch(() => { /* 静默失败，仍可手动输入 */ })
      .finally(() => setInitLoading(false))
  }, [])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      // 格式化日期字段
      const dateFields = ['hire_date', 'work_start_date', 'certificate_review_date']
      const formatted: Record<string, any> = { ...values }
      for (const key of dateFields) {
        if (formatted[key] && dayjs.isDayjs(formatted[key])) {
          formatted[key] = formatted[key].format('YYYY-MM-DD')
        }
      }
      // 移除空值
      Object.keys(formatted).forEach(k => {
        if (formatted[k] === undefined || formatted[k] === '') delete formatted[k]
      })
      const result = await createEmployeePublicAction(formatted)
      message.success(result.message || '提交成功')
      setSubmitted(true)
    } catch (err) {
      if ((typeof err === 'object' && err !== null && 'errorFields' in err)) return // 表单校验失败，不提示
      message.error((err instanceof Error ? err.message : '') || '提交失败')
    } finally {
      setLoading(false)
    }
  }

  if (initLoading) {
    return (
      <div className="flex justify-center items-center" style={{ minHeight: '100vh' }}>
        <Spin size="large" description="加载中..." />
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="flex justify-center items-center" style={{ minHeight: '100vh', background: '#f5f5f5' }}>
        <Result
          status="success"
          title="提交成功"
          subTitle="您的员工档案信息已提交，请等待 HR 审核。"
          extra={[
            <Button key="back" type="primary" onClick={() => { setSubmitted(false); form.resetFields() }}>
              再填一份
            </Button>,
          ]}
        />
      </div>
    )
  }

  const collapseItems = [
    {
      key: 'basic',
      label: '基本信息（必填）',
      children: (
        <div className="space-y-3">
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <AutoComplete options={nameOptions} filterOption={(input, option) =>
              (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
            } placeholder="选择或输入姓名" />
          </Form.Item>
          <Form.Item name="department" label="部门" rules={[{ required: true, message: '请选择部门' }]}>
            <Select options={DEPARTMENT_OPTIONS} showSearch allowClear placeholder="选择部门" />
          </Form.Item>
          <Form.Item name="position" label="职位" rules={[{ required: true, message: '请输入职位' }]}>
            <Input placeholder="请输入职位" />
          </Form.Item>
          <Form.Item name="hire_date" label="入职日期" rules={[{ required: true, message: '请选择入职日期' }]}>
            <DatePicker style={{ width: '100%' }} placeholder="选择日期" />
          </Form.Item>
          <Form.Item name="sub_department" label="二级部门">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item name="team" label="班组">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item name="job_category" label="职类">
            <Select options={JOB_CATEGORY_OPTIONS} allowClear placeholder="选填" />
          </Form.Item>
          <Form.Item name="level" label="级别">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item name="employment_type" label="人员就业方式">
            <Input placeholder="选填" />
          </Form.Item>
          <Form.Item name="gender" label="性别">
            <Select options={GENDER_OPTIONS} allowClear placeholder="选填" />
          </Form.Item>
        </div>
      ),
    },
    {
      key: 'personal',
      label: '个人信息',
      children: (
        <div className="space-y-3">
          <Form.Item name="native_place" label="籍贯"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="ethnic_group" label="民族"><Select options={ETHNIC_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <Form.Item name="political_status" label="政治面貌"><Select options={POLITICAL_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <Form.Item name="marital_status" label="婚姻状况"><Select options={MARITAL_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <Form.Item name="health_status" label="健康状况"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="household_type" label="户口类别"><Select options={HOUSEHOLD_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <Form.Item name="status_category" label="人员类别"><Select options={STATUS_CATEGORY_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <div className="flex gap-2">
            <Form.Item name="birth_year" label="出生年" className="flex-1"><Input type="number" placeholder="如1990" /></Form.Item>
            <Form.Item name="birth_month" label="月" className="flex-1"><Input type="number" placeholder="1-12" /></Form.Item>
            <Form.Item name="birth_day" label="日" className="flex-1"><Input type="number" placeholder="1-31" /></Form.Item>
          </div>
          <Form.Item name="id_card" label="身份证号"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="id_card_expiry" label="身份证到期日"><Input placeholder="选填" /></Form.Item>
        </div>
      ),
    },
    {
      key: 'contact',
      label: '联系信息',
      children: (
        <div className="space-y-3">
          <Form.Item name="phone" label="手机"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="email" label="邮箱"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="id_card_address" label="身份证地址"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="current_address" label="现住址"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="emergency_contact_name" label="紧急联系人"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="emergency_contact_phone" label="紧急联系人电话"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="emergency_contact_relation" label="紧急联系人关系"><Input placeholder="选填" /></Form.Item>
        </div>
      ),
    },
    {
      key: 'edu',
      label: '学历职业',
      children: (
        <div className="space-y-3">
          <Form.Item name="education" label="学历"><Select options={EDUCATION_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <Form.Item name="degree" label="学位"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="classification" label="分类"><Select options={CLASSIFICATION_OPTIONS} allowClear placeholder="选填" /></Form.Item>
          <Form.Item name="school" label="毕业学校"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="major" label="专业"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="qualification_type" label="职称"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="certificate_number" label="证书编号"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="certificate_review_date" label="技能证书复审时间"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="work_start_date" label="参加工作时间"><DatePicker style={{ width: '100%' }} placeholder="选填" /></Form.Item>
        </div>
      ),
    },
    {
      key: 'other',
      label: '其他',
      children: (
        <div className="space-y-3">
          <Form.Item name="bank_account" label="银行卡号"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="training_id" label="培训档案编号"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="archive_number" label="档案编号"><Input placeholder="选填" /></Form.Item>
          <Form.Item name="work_experience_1" label="工作经验一"><TextArea rows={2} placeholder="选填" /></Form.Item>
          <Form.Item name="work_experience_2" label="工作经验二"><TextArea rows={2} placeholder="选填" /></Form.Item>
          <Form.Item name="work_experience_3" label="工作经验三"><TextArea rows={2} placeholder="选填" /></Form.Item>
          <Form.Item name="work_experience_4" label="工作经验四"><TextArea rows={2} placeholder="选填" /></Form.Item>
        </div>
      ),
    },
  ]

  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5', padding: '12px' }}>
      <div style={{ maxWidth: 480, margin: '0 auto', background: '#fff', borderRadius: 8, padding: '16px' }}>
        <h2 className="text-center text-lg font-semibold mb-1">员工档案信息填写</h2>
        <p className="text-center text-xs text-gray-400 mb-4">请如实填写以下信息，提交后将自动录入员工档案</p>

        <Form form={form} layout="vertical" requiredMark>
          <Collapse
            defaultActiveKey={['basic']}
            items={collapseItems}
            size="small"
            className="mb-4"
          />

          <Button
            type="primary"
            block
            size="large"
            loading={loading}
            onClick={handleSubmit}
          >
            提交
          </Button>
        </Form>
      </div>
    </div>
  )
}
