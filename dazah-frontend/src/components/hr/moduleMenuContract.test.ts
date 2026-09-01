import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('HR migrated menu contract', () => {
  it('matches the HR landing page entry menu', () => {
    const hr = moduleMenus.find((menu) => menu.moduleCode === 'hr')

    expect(hr?.children.map(({ key, label, path, children }) => ({ key, label, path, children }))).toEqual([
      { key: 'departments', label: '部门管理', path: '/hr/departments', children: undefined },
      {
        key: 'employee-management',
        label: '员工管理',
        path: '/hr/employee-management',
        children: [
          { key: 'profile', label: '员工档案', path: '/hr/profile' },
          { key: 'feishu-contacts', label: '飞书联系人', path: '/hr/feishu-contacts' },
        ],
      },
      { key: 'recruitment', label: '招聘管理', path: '/hr/recruitment', children: undefined },
      { key: 'onboarding', label: '入职台账', path: '/hr/onboarding', children: undefined },
      { key: 'offboarding', label: '离职管理', path: '/hr/offboarding', children: undefined },
      { key: 'position-transfer', label: '岗位调动管理', path: '/hr/position-transfer', children: undefined },
      {
        key: 'contracts',
        label: '合同管理',
        path: '/hr/contracts',
        children: [
          { key: 'contracts-ledger', label: '合同台账', path: '/hr/contracts' },
          { key: 'contract-approval-results', label: '合同到期审批结果', path: '/hr/contracts/approval-results' },
        ],
      },
      {
        key: 'training',
        label: '培训管理',
        path: '/hr/training',
        children: [
          { key: 'annual-plan', label: '年度培训计划', path: '/hr/training/annual-plan' },
          { key: 'sign-in-sheet', label: '培训资料', path: '/hr/training/sign-in' },
          { key: 'new-employee-training', label: '新员工培训', path: '/hr/training/new-employee' },
          { key: 'training-ledger', label: '培训台账', path: '/hr/training/ledger' },
          { key: 'employee-training-list', label: '员工培训清单', path: '/hr/training/employee-training-list' },
          { key: 'trainer', label: '培训师管理', path: '/hr/training/trainer' },
          { key: 'position-training', label: '岗位培训清单', path: '/hr/training/position-training' },
          { key: 'plan-tracking', label: '培训计划跟踪', path: '/hr/training/plan-tracking' },
        ],
      },
      {
        key: 'hr-settings',
        label: 'HR设置',
        path: '/hr/settings/feishu',
        children: [
          { key: 'hr-settings-feishu', label: '飞书设置', path: '/hr/settings/feishu' },
          { key: 'hr-settings-reminder', label: '提醒设置', path: '/hr/settings/reminder' },
          { key: 'hr-settings-approval', label: '审批流程设置', path: '/hr/settings/approval' },
          { key: 'hr-settings-dept-mapping', label: '培训部门映射', path: '/hr/settings/dept-mapping', permission: 'hr:write' },
          { key: 'hr-settings-dept-scopes', label: '部门权限配置', path: '/hr/settings/dept-scopes', permission: 'hr:write' },
        ],
      },
    ])
  })
})
