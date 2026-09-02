'use client'

import { Drawer, Descriptions, Divider, Tag, Button, Space } from 'antd'
import { LinkOutlined, SwapOutlined, EditOutlined, FileTextOutlined } from '@ant-design/icons'
import Link from 'next/link'
import { Employee } from '@/types/hr'
import { maskIdCard, maskMiddle, maskPhone } from '@/lib/mask'

interface EmployeeDetailDrawerProps {
  open: boolean
  employee: Employee | null
  onClose: () => void
  onEdit?: (employee: Employee) => void
}

export default function EmployeeDetailDrawer({ open, employee, onClose, onEdit }: EmployeeDetailDrawerProps) {
  if (!employee) return null

  return (
    <Drawer
      title={`员工详情 - ${employee.name}`}
      placement="right"
      size={720}
      open={open}
      onClose={onClose}
      extra={
        <Space>
          {onEdit && (
            <Button type="primary" size="small" icon={<EditOutlined />} onClick={() => onEdit(employee)}>
              编辑
            </Button>
          )}
          <Link href={`/hr/offboarding?employee_id=${employee.id}`}>
            <Button size="small" icon={<LinkOutlined />}>查看离职记录</Button>
          </Link>
          <Link href={`/hr/position-transfer?employee_id=${employee.id}`}>
            <Button size="small" icon={<SwapOutlined />}>查看调动记录</Button>
          </Link>
        </Space>
      }
    >
      <Descriptions title="基本信息" bordered column={2} size="small">
        <Descriptions.Item label="工号">{employee.employee_number}</Descriptions.Item>
        <Descriptions.Item label="姓名">{employee.name}</Descriptions.Item>
        <Descriptions.Item label="域账户">{employee.domain_account || '-'}</Descriptions.Item>
        <Descriptions.Item label="性别">{employee.gender || '-'}</Descriptions.Item>
        <Descriptions.Item label="民族">{employee.ethnic_group || '-'}</Descriptions.Item>
        <Descriptions.Item label="出生年月">
          {employee.birth_year && employee.birth_month
            ? `${employee.birth_year}年${employee.birth_month}月`
            : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="年龄">{employee.age ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="籍贯">{employee.native_place || '-'}</Descriptions.Item>
        <Descriptions.Item label="政治面貌">{employee.political_status || '-'}</Descriptions.Item>
        <Descriptions.Item label="婚姻状况">{employee.marital_status || '-'}</Descriptions.Item>
        <Descriptions.Item label="健康状况">{employee.health_status || '-'}</Descriptions.Item>
        <Descriptions.Item label="户口类别">{employee.household_type || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="证件信息" bordered column={2} size="small">
        <Descriptions.Item label="身份证号">{maskIdCard(employee.id_card)}</Descriptions.Item>
        <Descriptions.Item label="身份证有效期">{employee.id_card_expiry || '-'}</Descriptions.Item>
        <Descriptions.Item label="现居住地址" span={2}>{maskMiddle(employee.current_address, 8, 4)}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="组织信息" bordered column={2} size="small">
        <Descriptions.Item label="一级部门">{employee.department}</Descriptions.Item>
        <Descriptions.Item label="二级部门">{employee.sub_department || '-'}</Descriptions.Item>
        <Descriptions.Item label="职位/岗位">{employee.position}</Descriptions.Item>
        <Descriptions.Item label="职级">{employee.level || '-'}</Descriptions.Item>
        <Descriptions.Item label="人员类别">{employee.status_category || '-'}</Descriptions.Item>
        <Descriptions.Item label="人员就业方式">{employee.employment_type || '-'}</Descriptions.Item>
        <Descriptions.Item label="在职状态">
          <Tag color={employee.status === '在职' ? 'success' : employee.status === '试用期' ? 'warning' : 'default'}>
            {employee.status}
          </Tag>
        </Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="转正信息" bordered column={2} size="small">
        <Descriptions.Item label="转正状态">{employee.probation_status || '-'}</Descriptions.Item>
        <Descriptions.Item label="拟转正日期">{employee.planned_probation_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="转正生效日期">{employee.probation_effective_date || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="职业生涯" bordered column={2} size="small">
        <Descriptions.Item label="入职日期">{employee.hire_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="参加工作时间">{employee.work_start_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="进本公司时间">{employee.factory_entry_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="入丽珠时间">{employee.livo_entry_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="工龄">{employee.work_years ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="最后工作日">{employee.last_working_day || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="教育背景" bordered column={2} size="small">
        <Descriptions.Item label="学历">{employee.education || '-'}</Descriptions.Item>
        <Descriptions.Item label="学位">{employee.degree || '-'}</Descriptions.Item>
        <Descriptions.Item label="专业">{employee.major || '-'}</Descriptions.Item>
        <Descriptions.Item label="毕业院校">{employee.school || '-'}</Descriptions.Item>
        <Descriptions.Item label="毕业时间">{employee.graduation_date || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="资格证书" bordered column={2} size="small">
        <Descriptions.Item label="职称">{employee.qualification_type || '-'}</Descriptions.Item>
        <Descriptions.Item label="技能证书">
          {employee.qualifications?.length ? employee.qualifications.join('、') : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="证书编号">{employee.certificate_number || '-'}</Descriptions.Item>
        <Descriptions.Item label="证书复审时间">{employee.certificate_review_date || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="合同信息" bordered column={2} size="small">
        <Descriptions.Item label="首次合同开始">{employee.contract_start_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="首次合同结束">{employee.contract_end_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="第二次续签开始">{employee.contract_start_2 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第二次合同结束">{employee.contract_end_2 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第三次续签开始">{employee.contract_start_3 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第三次合同结束">{employee.contract_end_3 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第四次续签开始">{employee.contract_start_4 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第四次合同结束">{employee.contract_end_4 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第五次续签">{employee.contract_start_5 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期5">{employee.contract_end_5 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第六次续签">{employee.contract_start_6 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期6">{employee.contract_end_6 || '-'}</Descriptions.Item>
        <Descriptions.Item label="审批负责人">{employee.dept_leader_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同审批意见">
          {employee.contract_opinion
            ? <Tag color={employee.contract_opinion === '同意续签' ? 'green' : 'red'}>{employee.contract_opinion}</Tag>
            : <Tag>待审批</Tag>}
        </Descriptions.Item>
      </Descriptions>
      <div style={{ marginTop: 8 }}>
        <Link href={`/hr/contracts?keyword=${encodeURIComponent(employee.name)}`} target="_blank">
          <Button size="small" icon={<FileTextOutlined />}>查看合同台账</Button>
        </Link>
      </div>

      <Divider />

      <Descriptions title="工作经历" bordered column={1} size="small">
        <Descriptions.Item label="工作经验一">{employee.work_experience_1 || '-'}</Descriptions.Item>
        <Descriptions.Item label="工作经验二">{employee.work_experience_2 || '-'}</Descriptions.Item>
        <Descriptions.Item label="工作经验三">{employee.work_experience_3 || '-'}</Descriptions.Item>
        <Descriptions.Item label="工作经验四">{employee.work_experience_4 || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="联系信息" bordered column={2} size="small">
        <Descriptions.Item label="联系电话">{maskPhone(employee.phone)}</Descriptions.Item>
        <Descriptions.Item label="电子邮箱">{employee.email || '-'}</Descriptions.Item>
        <Descriptions.Item label="紧急联系人">{employee.emergency_contact_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="紧急联系人电话">{maskPhone(employee.emergency_contact_phone)}</Descriptions.Item>
        <Descriptions.Item label="与本人关系">{employee.emergency_contact_relation || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="其他" bordered column={2} size="small">
        <Descriptions.Item label="档案编号">{employee.archive_number || '-'}</Descriptions.Item>
        <Descriptions.Item label="培训档案编号">{employee.training_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="异动记录" span={2}>{employee.transfer_history || '-'}</Descriptions.Item>
        <Descriptions.Item label="备注" span={2}>
          {employee.remarks?.length ? employee.remarks.join('、') : '-'}
        </Descriptions.Item>
      </Descriptions>
    </Drawer>
  )
}
