'use client'

import {
  BankOutlined,
  BookOutlined,
  FileProtectOutlined,
  FileSearchOutlined,
  LoginOutlined,
  SettingOutlined,
  SwapOutlined,
  TeamOutlined,
  UserDeleteOutlined,
} from '@ant-design/icons'
import { ModuleLandingCards, type ModuleLandingEntry } from '@/components/shared/ModuleLandingCards'

const entries: ModuleLandingEntry[] = [
  { title: '部门管理', description: '组织架构和部门信息', href: '/hr/departments', icon: <BankOutlined /> },
  { title: '员工管理', description: '员工统计、档案与飞书联系人', href: '/hr/employee-management', icon: <TeamOutlined />, dashboard: true },
  { title: '招聘管理', description: '职位与候选人管理', href: '/hr/recruitment', icon: <FileSearchOutlined /> },
  { title: '入职台账', description: '入职记录与飞书同步', href: '/hr/onboarding', icon: <LoginOutlined /> },
  { title: '离职管理', description: '离职流程和记录', href: '/hr/offboarding', icon: <UserDeleteOutlined /> },
  { title: '岗位调动管理', description: '岗位调动记录与审批', href: '/hr/position-transfer', icon: <SwapOutlined /> },
  { title: '合同管理', description: '合同台账、到期提醒与续签', href: '/hr/contracts', icon: <FileProtectOutlined /> },
  { title: '培训管理', description: '培训计划、资料和记录', href: '/hr/training', icon: <BookOutlined /> },
  { title: 'HR设置', description: '飞书同步、提醒与审批配置', href: '/hr/settings/feishu', icon: <SettingOutlined /> },
]

export default function HrPage() {
  return <ModuleLandingCards title="人事管理" description="查看人员、组织、合同与培训业务入口" entries={entries} />
}
