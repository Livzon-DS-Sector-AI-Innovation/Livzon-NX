import { describe, expect, it } from 'vitest'
import {
  getFirstAuthorizedModulePath,
  getAuthorizedPageMenus,
  getPageKeyByPath,
  getPermissionModuleName,
  moduleMenus,
} from './menu-config'

describe('page permission menu boundary', () => {
  it('uses Chinese navigation names for every permission module, never raw module codes', () => {
    for (const item of moduleMenus) {
      expect(getPermissionModuleName(item.moduleCode)).toBe(item.label)
      expect(getPermissionModuleName(item.moduleCode)).toMatch(/[\u4e00-\u9fff]/)
    }
    expect(getPermissionModuleName('production')).toBe('生产管理')
    expect(getPermissionModuleName('equipment')).toBe('设备管理')
    expect(getPermissionModuleName('energy')).toBe('能源管理')
    expect(getPermissionModuleName('safety')).toBe('安全管理')
    expect(getPermissionModuleName('research')).toBe('研发管理')
    expect(getPermissionModuleName('registration')).toBe('注册管理')
    expect(getPermissionModuleName('administration')).toBe('行政管理')
    expect(getPermissionModuleName('unknown')).toBe('未命名模块')
  })
  it('filters an enforced module down to authorized leaf pages and ancestors', () => {
    const menus = getAuthorizedPageMenus(
      ['hr'],
      [
        {
          page_key: 'hr:employee-management:profile',
          module_code: 'hr',
          permissions: ['access'],
        },
      ],
      { hr: 'enforced' }
    )
    expect(menus).toHaveLength(1)
    expect(menus[0].children.map((item) => item.key)).toEqual([
      'employee-management',
    ])
  })

  it('keeps draft modules on the legacy menu rule', () => {
    const menus = getAuthorizedPageMenus(['hr'], [], { hr: 'draft' })
    expect(menus[0].children.length).toBeGreaterThan(1)
  })

  it('uses navigation order for the post-login module landing page', () => {
    expect(getFirstAuthorizedModulePath({
      role: 'user',
      module_codes: ['quality', 'administration', 'research'],
      page_permissions: [],
      page_permission_rollouts: {},
    })).toBe('/rd')
  })

  it('keeps the first platform module as the administrator landing page', () => {
    expect(getFirstAuthorizedModulePath({ role: 'admin' })).toBe('/production')
  })

  it('resolves dynamic detail URLs to the longest stable page key', () => {
    expect(getPageKeyByPath('/hr/profile')).toBe(
      'hr:employee-management:profile'
    )
  })
})

describe('procurement menu structure', () => {
  it('adds the new request categories and nests labor categories', () => {
    const purchasing = moduleMenus.find((menu) => menu.key === 'purchasing')
    const request = purchasing?.children.find((item) => item.key === 'request')

    expect(request?.children?.map((item) => item.key)).toEqual(
      expect.arrayContaining([
        'request-advertising-printing',
        'request-fire',
        'request-packaging',
        'request-labor',
        'request-urgent',
      ])
    )

    const labor = request?.children?.find((item) => item.key === 'request-labor')
    expect(labor?.children?.map((item) => item.key)).toEqual([
      'request-labor-special',
      'request-labor-miscellaneous',
    ])
    expect(request?.children?.some((item) => item.key === 'request-labor-protection')).toBe(false)
  })

  it('keeps approval labor categories under a collapsible labor parent', () => {
    const purchasing = moduleMenus.find((menu) => menu.key === 'purchasing')
    const approval = purchasing?.children.find((item) => item.key === 'approval')
    const labor = approval?.children?.find((item) => item.key === 'approval-labor')
    const advertisingPrinting = approval?.children?.find(
      (item) => item.key === 'approval-advertising-printing'
    )
    const urgent = approval?.children?.find((item) => item.key === 'approval-urgent')
    const hardware = approval?.children?.find((item) => item.key === 'approval-hardware')
    const electrical = approval?.children?.find((item) => item.key === 'approval-electrical')

    expect(advertisingPrinting?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/advertising-printing/department-head',
      '/purchasing/approval/advertising-printing/responsible-leader',
      '/purchasing/approval/advertising-printing/supervising-leader',
    ])
    expect(urgent?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/urgent/hardware-warehouse',
      '/purchasing/approval/urgent/department-head',
      '/purchasing/approval/urgent/responsible-leader',
      '/purchasing/approval/urgent/supervising-leader',
      '/purchasing/approval/urgent/finance-director',
      '/purchasing/approval/urgent/general-manager',
    ])
    expect(hardware?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/hardware/hardware-warehouse',
      '/purchasing/approval/hardware/department-head',
      '/purchasing/approval/hardware/responsible-leader',
      '/purchasing/approval/hardware/supervising-leader',
      '/purchasing/approval/hardware/general-manager',
    ])
    expect(electrical?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/electrical/hardware-warehouse',
      '/purchasing/approval/electrical/equipment-power',
      '/purchasing/approval/electrical/department-head',
      '/purchasing/approval/electrical/responsible-leader',
      '/purchasing/approval/electrical/supervising-leader',
    ])
    expect(labor?.children?.map((item) => item.key)).toEqual([
      'approval-labor-special',
      'approval-labor-miscellaneous',
    ])
    expect(labor?.children?.[0]?.children?.[0]?.path).toBe(
      '/purchasing/approval/labor-special/safety-officer'
    )
  })

  it('exposes procurement settings only as an admin menu item', () => {
    const settings = moduleMenus
      .find((menu) => menu.key === 'purchasing')
      ?.children.find((item) => item.key === 'settings')

    expect(settings).toMatchObject({
      label: '采购设置',
      path: '/purchasing/settings',
      adminOnly: true,
    })
  })

  it('exposes the material code library to procurement users', () => {
    const materialLibrary = moduleMenus
      .find((menu) => menu.key === 'purchasing')
      ?.children.find((item) => item.key === 'material-library')

    expect(materialLibrary).toMatchObject({
      label: '物料编码库',
      path: '/purchasing/material-library',
    })
    expect(materialLibrary?.adminOnly).toBeUndefined()
  })
})
