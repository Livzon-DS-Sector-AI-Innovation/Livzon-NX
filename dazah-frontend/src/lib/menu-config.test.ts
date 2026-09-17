import { describe, expect, it } from 'vitest'
import {
  getFirstAuthorizedModulePath,
  getAuthorizedPageMenus,
  getPageKeyByPath,
  getPermissionModuleName,
  moduleMenus,
} from './menu-config'

describe('page permission menu boundary', () => {
  it('resolves the HR contract landing URL to its grantable leaf', () => {
    expect(getPageKeyByPath('/hr/contracts')).toBe('hr:contracts:contracts-ledger')
  })
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
  it('filters a module down to authorized leaf pages and ancestors immediately', () => {
    const menus = getAuthorizedPageMenus(
      ['hr'],
      [
        {
          page_key: 'hr:employee-management:profile',
          module_code: 'hr',
          permissions: ['access'],
        },
      ],
    )
    expect(menus).toHaveLength(1)
    expect(menus[0].children.map((item) => item.key)).toEqual([
      'employee-management',
    ])
  })

  it('does not let verification status bypass saved page grants', () => {
    const menus = getAuthorizedPageMenus(['hr'], [])
    expect(menus).toEqual([])
  })

  it('uses navigation order for the post-login module landing page', () => {
    expect(getFirstAuthorizedModulePath({
      role: 'user',
      module_codes: ['quality', 'administration', 'research'],
      page_permissions: [{
        page_key: 'rd:project-initiation',
        module_code: 'research',
        permissions: ['access'],
      }],
      page_permission_rollouts: {},
    })).toBe('/rd/project-initiation')
  })

  it('keeps the first platform module as the administrator landing page', () => {
    expect(getFirstAuthorizedModulePath({ role: 'admin' })).toBe('/production')
  })

  it('keeps retired CPV routes out of the quality permission menu', () => {
    const quality = moduleMenus.find((menu) => menu.key === 'quality')
    expect(JSON.stringify(quality)).not.toContain('/quality/cpv')
    expect(getPageKeyByPath('/quality/cpv')).toBeUndefined()
  })

  it('lands directly on an authorized nested page when the module overview is denied', () => {
    expect(getFirstAuthorizedModulePath({ role: 'user', module_codes: ['production'],
      page_permissions: [{ page_key: 'production:batches:workshop-101-1', module_code: 'production', permissions: ['access', 'query'] }],
    })).toBe('/production/batches/workshop/101-1')
  })

  it.each([
    {},
    { module_codes: ['production'] },
    { module_codes: [], page_permissions: [{ page_key: 'production:overview', module_code: 'production', permissions: ['access' as const] }] },
    { module_codes: ['procurement'], page_permissions: [{ page_key: 'purchasing:settings', module_code: 'procurement', permissions: ['access' as const] }] },
    { module_codes: ['production'], page_permissions: [{ page_key: 'unknown', module_code: 'production', permissions: ['access' as const] }] },
    { module_codes: ['administration'], page_permissions: [{ page_key: 'admin:notice', module_code: 'administration', permissions: ['access' as const] }] },
  ])('uses the neutral landing page when no usable page is authorized: %j', (user) => {
    expect(getFirstAuthorizedModulePath({ role: 'user', ...user })).toBe('/no-access')
  })

  it('resolves dynamic detail URLs to the longest stable page key', () => {
    expect(getPageKeyByPath('/hr/profile')).toBe(
      'hr:employee-management:profile'
    )
  })

  it('resolves reviewed module landing routes to active leaf page keys', () => {
    expect(getPageKeyByPath('/hr/employee-management')).toBe(
      'hr:employee-management:profile'
    )
    expect(getPageKeyByPath('/warehouse/materials/dashboard')).toBe(
      'warehouse:materials:raw-summary'
    )
    expect(getPageKeyByPath('/registration/project')).toBe(
      'registration:project:project-ledger:international-associated-review'
    )
    expect(getPageKeyByPath('/registration/validation-audit/task-1')).toBe(
      'registration:project:declaration-progress:international-planned-in-progress'
    )
  })

  it.each([
    ['/production', 'production:overview'],
    ['/production/batches/workshop/101-1', 'production:batches:workshop-101-1'],
    ['/production/batches/workshop/101-2', 'production:batches:workshop-101-2'],
    ['/production/batches/workshop/102-1', 'production:batches:workshop-102-1'],
    ['/production/batches/workshop/102-2', 'production:batches:workshop-102-2'],
    ['/production/batches/workshop/103/phenylalanine', 'production:batches:workshop-103:ws103-phenylalanine'],
    ['/production/batches/workshop/103/lovastatin', 'production:batches:workshop-103:ws103-lovastatin'],
    ['/production/batches/workshop/201-1', 'production:batches:workshop-201-1'],
    ['/production/batches/workshop/201-2', 'production:batches:workshop-201-2'],
    ['/production/batches/workshop/201-3', 'production:batches:workshop-201-3'],
    ['/production/batches/workshop/202', 'production:batches:workshop-202'],
    ['/production/batches/workshop/203', 'production:batches:workshop-203'],
    ['/production/batches/workshop/203-3', 'production:batches:workshop-203-3'],
    ['/production/plan', 'production:plan:sales-plan'],
    ['/production/scheduling', 'production:plan:scheduling'],
    ['/production/shift-log/deviation', 'production:shift-log:shift-log-deviation'],
    ['/production/shift-log/quality', 'production:shift-log:shift-log-quality'],
    ['/production/shift-log/summary', 'production:shift-log:shift-log-summary'],
    ['/production/shift-log/handover', 'production:shift-log:shift-log-handover'],
    ['/production/label-verification', 'production:label-verification'],
    ['/production/pressure', 'production:pressure'],
  ])('maps every production menu page to its stable permission key: %s', (path, pageKey) => {
    expect(getPageKeyByPath(path)).toBe(pageKey)
  })

  it.each([
    '/production/process',
    '/production/process/parameters',
    '/production/records',
    '/production/balance',
  ])('does not register a removed production page: %s', (path) => {
    expect(getPageKeyByPath(path)).toBeUndefined()
  })

  it.each([
    ['/production/batches/workshop/201-2/extraction', 'production:batches:workshop-201-2'],
    ['/production/batches/workshop/201-3/scheduling', 'production:batches:workshop-201-3'],
    ['/production/batches/workshop/203/traceability', 'production:batches:workshop-203'],
    ['/production/pressure/audit', 'production:pressure'],
    ['/production/shift-log/deviation/event-1', 'production:shift-log:shift-log-deviation'],
  ])('inherits the workshop or feature page key for internal production routes: %s', (path, pageKey) => {
    expect(getPageKeyByPath(path)).toBe(pageKey)
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

describe('production menu structure', () => {
  it('exposes the production overview as the first production menu entry', () => {
    const production = moduleMenus.find((menu) => menu.key === 'production')
    expect(production?.children[0]).toMatchObject({
      key: 'overview',
      label: '生产管理概览',
      path: '/production',
    })
  })
})
