import { describe, expect, it } from 'vitest'
import {
  expandEquipmentPagePermissions,
  getAuthorizedDirectoryEntryPath,
  getFirstAuthorizedModulePath,
  getPostLoginPath,
  getAuthorizedPageMenus,
  getPageKeyByPath,
  getPermissionModuleName,
  moduleMenus,
  type PageAccessSummary,
} from './menu-config'

describe('page permission menu boundary', () => {
  it('resolves every enabled directory entry to a grantable leaf identity', () => {
    const leaves = new Set<string>()
    const directories: string[] = []
    function walk(items: typeof moduleMenus[number]['children'], parent: string) {
      for (const item of items) {
        if (item.disabled || item.adminOnly) continue
        const key = `${parent}:${item.key}`
        if (item.children?.length) {
          if (item.path) directories.push(item.path)
          walk(item.children, key)
        } else if (item.path) leaves.add(key)
      }
    }
    for (const entry of moduleMenus) walk(entry.children, entry.key)
    for (const path of directories) {
      expect(leaves.has(getPageKeyByPath(path) ?? ''), path).toBe(true)
    }
  })
  it('opens every enabled directory with its queryable descendant grants', () => {
    function walk(items: typeof moduleMenus[number]['children'], moduleCode: string) {
      for (const item of items) {
        if (item.disabled || item.adminOnly) continue
        if (item.children?.length) {
          if (item.path) {
            const primary = getPageKeyByPath(item.path)!
            const grants = [{ page_key: primary, module_code: moduleCode, permissions: ['access', 'query'] as Array<'access' | 'query'> }]
            expect(getAuthorizedDirectoryEntryPath(item.path, grants), item.path).toBe(item.path)
            expect(getAuthorizedDirectoryEntryPath(item.path, []), item.path).toBeUndefined()
            function check(children: typeof items) {
              for (const child of children) {
                if (child.disabled || child.adminOnly) continue
                if (child.children?.length) check(child.children)
                else if (child.path) {
                  const key = getPageKeyByPath(child.path.split('?')[0])!
                  const leafGrant = [{ ...grants[0], page_key: key }]
                  expect(getAuthorizedDirectoryEntryPath(item.path, leafGrant), child.path)
                    .toBe(key === primary ? item.path : child.path)
                }
              }
            }
            check(item.children)
          }
          walk(item.children, moduleCode)
        }
      }
    }
    for (const entry of moduleMenus) walk(entry.children, entry.moduleCode)
    expect(getAuthorizedDirectoryEntryPath('/quality/deviations/not-a-page', [{
      page_key: 'quality:deviations:deviation-records', module_code: 'quality', permissions: ['access', 'query'],
    }])).toBeUndefined()
  })
  it('uses the deviation ledger permission for the deviation dashboard, preserving sibling identities', () => {
    expect(getPageKeyByPath('/quality/deviations')).toBe('quality:deviations:deviation-ledger')
    expect(getPageKeyByPath('/quality/deviations/records')).toBe('quality:deviations:deviation-records')
  })
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

  it.each([undefined, [], ['quality']])('opens a module from pages regardless of legacy module grants: %j', (moduleCodes) => {
    const grant = { page_key: 'hr:employee-management:profile', module_code: 'hr', permissions: ['access' as const] }
    expect(getAuthorizedPageMenus(moduleCodes, [grant]).map((module) => module.moduleCode)).toEqual(['hr'])
    expect(getFirstAuthorizedModulePath({ role: 'user', module_codes: moduleCodes, page_permissions: [grant] })).toBe('/hr/employee-management')
    expect(getAuthorizedPageMenus(moduleCodes, [{ ...grant, permissions: [] }])).toEqual([])
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

  it('preserves permitted task links and rejects unauthorized post-login targets', () => {
    const user = { role: 'user', page_permissions: [{ page_key: 'energy:entry', module_code: 'energy', permissions: ['access' as const, 'query' as const] }] }
    const target = '/energy/entry?task=task-1&source=feishu'
    expect(getPostLoginPath(user, target)).toBe(target)
    expect(getPostLoginPath(user, '/energy/settings')).toBe('/energy/entry')
    expect(getPostLoginPath({ role: 'admin' }, target)).toBe(target)
  })

  it.each(['https://other.test', '//other.test', '/\\other.test', '/energy/../auth/logout', '/login?next=/energy/entry', '/api/v1/identity/auth/logout', '/energy/entry\n'])('rejects unsafe or authentication post-login target %j', target => {
    expect(getPostLoginPath({ role: 'admin' }, target)).toBe('/production')
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

describe('equipment menu structure', () => {
  it('collapses the equipment module to the stats page plus the unified console', () => {
    const equipment = moduleMenus.find((menu) => menu.key === 'equipment')

    // 统一工作台：车间块 + 功能模块 Tab 都在页内；功能页 key 仍是授权实体
    expect(equipment?.children.map((item) => item.key)).toEqual([
      'stats',
      'console',
      'feishu-config',
    ])
    expect(equipment?.children.map((item) => item.path)).toEqual([
      '/equipment/stats',
      '/equipment',
      '/equipment/feishu-config',
    ])
    const console = equipment?.children.find((item) => item.key === 'console')
    expect(console?.anyOfPageKeys).toEqual([
      'equipment:assets',
      'equipment:maintenance',
      'equipment:inspection',
      'equipment:spare-parts',
      'equipment:personnel',
    ])
  })

  it.each([
    // 工作台根按聚合入口解析；旧功能页与旧车间子路径仍解析到功能页 key（由路由层重定向到工作台）
    ['/equipment', 'equipment:console'],
    ['/equipment/assets', 'equipment:assets'],
    ['/equipment/assets/101-1', 'equipment:assets'],
    ['/equipment/assets/201-1', 'equipment:assets'],
    ['/equipment/maintenance/101-1', 'equipment:maintenance'],
    ['/equipment/inspection/101-1', 'equipment:inspection'],
    ['/equipment/inspection/201-3', 'equipment:inspection'],
    ['/equipment/spare-parts/101-1', 'equipment:spare-parts'],
    ['/equipment/personnel/101-1', 'equipment:personnel'],
    ['/equipment/stats', 'equipment:stats'],
  ])('maps the equipment pages to functional permission keys: %s', (path, pageKey) => {
    expect(getPageKeyByPath(path)).toBe(pageKey)
  })

  it('projects legacy workshop-leaf grants onto functional pages with visible sections', () => {
    const grants = expandEquipmentPagePermissions([
      { page_key: 'equipment:workshop-101-1:inspection-101-1', module_code: 'equipment', permissions: ['access', 'query'] },
      { page_key: 'equipment:workshop-203:inspection-203', module_code: 'equipment', permissions: ['access', 'operate'] },
    ])
    const projected = grants.find((grant) => grant.page_key === 'equipment:inspection')
    expect(projected).toMatchObject({
      page_key: 'equipment:inspection',
      permissions: expect.arrayContaining(['access', 'query', 'operate']),
      visible_sections: ['101-1', '203'],
    })
  })

  it('keeps legacy full functional grants unlimited (no visible sections)', () => {
    const grants = expandEquipmentPagePermissions<PageAccessSummary>([
      { page_key: 'equipment:inspection', module_code: 'equipment', permissions: ['access', 'query'] },
      { page_key: 'equipment:workshop-101-1:inspection-101-1', module_code: 'equipment', permissions: ['access'] },
    ])
    const projected = grants.find((grant) => grant.page_key === 'equipment:inspection')
    // 全量授权已存在：车间叶授权不再额外投影，保持全部车间可见
    expect(projected?.visible_sections).toBeUndefined()
    expect(grants.filter((grant) => grant.page_key === 'equipment:inspection')).toHaveLength(1)
  })

  it('authorizes the console menu item from a legacy workshop grant', () => {
    const menus = getAuthorizedPageMenus([], [
      { page_key: 'equipment:workshop-201-1:inspection-201-1', module_code: 'equipment', permissions: ['access', 'query', 'operate'] },
    ])
    const equipment = menus.find((menu) => menu.key === 'equipment')
    // 巡检叶授权投影到 equipment:inspection，聚合入口 console 因任一模块授权而可见
    expect(equipment?.children?.map((item) => item.key)).toEqual(['console'])
    expect(getFirstAuthorizedModulePath({
      role: 'user',
      page_permissions: [
        { page_key: 'equipment:workshop-201-1:inspection-201-1', module_code: 'equipment', permissions: ['access', 'query'] },
      ],
    })).toBe('/equipment')
  })
})


describe('legacy equipment grant boundaries', () => {
  it('preserves an explicit denial and never grants unauthorized workshops', () => {
    // 车间叶授权 permissions 为空（显式拒绝）：不投影出功能页授权
    const grants = [
      { page_key: 'equipment:workshop-201-1:inspection-201-1', module_code: 'equipment', permissions: [] },
    ]
    expect(getAuthorizedPageMenus([], grants)).toEqual([])
    expect(getFirstAuthorizedModulePath({ role: 'user', page_permissions: grants })).toBe('/no-access')
  })
})
