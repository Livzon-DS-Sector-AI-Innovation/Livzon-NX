'use client'

import { useEffect, useState } from 'react'
import { App, Modal, Form, Input, Select, DatePicker, Tabs } from 'antd'
import dayjs from 'dayjs'
const { TabPane } = Tabs
import { Employee, EmployeeCreateInput, EmployeeUpdateInput, Department } from '@/types/hr'
import { createEmployee, updateEmployee } from '@/actions/hr'
import { fetchDepartments } from '@/lib/api/hr'
import { fetchMaxSeqNumber } from '@/lib/api/client/hr'

interface EmployeeFormProps {
  open: boolean
  employee: Employee | null
  onClose: () => void
  onSuccess: () => void
}

export default function EmployeeForm({ open, employee, onClose, onSuccess }: EmployeeFormProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const isEdit = !!employee
  const [departments, setDepartments] = useState<Department[]>([])
  const [selectedDeptName, setSelectedDeptName] = useState<string | undefined>()
  const currentSubDept = Form.useWatch('sub_department', form)

  useEffect(() => {
    if (open) {
      fetchDepartments({ page_size: 100 })
        .then((res) => setDepartments(res.data))
        .catch(() => setDepartments([]))

      if (employee) {
        const dateFields = [
          'hire_date', 'work_start_date', 'factory_entry_date', 'livo_entry_date',
          'contract_start_date', 'contract_end_date',
          'contract_start_2', 'contract_start_3', 'contract_start_4', 'contract_start_5',
          'planned_probation_date', 'probation_effective_date',
        ]
        const values: any = { ...employee }
        dateFields.forEach((f) => {
          const val = employee[f as keyof Employee]
          if (val && typeof val === 'string') {
            values[f] = dayjs(val)
          }
        })
        form.setFieldsValue(values)
        queueMicrotask(() => setSelectedDeptName(values.department))
      } else {
        form.resetFields()
        form.setFieldsValue({ status: '在职' })
        // 新增模式：自动获取下一个序号
        fetchMaxSeqNumber()
          .then((res) => {
            if (res?.data?.next_seq) {
              form.setFieldsValue({ seq_number: res.data.next_seq })
            }
          })
          .catch(() => { /* 获取失败不阻塞 */ })
      }
    }
  }, [open, employee, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const dateFields = [
        'hire_date', 'work_start_date', 'factory_entry_date', 'livo_entry_date',
        'contract_start_date', 'contract_end_date',
        'contract_start_2', 'contract_start_3', 'contract_start_4', 'contract_start_5',
        'planned_probation_date', 'probation_effective_date',
      ]
      const payload: any = { ...values }
      dateFields.forEach((f) => {
        if (values[f]) {
          payload[f] = values[f].format('YYYY-MM-DD')
        }
      })

      // 过滤空字符串：后端 date 类型字段不接受空字符串
      // contract_end_2/3/4、last_working_day 在后端是 date 类型
      const dateTypeStringFields = ['contract_end_2', 'contract_end_3', 'contract_end_4', 'last_working_day']
      dateTypeStringFields.forEach((f) => {
        if (payload[f] === '') {
          delete payload[f]
        }
      })
      // 过滤所有空字符串为 undefined（不传给后端）
      Object.keys(payload).forEach((k) => {
        if (payload[k] === '' || payload[k] === undefined) {
          delete payload[k]
        }
      })

      if (isEdit && employee) {
        const result = await updateEmployee(employee.id, payload as EmployeeUpdateInput)
        const syncStatus = result.meta?.feishu_sync_status
        if (syncStatus === 'success') {
          message.success('员工更新成功，已同步到飞书')
        } else if (syncStatus?.startsWith('failed')) {
          message.warning(`员工更新成功，但飞书同步失败：${syncStatus.replace('failed: ', '')}`)
        } else {
          message.success('员工更新成功')
        }
      } else {
        const result = await createEmployee(payload as EmployeeCreateInput)
        const syncStatus = result.meta?.feishu_sync_status
        if (syncStatus === 'success') {
          message.success('员工创建成功，已同步到飞书')
        } else if (syncStatus?.startsWith('failed')) {
          message.warning(`员工创建成功，但飞书同步失败：${syncStatus.replace('failed: ', '')}`)
        } else {
          message.success('员工创建成功')
        }
      }

      form.resetFields()
      onSuccess()
      onClose()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '操作失败')
    }
  }

  // 找到根节点（总公司），筛选其下的一级部门
  const rootDept = departments.find((d) => !d.parent_id)
  const firstLevelDepts = rootDept
    ? departments.filter((d) => d.parent_id && d.parent_id === rootDept.id)
    : departments.filter((d) => !d.parent_id)
  const departmentOptions = firstLevelDepts.map((d) => ({ value: d.name, label: d.name }))

  // 根据选择的一级部门获取二级部门
  const subDepartmentOptions = departments
    .filter((d) => {
      const parentDept = departments.find((p) => p.name === selectedDeptName)
      return parentDept && d.parent_id === parentDept.id
    })
    .map((d) => ({ value: d.name, label: d.name }))

  // 编辑时：如果当前二级部门值不在子部门选项中，自动加入（避免数据不一致导致选项丢失）
  if (isEdit && currentSubDept && !subDepartmentOptions.find((o) => o.value === currentSubDept)) {
    subDepartmentOptions.unshift({ value: currentSubDept, label: currentSubDept })
  }

  // 当一级部门改变时，清空二级部门并更新选中状态
  const handleDepartmentChange = (value: string) => {
    form.setFieldsValue({ sub_department: undefined })
    setSelectedDeptName(value)
  }

  const commonInput = (name: string, label: string, required?: boolean, rest?: any) => (
    <Form.Item name={name} label={label} rules={required ? [{ required: true, message: `请输入${label}` }] : undefined} {...rest}>
      <Input placeholder={`请输入${label}`} />
    </Form.Item>
  )

  const commonSelect = (name: string, label: string, options: { value: string; label: string }[], required?: boolean, onChange?: (value: string) => void) => (
    <Form.Item name={name} label={label} rules={required ? [{ required: true, message: `请选择${label}` }] : undefined}>
      <Select placeholder={`请选择${label}`} allowClear options={options} onChange={onChange} />
    </Form.Item>
  )

  const dateItem = (name: string, label: string, required?: boolean) => (
    <Form.Item name={name} label={label} rules={required ? [{ required: true, message: `请选择${label}` }] : undefined}>
      <DatePicker className="w-full" placeholder={`请选择${label}`} />
    </Form.Item>
  )

  return (
    <Modal
      title={isEdit ? '编辑员工' : '新增员工'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      okText="保存"
      cancelText="取消"
      width={860}
    >
      <Form form={form} layout="vertical" className="mt-4">
        <Tabs
          defaultActiveKey="basic"
          items={[
            {
              key: 'basic',
              label: '基本信息',
              children: (
                <div className="grid grid-cols-3 gap-4">
                  {commonInput('employee_number', '工号', false)}
                  {commonInput('name', '姓名', true)}
                  {commonInput('archive_number', '档案编号')}
                  {commonInput('domain_account', '域账号')}
                  {commonSelect('department', '一级部门', departmentOptions, true, handleDepartmentChange)}
                  {commonSelect('sub_department', '二级部门', subDepartmentOptions)}
                  {commonInput('position', '职务|岗位', true)}
                  {commonInput('level', '职级')}
                  {commonInput('employment_type', '人员就业方式')}
                  {commonInput('seq_number', '序号')}
                  {commonSelect('gender', '性别', [
                    { value: '男', label: '男' }, { value: '女', label: '女' },
                  ])}
                  {commonSelect('status', '在职状态', [
                    { value: '正式', label: '正式' }, { value: '转正实习生', label: '转正实习生' },
                    { value: '实习生', label: '实习生' }, { value: '试用期', label: '试用期' },
                    { value: '在职', label: '在职' },
                  ], true)}
                  {dateItem('hire_date', '入职日期', true)}
                </div>
              ),
            },
            {
              key: 'personal',
              label: '个人信息',
              children: (
                <div className="grid grid-cols-3 gap-4">
                  {commonInput('native_place', '籍贯')}
                  {commonSelect('ethnic_group', '民族', [
                    '汉族', '蒙古族', '回族', '藏族', '维吾尔族', '苗族', '彝族', '壮族',
                    '布依族', '朝鲜族', '满族', '侗族', '瑶族', '白族', '土家族', '哈尼族',
                    '哈萨克族', '傣族', '黎族', '傈僳族', '佤族', '畲族', '高山族', '拉祜族',
                    '水族', '东乡族', '纳西族', '景颇族', '柯尔克孜族', '土族', '达斡尔族',
                    '仫佬族', '羌族', '布朗族', '撒拉族', '毛南族', '仡佬族', '锡伯族',
                    '阿昌族', '普米族', '塔吉克族', '怒族', '乌孜别克族', '俄罗斯族',
                    '鄂温克族', '德昂族', '保安族', '裕固族', '京族', '塔塔尔族', '独龙族',
                    '鄂伦春族', '赫哲族', '门巴族', '珞巴族', '基诺族',
                  ].map(v => ({ value: v, label: v })))}
                  {commonSelect('political_status', '政治面貌', [
                    { value: '群众', label: '群众' }, { value: '预备党员', label: '预备党员' },
                    { value: '中共党员', label: '中共党员' }, { value: '党员', label: '党员' },
                    { value: '团员', label: '团员' }, { value: '共青团员', label: '共青团员' },
                  ])}
                  {commonSelect('marital_status', '婚姻状况', [
                    { value: '已婚', label: '已婚' }, { value: '离异', label: '离异' },
                    { value: '未婚', label: '未婚' },
                  ])}
                  {commonInput('health_status', '健康情况')}
                  {commonSelect('household_type', '户口类别', [
                    { value: '城镇', label: '城镇' }, { value: '农业', label: '农业' },
                  ])}
                  {commonSelect('status_category', '人员类别', [
                    { value: '职能管理', label: '职能管理' }, { value: '后勤服务', label: '后勤服务' },
                    { value: '生产辅助', label: '生产辅助' }, { value: '生产一线', label: '生产一线' },
                    { value: '技术一线', label: '技术一线' }, { value: '研发一线', label: '研发一线' },
                  ])}
                  {commonInput('id_card', '身份证号')}
                  {commonInput('id_card_expiry', '身份证到期日')}
                </div>
              ),
            },
            {
              key: 'contact',
              label: '联系信息',
              children: (
                <div className="grid grid-cols-2 gap-4">
                  {commonInput('phone', '联系电话')}
                  {commonInput('email', '电子邮箱')}
                  {commonInput('current_address', '现住址')}
                  {commonInput('emergency_contact_name', '紧急联系人')}
                  {commonInput('emergency_contact_phone', '紧急联系人电话')}
                  {commonInput('emergency_contact_relation', '紧急联系人关系')}
                </div>
              ),
            },
            {
              key: 'edu',
              label: '学历职业',
              children: (
                <div className="grid grid-cols-3 gap-4">
                  {commonSelect('education', '学历', [
                    { value: '大专', label: '大专' }, { value: '高中', label: '高中' },
                    { value: '本科', label: '本科' }, { value: '中专/中技', label: '中专/中技' },
                    { value: '高中以下', label: '高中以下' }, { value: '函授本科', label: '函授本科' },
                    { value: '硕士研究生', label: '硕士研究生' }, { value: '中专', label: '中专' },
                  ])}
                  {commonInput('degree', '学位')}
                  {commonInput('school', '毕业院校')}
                  {commonInput('major', '专业')}
                  {commonInput('qualification_type', '职称')}
                  <Form.Item name="qualifications" label="技能证书">
                    <Select mode="multiple" placeholder="请选择技能证书" allowClear showSearch style={{ width: '100%' }} options={[
                      '机动车驾驶证A2D', '高级技术维修电工证', '高压类电工进网作业证', '电工作业证', '机动车驾驶证C1',
                      'G2司炉工热力运行工证', '司炉证（G3', '三级）', '一级锅炉司炉', '一级锅炉司炉证',
                      '市场营销师、会展策划师', '熔化焊接与热切割作业证', '维修电工', '化工高级总控证',
                      '高级钳工证、电工证', '高处作业证、有限空间作业证、焊接与热切割作业', 'CET-4',
                      '化工检修焊工、化工检修钳工、焊工', '电焊工', '焊接与热切割作业证',
                      '高压电工作业证/低压电工作业证', 'G3司炉证', '电焊工证', '电工证',
                      '计算机操作证', '化工与制药助理工', '电工证、高压类电工进网作业证', '金属焊接切割',
                      '电工作业证/高压类电工进网作业证', '高压电工进网作业证/低压电工作业', '化工总控证',
                      'G3三级锅炉司炉证', 'G1一级锅炉司炉证', 'R1固定式压力容器操作证', '内审员',
                      '会计从业\n资格证', '采煤机司机', '化工检修焊工',
                      '高处作业证、有限空间作业证、焊接与热切割作业、化工焊工证', 'III类司炉证',
                      '建构筑物消防员结业证', '上等兵警衔', '电焊工四级', '低压电工作业操作证',
                      '焊接与热切割作业', '矿井维修电工四级', '电子设备装接工、建构筑物消防员资格证',
                      '焊工三级', '化学检验工三级', '微生物发酵工三级', '锅炉作业证G2',
                      '有限空间作业证、焊接与热切割作业', '建构筑物消防员资格证',
                      '压力容器焊工证、高处作业证、有限空间作业证、焊接与热切割作业',
                      '高处作业证、焊接与热切割作业', '人力资源管理师',
                      '焊接与热切割作业证、高处作业证', '制冷与空调作业', '维修电工三级',
                      '计算机绘图师、化工检修钳工、高处作业', '美容师五级', '安全生产管理人员',
                      '数控车床三级、汽车维修工', '化学检验员', '英语六级',
                      '低压电工作业证、电工证', '煤质化验工三级',
                      '高处作业证、焊接与热切割作业、有限空间',
                      '卫生专业技术资格初级、计算机应用基础',
                      '焊接与热切割作业、有限空间、高处作业', '有限空间作业', '初级护理学',
                      '会计初级', '安全生产管理人员、计算机信息高新技术四级',
                      '焊接与热切割作业、高处作业、有限空间作业、焊工',
                      '高压电工、低压电工证、电工证',
                      '化学检验员、危险化学品安全作业、有限空间作业、',
                      '焊接与热切割作业、高处作业、焊工证', '分析工', '钳工、电工',
                      '国际商贸单证员（中级）、办公自动化', '教师资格证', '高处作业证',
                      '焊工证', '化工总控工三级', '初级会计证',
                    ].map(v => ({ value: v, label: v }))} />
                  </Form.Item>
                  {commonInput('certificate_number', '证书编号')}
                  {commonInput('certificate_review_date', '技能证书复审时间')}
                  {dateItem('work_start_date', '参加工作时间')}
                  {dateItem('factory_entry_date', '进本公司时间')}
                  {dateItem('livo_entry_date', '入丽珠时间')}
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
                  {dateItem('contract_start_2', '第二次续签合同日期')}
                  {commonInput('contract_end_2', '合同截止日期（2）')}
                  {dateItem('contract_start_3', '第三次续签合同日期')}
                  {commonInput('contract_end_3', '合同截止日期（3）')}
                  {dateItem('contract_start_4', '第四次续签合同日期')}
                  {commonInput('contract_end_4', '合同截止日期4')}
                  {dateItem('contract_start_5', '第五次续签合同日期')}
                  {commonInput('contract_end_5', '合同截止日期5')}
                  {commonInput('contract_start_6', '第六次续签合同日期')}
                  {commonInput('contract_end_6', '合同截止日期6')}
                </div>
              ),
            },
            {
              key: 'other',
              label: '其他',
              children: (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <Form.Item name="remarks" label="备注">
                      <Select mode="multiple" placeholder="请选择备注" allowClear options={[
                        '福州调入', '2014/4/3由设备部调入', '2014年12月31日离职', '2015年1月12日重新入职',
                        '10化工技师1班', '机械技师', '2014/5/5福兴提炼调入', '2014/4/4由提炼调入',
                        '2014/4/1由提炼调入', '2014/4/9任命', '2014/1/1实习转试用',
                        '2014/5/26新北江提炼调入', '半个月复查肝功能（胆红素)', '2024/3/20回校答辩2024/7/2返岗',
                      ].map(v => ({ value: v, label: v }))} />
                    </Form.Item>
                  </div>
                  <div className="grid grid-cols-2 gap-4 mt-4">
                    {commonSelect('probation_status', '转正状态', [
                      { value: '正常转正', label: '正常转正' }, { value: '提前转正', label: '提前转正' },
                      { value: '延长转正', label: '延长转正' }, { value: '推迟转正', label: '推迟转正' },
                    ])}
                    {dateItem('planned_probation_date', '拟转正日期')}
                    {dateItem('probation_effective_date', '转正生效日期')}
                    {commonInput('last_working_day', '最后工作日')}
                    {commonSelect('offboarding_type', '离职类型', [
                      { value: '正常离职', label: '正常离职' }, { value: '补办手续', label: '补办手续' },
                    ])}
                    {commonSelect('offboarding_reason', '离职原因', [
                      { value: '薪资低', label: '薪资低' }, { value: '与领导关系不融洽', label: '与领导关系不融洽' },
                      { value: '家庭原因', label: '家庭原因' },
                    ])}
                  </div>
                  <div className="mt-4">
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
                  </div>
                </>
              ),
            },
          ]}
        />
      </Form>
    </Modal>
  )
}
