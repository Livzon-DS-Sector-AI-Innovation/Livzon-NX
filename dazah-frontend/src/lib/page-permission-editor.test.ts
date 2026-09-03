import { expect, it } from 'vitest'
import type { components } from '@/types/generated/schema'
import { changePageLevels, highRiskPageKeys, pageGrantChanges, type PageEditorGrant } from './page-permission-editor'

it('adds dependencies when selecting operate', () => {
  expect(changePageLevels([], ['operate'])).toEqual(['access', 'query', 'operate'])
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
  expect(changes[0].after).toBe('用户覆盖；访问、查询、操作；作废员工档案')
  expect(changes[0].after).not.toContain('采购部')
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
