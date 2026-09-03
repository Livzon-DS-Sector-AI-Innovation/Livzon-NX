import { afterEach, describe, expect, it } from 'vitest'

import { useAuthStore } from './auth'

describe('authentication display store', () => {
  afterEach(() => useAuthStore.getState().clearUser())

  it('grants all page operations to the system administrator and removes them on demotion', () => {
    useAuthStore.getState().setUser({ id: 'admin', name: '系统管理员', role: 'admin',
      page_permission_rollouts: { procurement: 'enforced' }, page_permissions: [] })
    expect(useAuthStore.getState().hasPagePermission('purchasing:supplier', 'operate', 'bulk_import')).toBe(true)
    expect(useAuthStore.getState().hasPermission('quality.write')).toBe(true)
    useAuthStore.getState().setUser({ id: 'admin', name: '普通用户', role: 'user',
      page_permission_rollouts: { procurement: 'enforced' }, page_permissions: [] })
    expect(useAuthStore.getState().hasPagePermission('purchasing:supplier', 'query')).toBe(false)
    expect(useAuthStore.getState().hasPermission('quality.write')).toBe(false)
  })

  it('requires explicit page operations and high-risk rights after publication', () => {
    const pageKey = 'purchasing:supplier'
    expect(useAuthStore.getState().hasPagePermission(pageKey, 'query')).toBe(false)
    useAuthStore.getState().setUser({ id: 'user', name: '经办员', permissions: ['*'],
      page_permission_rollouts: { procurement: 'enforced' }, page_permissions: [{
        page_key: pageKey, module_code: 'procurement', permissions: ['access', 'query'],
        sensitive_actions: [], data_scope: { scope_type: 'not_applicable' }, source: 'user',
      }] })
    expect(useAuthStore.getState().hasPagePermission(pageKey, 'query')).toBe(true)
    expect(useAuthStore.getState().hasPagePermission(pageKey, 'operate', 'bulk_import')).toBe(false)
    expect(useAuthStore.getState().hasPagePermission('purchasing:order', 'query')).toBe(false)
    useAuthStore.getState().setUser({ id: 'user', name: '经办员', page_permission_rollouts: { procurement: 'draft' } })
    expect(useAuthStore.getState().hasPagePermission(pageKey, 'operate')).toBe(true)
  })

  it('only reports explicitly granted permissions or the wildcard', () => {
    useAuthStore.getState().setUser({
      id: 'user-1',
      name: '管理员',
      permissions: ['quality.read'],
    })

    expect(useAuthStore.getState().hasPermission('quality.read')).toBe(true)
    expect(useAuthStore.getState().hasPermission('quality.write')).toBe(false)

    useAuthStore.getState().setUser({
      id: 'user-2',
      name: '超级管理员',
      permissions: ['*'],
    })
    expect(useAuthStore.getState().hasPermission('quality.write')).toBe(true)
  })
})
