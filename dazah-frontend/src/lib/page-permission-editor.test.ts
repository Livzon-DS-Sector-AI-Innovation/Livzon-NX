import { expect, it } from 'vitest'
import type { components } from '@/types/generated/schema'
import {
  changePageLevels, highRiskPageKeys, pageGrantChanges, pagePermissionTier,
  pageGrantChangeKind, pagePermissionTierLabel, permissionsForTier, type PageEditorGrant,
  pageScopeIssue, pageScopeSummary,
} from './page-permission-editor'

it('adds dependencies when selecting operate', () => {
  expect(changePageLevels([], ['operate'])).toEqual(['access', 'query', 'operate'])
})

it('maps dependent permission arrays to one readable tier', () => {
  expect(permissionsForTier('operate')).toEqual(['access', 'query', 'operate'])
  expect(pagePermissionTier(['access', 'query'])).toBe('query')
  expect(pagePermissionTierLabel(['access'])).toBe('仅入口')
  expect(pagePermissionTierLabel(['access', 'query', 'operate'])).toBe('普通操作')
  expect(pagePermissionTierLabel([])).toBe('无权限')
})

it('summarizes stored data scope without exposing raw department ids', () => {
  expect(pageScopeSummary('department_tree', [])).toBe('本部门及下级')
  expect(pageScopeSummary('departments', ['od-1'])).toBe('指定 1 个部门')
  expect(pageScopeSummary('departments', ['od-1'], new Map([['od-1', '质量部']]))).toBe('指定部门：质量部')
  expect(pageScopeSummary('all', [])).toBe('全部部门')
})

it('rejects empty, stale and unsupported editable data scopes', () => {
  const active = new Set(['od-active'])
  expect(pageScopeIssue('departments', [], ['departments'], active)).toContain('至少选择')
  expect(pageScopeIssue('departments', ['od-stale'], ['departments'], active)).toContain('已失效')
  expect(pageScopeIssue('self', [], ['department_tree'], active)).toContain('不再受此页面支持')
  expect(pageScopeIssue('departments', ['od-active'], ['departments'], active)).toBeUndefined()
})

it('classifies grant impact for review', () => {
  expect(pageGrantChangeKind(before, { ...before, mode: 'custom' })).toBe('source')
  expect(pageGrantChangeKind(before, { ...before, permissions: ['access', 'query', 'operate'] })).toBe('expand')
  expect(pageGrantChangeKind(before, { ...before, permissions: [] })).toBe('revoke')
  expect(pageGrantChangeKind(
    { ...before, permissions: ['access', 'query', 'operate'], sensitiveActions: ['delete'] },
    { ...before, permissions: ['access', 'query'], sensitiveActions: ['export'] },
  )).toBe('mixed')
})

const definition: components['schemas']['PagePermissionDefinitionOut'] = { page_key: 'hr:employee-management:profile', module_code: 'hr', page_name: '员工管理',
  route_path: '/hr/employee-management', sensitive_actions: [
    { key: 'delete', name: '作废员工档案', category: 'destructive', description: '作废记录' },
  ] }
const before: PageEditorGrant = { mode: 'inherit', permissions: ['access', 'query'],
  sensitiveActions: [], scopeType: 'department_tree', departmentIds: [] }

it('previews permission, override, scope and high risk changes in Chinese', () => {
  const after: PageEditorGrant = { mode: 'custom', permissions: ['access', 'query', 'operate'],
    sensitiveActions: ['delete'], scopeType: 'departments', departmentIds: ['stable-id'] }
  const changes = pageGrantChanges([definition], { [definition.page_key]: before },
    { [definition.page_key]: after }, new Map([['stable-id', '采购部']]))
  expect(changes).toHaveLength(1)
  expect(changes[0].pageName).toBe('人事管理 · 员工管理')
  expect(changes[0].before).toContain('角色基线')
  expect(changes[0].after).toBe('用户覆盖；普通操作；指定部门及下级；采购部；作废员工档案')
  expect(changes[0].after).toContain('采购部')
  expect(changes[0].after).not.toContain('stable-id')
})

it('does not report a change for selection ordering alone', () => {
  expect(pageGrantChanges([definition], { [definition.page_key]: before },
    { [definition.page_key]: { ...before, permissions: ['query', 'access'] } }, new Map())).toEqual([])
})

it('expands only pages declaring independent high risk actions', () => {
  expect(highRiskPageKeys([definition, { ...definition, page_key: 'hr:other', sensitive_actions: [] }])).toEqual([definition.page_key])
})

it('distinguishes explicit denial from an inherited empty grant', () => {
  const empty = { ...before, permissions: [] }
  const changes = pageGrantChanges([definition], { [definition.page_key]: empty },
    { [definition.page_key]: { ...empty, mode: 'custom' } }, new Map())
  expect(changes[0].after).toContain('用户覆盖；无权限')
})
it('removes dependent rights when query or access is unchecked', () => {
  expect(changePageLevels(['access', 'query', 'operate'], ['access', 'operate'])).toEqual(['access'])
  expect(changePageLevels(['access', 'query', 'operate'], ['query', 'operate'])).toEqual([])
  expect(changePageLevels(['access', 'query', 'operate'], ['access', 'query'])).toEqual(['access', 'query'])
})
