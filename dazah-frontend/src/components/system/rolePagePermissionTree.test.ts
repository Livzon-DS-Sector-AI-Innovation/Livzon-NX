import { expect, it } from 'vitest'
import { buildPermissionTree, changeTreePermission, filterAuthorizedTree } from './rolePagePermissionTree'
import type { PageEditorGrant } from '@/lib/page-permission-editor'

const keys = ['purchasing:apply:hardware', 'purchasing:apply:labor:special', 'purchasing:approval:hardware']
const definitions = keys.map((page_key) => ({ page_key, page_name: page_key, module_code: 'purchasing', route_path: '/' }))
const grant: PageEditorGrant = { permissions: [], sensitiveActions: [], scopeType: 'departments', departmentIds: ['dept'] }

it('builds all nested groups, retains parent definitions and isolates siblings', () => {
  const tree = buildPermissionTree([...definitions, { ...definitions[0], page_key: 'purchasing:apply' }])
  expect(tree).toHaveLength(2)
  expect(tree[0].pageKeys).toEqual([keys[0], keys[1], 'purchasing:apply'])
  expect(tree[0].children![1].children![0].page_key).toBe(keys[1])
  expect(tree[0].definition?.page_key).toBe('purchasing:apply')
})

it('retains ancestors and full cascade targets when filtering unauthorized descendants', () => {
  const state = Object.fromEntries(keys.map((key, index) => [key, { ...grant, permissions: index === 0 ? ['access'] as const : [] }]))
  const grants: Record<string, PageEditorGrant> = Object.fromEntries(Object.entries(state).map(([key, value]) => [key, { ...value, permissions: [...value.permissions] }]))
  const tree = filterAuthorizedTree(buildPermissionTree(definitions), grants)
  expect(tree).toHaveLength(1)
  expect(tree[0].children).toHaveLength(1)
  const next = changeTreePermission(grants, tree[0].pageKeys, 'operate', true)
  expect(next[keys[1]].permissions).toEqual(['access', 'query', 'operate'])
  expect(next[keys[1]].sensitiveActions).toEqual([])
  expect(next[keys[1]].departmentIds).toEqual(['dept'])
  expect(next[keys[2]]).toBe(grants[keys[2]])
  expect(grants[keys[1]].permissions).toEqual([])
})

it('clears dependent and sensitive rights recursively while preserving other grants', () => {
  const grants = Object.fromEntries(keys.map((key) => [key, { ...grant, permissions: ['access', 'query', 'operate'] as PageEditorGrant['permissions'], sensitiveActions: ['delete'] }]))
  const next = changeTreePermission(grants, buildPermissionTree(definitions)[0].pageKeys, 'query', false)
  expect(next[keys[0]].permissions).toEqual(['access'])
  expect(next[keys[1]].sensitiveActions).toEqual([])
  expect(next[keys[2]].sensitiveActions).toEqual(['delete'])
  expect(buildPermissionTree([])).toEqual([])
  expect(filterAuthorizedTree(buildPermissionTree(definitions), {})).toEqual([])
})
