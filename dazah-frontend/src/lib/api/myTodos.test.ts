import { afterEach, describe, expect, it, vi } from 'vitest'
import { getPageKeyByPath, moduleMenus } from '@/lib/menu-config'
import type { User } from '@/types/user'
import { fetchMyTodos, getTodoSources } from './myTodos'

const path = '/quality/deviations/ledger'
const pageKey = getPageKeyByPath(path)!
const user: User = { id: 'test-user', name: '测试用户', role: 'user', status: 'active', auth_source: 'local', grant_version: 1, page_permission_rollouts: {}, page_permissions: [{
  page_key: pageKey, module_code: 'quality', permissions: ['access', 'query', 'operate'], sensitive_actions: ['approve'], source: 'user', data_scope: { scope_type: 'departments', department_ids: [] },
}] }

afterEach(() => vi.unstubAllGlobals())

describe('permission-scoped todos', () => {
  it('system administrators never get business sources even with grants, while ordinary administrators do', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    for (const roles of [[], ['super_admin']]) {
      const sources = getTodoSources({ ...user, role: 'admin', roles }, moduleMenus)
      expect(sources).toEqual([])
      expect(await fetchMyTodos(sources)).toEqual([])
    }
    expect(fetcher).not.toHaveBeenCalled()
    expect(getTodoSources({ ...user, role: 'admin', roles: ['ordinary_admin'] }, moduleMenus).some((source) => source.key === pageKey)).toBe(true)
  })
  it('never reads procurement todos even with approval grants or administrator access', async () => {
    const purchaseGrant = { ...user.page_permissions![0], page_key: getPageKeyByPath('/purchasing/approval/hardware/department-head')!, module_code: 'procurement' }
    const fetcher = vi.fn().mockImplementation(async () => Response.json({ items: [], total: 0, page: 1, page_size: 5 }))
    vi.stubGlobal('fetch', fetcher)
    const sources = getTodoSources({ ...user, page_permissions: [purchaseGrant] }, moduleMenus)
    expect(sources).toEqual([])
    expect(await fetchMyTodos(sources)).toEqual([])
    expect(fetcher).not.toHaveBeenCalled()
    const adminSources = getTodoSources({ ...user, role: 'admin' }, moduleMenus)
    expect(adminSources).toEqual([])
    expect(adminSources.every((source) => !source.path.startsWith('/purchasing/'))).toBe(true)
    await fetchMyTodos(adminSources)
    expect(fetcher.mock.calls.every(([url]) => !/procurement|purchase-requests/.test(url))).toBe(true)
  })
  it('requires approval permission for HR transfers and reads the personal endpoint', () => {
    const grant = { ...user.page_permissions![0], page_key: 'hr:position-transfer', module_code: 'hr' }
    const sources = getTodoSources({ ...user, page_permissions: [grant] }, moduleMenus)
    expect(sources).toHaveLength(1)
    expect(sources[0].apiPath).toContain('/api/v1/hr/my-todos?')
    expect(sources[0].apiPath).toContain('kind=position-transfer')
    expect(getTodoSources({ ...user, page_permissions: [{ ...grant, sensitive_actions: [] }] }, moduleMenus)).toEqual([])
  })
  it('includes granted quality registration and HR work without requiring approval permission', async () => {
    const paths = ['/quality/capas/plans', '/registration/declaration-progress/international-planned-in-progress', '/hr/training/plan-tracking']
    const actor: User = { ...user, page_permissions: paths.map((entry) => ({ ...user.page_permissions![0], page_key: getPageKeyByPath(entry)!, sensitive_actions: [] })) }
    const sources = getTodoSources(actor, moduleMenus)
    expect(sources).toHaveLength(3)
    expect(sources.find((source) => source.apiPath.includes('/registration/'))?.path).toBe('/registration/validation-audit')
    const fetcher = vi.fn().mockImplementation(async () => Response.json({ items: [{ id: 'own', title: '本人任务', detail: '待处理', due_date: '2026-10-12' }], total: 17, page: 1, page_size: 5 }))
    vi.stubGlobal('fetch', fetcher)
    const groups = await fetchMyTodos(sources)
    expect(groups.map((group) => group.total)).toEqual([17, 17, 17])
    expect(groups.every((group) => group.items[0].due_date === '2026-10-12')).toBe(true)
    sources.forEach((source, index) => expect(fetcher.mock.calls[index][1].headers['X-Dazah-Page-Key']).toBe(source.key))
    expect(getTodoSources({ ...actor, page_permissions: actor.page_permissions?.map((grant) => ({ ...grant, permissions: ['access', 'query'] })) }, moduleMenus)).toEqual([])
  })

  it('keeps successful business feeds when another scoped feed fails', async () => {
    const sources = getTodoSources({ ...user, role: 'admin', roles: ['ordinary_admin'] }, moduleMenus).slice(0, 2)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json({ items: [{ id: 'mine', title: '本人任务', detail: '待处理' }], total: 9 })).mockResolvedValueOnce(new Response(null, { status: 403 })))
    const groups = await fetchMyTodos(sources)
    expect(groups[0].total).toBe(9)
    expect(groups[1].error).toContain('权限已变化')
  })

  it('includes only granted actionable workflows, including nested approvals', () => {
    const sources = getTodoSources(user, moduleMenus)
    expect(sources).toHaveLength(1)
    expect(sources[0].path).toBe(path)
    expect(sources[0].apiPath).toContain('kind=deviations')
    expect(getTodoSources({ ...user, page_permissions: [] }, moduleMenus)).toEqual([])
    expect(getTodoSources({ ...user, page_permissions: user.page_permissions?.map((grant) => ({ ...grant, sensitive_actions: [] })) }, moduleMenus)).toHaveLength(1)
    expect(getTodoSources({ ...user, page_permissions: user.page_permissions?.map((grant) => ({ ...grant, permissions: ['access', 'query'] })) }, moduleMenus)).toEqual([])
  })

  it('reads the granted page context even when the toolbar belongs to another module', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [{ id: 'task-1', title: '本人偏差调查', detail: '待本人处理' }], total: 1, page: 1, page_size: 5 }))
    vi.stubGlobal('fetch', fetcher)
    const groups = await fetchMyTodos(getTodoSources(user, moduleMenus))
    expect(groups[0].total).toBe(1)
    expect(groups[0].items[0].title).toContain('本人偏差调查')
    expect(fetcher.mock.calls[0][1].headers).toEqual({ 'X-Dazah-Page-Key': pageKey, 'X-Dazah-Page-Path': path })
  })

  it('reports partial failure rather than pretending there are no tasks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 403 })))
    const groups = await fetchMyTodos(getTodoSources(user, moduleMenus))
    expect(groups[0].error).toContain('权限已变化')
    expect(groups[0].items).toEqual([])
  })

  it('never reads APIs for a user without task permissions', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    expect(await fetchMyTodos([])).toEqual([])
    expect(fetcher).not.toHaveBeenCalled()
  })
})


it('equipment todo sources resolve maintenance only; inspection kind retired', () => {
  // 巡检待办 kind 已随本地巡检旧轨下线：巡检授权不产生待办来源
  const inspectionGrant = { ...user.page_permissions![0], page_key: 'equipment:inspection', module_code: 'equipment' }
  expect(getTodoSources({ ...user, page_permissions: [inspectionGrant] }, moduleMenus)).toEqual([])

  // 维保功能授权产生功能页待办来源；待办跳转到统一工作台的维保模块
  const grant = { ...user.page_permissions![0], page_key: 'equipment:maintenance', module_code: 'equipment' }
  const sources = getTodoSources({ ...user, page_permissions: [grant] }, moduleMenus)
  expect(sources).toHaveLength(1)
  expect(sources[0].key).toBe('equipment:maintenance')
  expect(sources[0].path).toBe('/equipment?module=maintenance')
  expect(sources[0].apiPath).toContain('kind=maintenance')
  const scoped = { ...grant, page_key: 'equipment:workshop-101-1:maintenance-101-1' }
  expect(getTodoSources({ ...user, page_permissions: [scoped] }, moduleMenus)[0].path).toBe('/equipment?module=maintenance')
})
