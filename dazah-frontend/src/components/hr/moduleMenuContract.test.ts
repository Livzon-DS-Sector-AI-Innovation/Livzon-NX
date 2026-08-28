import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('HR migrated menu contract', () => {
  it('matches the HR landing page entry menu', () => {
    const hr = moduleMenus.find((menu) => menu.moduleCode === 'hr')

    expect(hr?.children.map(({ key, label, path, children }) => ({ key, label, path, children }))).toEqual([
      { key: 'departments', label: '部门管理', path: '/hr/departments', children: undefined },
      { key: 'employee-management', label: '员工管理', path: '/hr/employee-management', children: undefined },
      { key: 'recruitment', label: '招聘管理', path: '/hr/recruitment', children: undefined },
      { key: 'onboarding', label: '入职台账', path: '/hr/onboarding', children: undefined },
      { key: 'offboarding', label: '离职管理', path: '/hr/offboarding', children: undefined },
      { key: 'position-transfer', label: '岗位调动管理', path: '/hr/position-transfer', children: undefined },
      { key: 'contracts', label: '合同管理', path: '/hr/contracts', children: undefined },
      { key: 'training', label: '培训管理', path: '/hr/training', children: undefined },
      { key: 'hr-settings', label: 'HR设置', path: '/hr/settings/feishu', children: undefined },
    ])
  })
})
