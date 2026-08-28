'use client'

import { useEffect, useState } from 'react'
import { App, Modal, Form, Select, DatePicker, Input, Tabs } from 'antd'
import dayjs from 'dayjs'
import { Employee, OffboardingRecord, OffboardingRecordCreateInput, OffboardingRecordUpdateInput } from '@/types/hr'
import { createOffboardingRecord, updateOffboardingRecord } from '@/actions/hr'
import { fetchEmployees } from '@/lib/api/hr'

interface OffboardingFormProps {
  open: boolean
  record: OffboardingRecord | null
  onClose: () => void
  onSuccess: () => void
}

const DATE_FIELDS = [
  'offboarding_date', 'hire_date', 'work_start_date', 'factory_entry_date',
  'livo_entry_date', 'graduation_date', 'probation_effective_date',
  'certificate_review_date', 'contract_start_date', 'contract_end_date',
  'contract_start_2',
]

export default function OffboardingForm({ open, record, onClose, onSuccess }: OffboardingFormProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const isEdit = !!record
  const [employees, setEmployees] = useState<Employee[]>([])

  useEffect(() => {
    if (open) {
      fetchEmployees({ status: '在职', page_size: 100 })
        .then((res) => setEmployees(res.data))
        .catch(() => setEmployees([]))

      if (record) {
        const values: Record<string, unknown> = { ...record }
        DATE_FIELDS.forEach((f) => {
          const val = (record as unknown as Record<string, unknown>)[f]
          if (val && typeof val === 'string') {
            values[f] = dayjs(val)
          }
        })
        form.setFieldsValue(values)
      } else {
        form.resetFields()
        form.setFieldsValue({ offboarding_type: '辞职', handover_status: '待交接' })
      }
    }
  }, [open, record, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const payload: Record<string, unknown> = { ...values }
      DATE_FIELDS.forEach((f) => {
        if (values[f]) {
          payload[f] = values[f].format('YYYY-MM-DD')
        }
      })
      // 数字字段：转换为整数
      const numberFields = ['birth_year', 'birth_month', 'birth_day', 'age', 'seq_number']
      numberFields.forEach((f) => {
        if (values[f] !== undefined && values[f] !== null && values[f] !== '') {
          payload[f] = Number(values[f])
        } else {
          payload[f] = null
        }
      })

      if (isEdit && record) {
        await updateOffboardingRecord(record.id, payload as OffboardingRecordUpdateInput)
        message.success('离职记录更新成功')
      } else {
        await createOffboardingRecord(payload as OffboardingRecordCreateInput)
        message.success('离职记录创建成功')
      }

      form.resetFields()
      onSuccess()
      onClose()
    } catch (err) {
      if ((typeof err === 'object' && err !== null && 'errorFields' in err)) return
      message.error((err instanceof Error ? err.message : '') || '操作失败')
    }
  }

  const handleEmployeeChange = (employeeId: string) => {
    const emp = employees.find((e) => e.id === employeeId)
    if (!emp) return
    const mapped: Record<string, unknown> = {
      employee_number: emp.employee_number,
      name: emp.name,
      domain_account: emp.domain_account,
      gender: emp.gender,
      ethnic_group: emp.ethnic_group,
      native_place: emp.native_place,
      political_status: emp.political_status,
      marital_status: emp.marital_status,
      health_status: emp.health_status,
      household_type: emp.household_type,
      status_category: emp.status_category,
      birth_year: emp.birth_year,
      birth_month: emp.birth_month,
      age: emp.age,
      department: emp.department,
      sub_department: emp.sub_department,
      position: emp.position,
      level: emp.level,
      employment_type: emp.employment_type,
      probation_status: emp.probation_status,
      id_card: emp.id_card,
      id_card_expiry: emp.id_card_expiry,
      current_address: emp.current_address,
      phone: emp.phone,
      email: emp.email,
      emergency_contact_name: emp.emergency_contact_name,
      emergency_contact_phone: emp.emergency_contact_phone,
      emergency_contact_relation: emp.emergency_contact_relation,
      education: emp.education,
      degree: emp.degree,
      major: emp.major,
      school: emp.school,
      qualification_type: emp.qualification_type,
      certificate_number: emp.certificate_number,
      work_years: emp.work_years,
      archive_number: emp.archive_number,
      work_experience_1: emp.work_experience_1,
      work_experience_2: emp.work_experience_2,
      work_experience_3: emp.work_experience_3,
      work_experience_4: emp.work_experience_4,
      contract_end_2: emp.contract_end_2,
      contract_end_3: emp.contract_end_3,
      contract_end_4: emp.contract_end_4,
      contract_end_5: emp.contract_end_5,
      contract_start_3: emp.contract_start_3,
      contract_start_4: emp.contract_start_4,
      contract_start_5: emp.contract_start_5,
      contract_start_6: emp.contract_start_6,
    }
    // 日期字段：转为 dayjs
    const dateFieldMap: Record<string, string> = {
      probation_effective_date: 'probation_effective_date',
      hire_date: 'hire_date',
      work_start_date: 'work_start_date',
      factory_entry_date: 'factory_entry_date',
      livo_entry_date: 'livo_entry_date',
      graduation_date: 'graduation_date',
      certificate_review_date: 'certificate_review_date',
      contract_start_date: 'contract_start_date',
      contract_end_date: 'contract_end_date',
      contract_start_2: 'contract_start_2',
    }
    for (const [empField, formField] of Object.entries(dateFieldMap)) {
      const val = (emp as unknown as Record<string, unknown>)[empField]
      if (typeof val === 'string' || typeof val === 'number' || val instanceof Date) {
        mapped[formField] = dayjs(val)
      }
    }
    form.setFieldsValue(mapped)
  }

  const employeeOptions = employees.map((e) => ({
    value: e.id,
    label: `${e.name} (${e.employee_number})`,
  }))

  const commonInput = (name: string, label: string, required?: boolean) => (
    <Form.Item name={name} label={label} rules={required ? [{ required: true, message: `请输入${label}` }] : undefined}>
      <Input placeholder={`请输入${label}`} />
    </Form.Item>
  )

  const dateItem = (name: string, label: string, required?: boolean) => (
    <Form.Item name={name} label={label} rules={required ? [{ required: true, message: `请选择${label}` }] : undefined}>
      <DatePicker className="w-full" placeholder={`请选择${label}`} />
    </Form.Item>
  )

  return (
    <Modal
      title={isEdit ? '编辑离职记录' : '新增离职记录'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      width={860}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" className="mt-4">
        <Tabs
          defaultActiveKey="offboarding"
          items={[
            {
              key: 'offboarding',
              label: '离职信息',
              children: (
                <>
                  <Form.Item
                    name="employee_id"
                    label="关联员工"
                    rules={[{ required: true, message: '请选择员工' }]}
                  >
                    <Select
                      placeholder="请选择员工"
                      options={employeeOptions}
                      showSearch
                      disabled={isEdit}
                      onChange={handleEmployeeChange}
                      filterOption={(input, option) =>
                        (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>
                  <div className="grid grid-cols-3 gap-4">
                    {commonInput('employee_number', '工号')}
                    {commonInput('name', '姓名')}
                    {commonInput('domain_account', '域账号')}
                    {dateItem('offboarding_date', '最后工作日', true)}
                    <Form.Item name="offboarding_type" label="离职类型" rules={[{ required: true }]}>
                      <Select options={[
                        { value: '辞职', label: '辞职' },
                        { value: '正常离职', label: '正常离职' },
                        { value: '补办手续', label: '补办手续' },
                        { value: '辞退', label: '辞退' },
                        { value: '合同到期', label: '合同到期' },
                        { value: '退休', label: '退休' },
                        { value: '其他', label: '其他' },
                      ]} />
                    </Form.Item>
                    <Form.Item name="handover_status" label="交接状态" rules={[{ required: true }]}>
                      <Select options={[
                        { value: '待交接', label: '待交接' },
                        { value: '交接中', label: '交接中' },
                        { value: '已完成', label: '已完成' },
                      ]} />
                    </Form.Item>
                  </div>
                  <Form.Item name="reason" label="离职原因">
                    <Input.TextArea rows={2} placeholder="请输入离职原因" />
                  </Form.Item>
                  <Form.Item name="notes" label="备注">
                    <Input.TextArea rows={2} placeholder="请输入备注" />
                  </Form.Item>
                </>
              ),
            },
            {
              key: 'basic',
              label: '基本信息',
              children: (
                <div className="grid grid-cols-3 gap-4">
                  {commonInput('gender', '性别')}
                  {commonInput('ethnic_group', '民族')}
                  {commonInput('native_place', '籍贯')}
                  {commonInput('political_status', '政治面貌')}
                  {commonInput('marital_status', '婚姻状况')}
                  {commonInput('health_status', '健康状况')}
                  {commonInput('household_type', '户口类别')}
                  {commonInput('status_category', '人员类别')}
                  <Form.Item name="birth_year" label="出生年份">
                    <Input type="number" placeholder="如: 1990" />
                  </Form.Item>
                  <Form.Item name="birth_month" label="出生月份">
                    <Input type="number" placeholder="如: 5" />
                  </Form.Item>
                  <Form.Item name="age" label="年龄">
                    <Input type="number" placeholder="如: 30" />
                  </Form.Item>
                </div>
              ),
            },
            {
              key: 'org',
              label: '组织信息',
              children: (
                <div className="grid grid-cols-3 gap-4">
                  {commonInput('department', '一级部门')}
                  {commonInput('sub_department', '二级部门')}
                  {commonInput('position', '职位/岗位')}
                  {commonInput('level', '职级')}
                  {commonInput('employment_type', '人员就业方式')}
                  {commonInput('probation_status', '转正状态')}
                  {dateItem('probation_effective_date', '转正生效日期')}
                  {dateItem('hire_date', '入职日期')}
                  {dateItem('work_start_date', '参加工作时间')}
                  {dateItem('factory_entry_date', '进本公司时间')}
                  {dateItem('livo_entry_date', '入丽珠时间')}
                  {commonInput('work_years', '工龄')}
                </div>
              ),
            },
            {
              key: 'contact',
              label: '证件联系',
              children: (
                <div className="grid grid-cols-2 gap-4">
                  {commonInput('id_card', '身份证号')}
                  {commonInput('id_card_expiry', '身份证有效期')}
                  {commonInput('current_address', '现居住地址')}
                  {commonInput('phone', '联系电话')}
                  {commonInput('email', '电子邮箱')}
                  {commonInput('emergency_contact_name', '紧急联系人')}
                  {commonInput('emergency_contact_phone', '紧急联系人电话')}
                  {commonInput('emergency_contact_relation', '与本人关系')}
                </div>
              ),
            },
            {
              key: 'edu',
              label: '学历资质',
              children: (
                <div className="grid grid-cols-3 gap-4">
                  {commonInput('education', '学历')}
                  {commonInput('degree', '学位')}
                  {commonInput('major', '专业')}
                  {commonInput('school', '毕业院校')}
                  {dateItem('graduation_date', '毕业时间')}
                  {commonInput('qualification_type', '职称')}
                  {commonInput('certificate_number', '证书编号')}
                  {dateItem('certificate_review_date', '证书复审时间')}
                </div>
              ),
            },
            {
              key: 'contract',
              label: '合同信息',
              children: (
                <div className="grid grid-cols-2 gap-4">
                  {dateItem('contract_start_date', '首次签订合同日期')}
                  {dateItem('contract_end_date', '首次签订合同截止日期')}
                  {commonInput('contract_end_2', '合同截止日期2')}
                  {commonInput('contract_end_3', '合同截止日期3')}
                  {commonInput('contract_end_4', '合同截止日期4')}
                  {commonInput('contract_end_5', '合同截止日期5')}
                  {dateItem('contract_start_2', '第二次续签合同日期')}
                  {commonInput('contract_start_3', '第三次续签合同日期')}
                  {commonInput('contract_start_4', '第四次续签合同日期')}
                  {commonInput('contract_start_5', '第五次续签合同日期')}
                  {commonInput('contract_start_6', '第六次续签合同日期')}
                </div>
              ),
            },
            {
              key: 'other',
              label: '工作经历/其他',
              children: (
                <>
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    {commonInput('archive_number', '档案编号')}
                    {commonInput('seq_number', '序号')}
                  </div>
                  <Form.Item name="work_experience_1" label="工作经验一">
                    <Input.TextArea rows={2} placeholder="请输入工作经验" />
                  </Form.Item>
                  <Form.Item name="work_experience_2" label="工作经验二">
                    <Input.TextArea rows={2} placeholder="请输入工作经验" />
                  </Form.Item>
                  <Form.Item name="work_experience_3" label="工作经验三">
                    <Input.TextArea rows={2} placeholder="请输入工作经验" />
                  </Form.Item>
                  <Form.Item name="work_experience_4" label="工作经验四">
                    <Input.TextArea rows={2} placeholder="请输入工作经验" />
                  </Form.Item>
                </>
              ),
            },
          ]}
        />
      </Form>
    </Modal>
  )
}
