import { describe, expect, it } from 'vitest'
import { SYSTEM_PERMISSION_PAGES } from './SystemPermissionsPanel'

describe('system permissions settings entry', () => {
  it('keeps authorization and verification pages without the retired menu management entry', () => {
    expect(SYSTEM_PERMISSION_PAGES.map((page) => page.href)).toEqual([
      '/system/roles',
      '/system/user-roles',
      '/system/dept-roles',
      '/system/permission-verification',
      '/settings?tab=permissions&view=impersonation',
    ])
    expect(SYSTEM_PERMISSION_PAGES.find((page) => page.href === '/system/dept-roles')).toMatchObject({
      title: '角色映射',
      description: '搜索用户或按部门查询，为所选用户批量分配角色。',
    })
  })

  it('keeps role management guidance and omits the user roles description', () => {
    expect(SYSTEM_PERMISSION_PAGES.find((page) => page.href === '/system/roles')?.description)
      .toContain('菜单页面')
    expect(SYSTEM_PERMISSION_PAGES.find((page) => page.href === '/system/user-roles'))
      .not.toHaveProperty('description')
  })
})
