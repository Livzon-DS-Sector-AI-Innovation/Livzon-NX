'use client'

import { Drawer, Descriptions, Divider, Tag, Button } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import Link from 'next/link'
import { OffboardingRecord } from '@/types/hr'

interface OffboardingDetailDrawerProps {
  open: boolean
  record: OffboardingRecord | null
  onClose: () => void
}

export default function OffboardingDetailDrawer({ open, record, onClose }: OffboardingDetailDrawerProps) {
  if (!record) return null

  const get = (field: string) => {
    const val = (record as any)[field]
    const empVal = record.employee ? (record.employee as any)[field] : undefined
    return val || empVal || '-'
  }

  return (
    <Drawer
      title={`离职详情 - ${get('name')}`}
      placement="right"
      open={open}
      onClose={onClose}
      styles={{ wrapper: { width: 720 } }}
      extra={
        record.employee_id ? (
          <Link href={`/hr/profile?employee_id=${record.employee_id}`}>
            <Button size="small" icon={<UserOutlined />}>查看员工档案</Button>
          </Link>
        ) : undefined
      }
    >
      <Descriptions title="离职信息" bordered column={2} size="small">
        <Descriptions.Item label="最后工作日">{record.offboarding_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="离职类型">
          <Tag>{record.offboarding_type}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="离职原因" span={2}>{record.reason || '-'}</Descriptions.Item>
        <Descriptions.Item label="交接状态" span={2}>
          <Tag color={record.handover_status === '已完成' ? 'success' : record.handover_status === '交接中' ? 'processing' : 'warning'}>
            {record.handover_status}
          </Tag>
        </Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="基本信息" bordered column={2} size="small">
        <Descriptions.Item label="工号">{get('employee_number')}</Descriptions.Item>
        <Descriptions.Item label="姓名">{get('name')}</Descriptions.Item>
        <Descriptions.Item label="域账户">{get('domain_account')}</Descriptions.Item>
        <Descriptions.Item label="性别">{get('gender')}</Descriptions.Item>
        <Descriptions.Item label="民族">{get('ethnic_group')}</Descriptions.Item>
        <Descriptions.Item label="出生年月">
          {record.birth_year && record.birth_month
            ? `${record.birth_year}年${record.birth_month}月`
            : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="年龄">{record.age ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="籍贯">{get('native_place')}</Descriptions.Item>
        <Descriptions.Item label="政治面貌">{get('political_status')}</Descriptions.Item>
        <Descriptions.Item label="婚姻状况">{get('marital_status')}</Descriptions.Item>
        <Descriptions.Item label="健康状况">{get('health_status')}</Descriptions.Item>
        <Descriptions.Item label="户口类别">{get('household_type')}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="证件信息" bordered column={2} size="small">
        <Descriptions.Item label="身份证号">{get('id_card')}</Descriptions.Item>
        <Descriptions.Item label="身份证有效期">{record.id_card_expiry || '-'}</Descriptions.Item>
        <Descriptions.Item label="现居住地址" span={2}>{record.current_address || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="组织信息" bordered column={2} size="small">
        <Descriptions.Item label="一级部门">{get('department')}</Descriptions.Item>
        <Descriptions.Item label="二级部门">{record.sub_department || '-'}</Descriptions.Item>
        <Descriptions.Item label="职位/岗位">{get('position')}</Descriptions.Item>
        <Descriptions.Item label="职级">{get('level')}</Descriptions.Item>
        <Descriptions.Item label="人员就业方式">{record.employment_type || '-'}</Descriptions.Item>
        <Descriptions.Item label="转正状态">{record.probation_status || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="职业生涯" bordered column={2} size="small">
        <Descriptions.Item label="入职日期">{record.hire_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="参加工作时间">{record.work_start_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="进本公司时间">{record.factory_entry_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="工龄">{record.work_years || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="教育背景" bordered column={2} size="small">
        <Descriptions.Item label="学历">{get('education')}</Descriptions.Item>
        <Descriptions.Item label="学位">{record.degree || '-'}</Descriptions.Item>
        <Descriptions.Item label="专业">{get('major')}</Descriptions.Item>
        <Descriptions.Item label="毕业院校">{get('school')}</Descriptions.Item>
        <Descriptions.Item label="毕业时间" span={2}>{record.graduation_date || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="资格证书" bordered column={2} size="small">
        <Descriptions.Item label="职称">{record.qualification_type || '-'}</Descriptions.Item>
        <Descriptions.Item label="技能证书">
          {record.qualifications?.length ? record.qualifications.join('、') : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="证书编号">{record.certificate_number || '-'}</Descriptions.Item>
        <Descriptions.Item label="证书复审时间">{record.certificate_review_date || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="合同信息" bordered column={2} size="small">
        <Descriptions.Item label="首次合同开始">{record.contract_start_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="首次合同结束">{record.contract_end_date || '-'}</Descriptions.Item>
        <Descriptions.Item label="第二次续签">{record.contract_start_2 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期2">{record.contract_end_2 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第三次续签">{record.contract_start_3 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期3">{record.contract_end_3 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第四次续签">{record.contract_start_4 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期4">{record.contract_end_4 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第五次续签">{record.contract_start_5 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期5">{record.contract_end_5 || '-'}</Descriptions.Item>
        <Descriptions.Item label="第六次续签">{record.contract_start_6 || '-'}</Descriptions.Item>
        <Descriptions.Item label="合同截止日期6">{record.contract_end_6 || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="工作经历" bordered column={1} size="small">
        <Descriptions.Item label="工作经验一">{record.work_experience_1 || '-'}</Descriptions.Item>
        <Descriptions.Item label="工作经验二">{record.work_experience_2 || '-'}</Descriptions.Item>
        <Descriptions.Item label="工作经验三">{record.work_experience_3 || '-'}</Descriptions.Item>
        <Descriptions.Item label="工作经验四">{record.work_experience_4 || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="联系信息" bordered column={2} size="small">
        <Descriptions.Item label="联系电话">{get('phone')}</Descriptions.Item>
        <Descriptions.Item label="电子邮箱">{get('email')}</Descriptions.Item>
        <Descriptions.Item label="紧急联系人">{record.emergency_contact_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="紧急联系人电话">{record.emergency_contact_phone || '-'}</Descriptions.Item>
        <Descriptions.Item label="与本人关系" span={2}>{record.emergency_contact_relation || '-'}</Descriptions.Item>
      </Descriptions>

      <Divider />

      <Descriptions title="其他" bordered column={2} size="small">
        <Descriptions.Item label="档案编号">{record.archive_number || '-'}</Descriptions.Item>
        <Descriptions.Item label="备注" span={2}>{record.notes || '-'}</Descriptions.Item>
      </Descriptions>
    </Drawer>
  )
}
