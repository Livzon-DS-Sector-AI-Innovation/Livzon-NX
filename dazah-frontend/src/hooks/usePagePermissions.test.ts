import { describe, expect, it } from 'vitest'
import type { AuthUser } from '@/stores/auth'
import { pagePermissionFlags } from './usePagePermissions'

const user: AuthUser = {
  id: 'permission-test', name: '权限验收用户', role: 'user', permissions: ['hr:write'],
  page_permissions: [{
    page_key: 'hr:contracts:contracts-ledger', module_code: 'hr',
    permissions: ['access', 'query', 'operate'], sensitive_actions: ['delete'],
    data_scope: { scope_type: 'all', department_ids: [] }, source: 'user', source_role_names: [],
  }],
}

describe('business page permission flags', () => {
  it('does not infer grants from legacy module write permission', () => {
    expect(pagePermissionFlags(user, 'warehouse:warehouse-settings').canOperate).toBe(false)
  })
  it('requires each independent sensitive action', () => {
    const flags = pagePermissionFlags(user, 'hr:contracts:contracts-ledger')
    expect(flags.canOperate).toBe(true)
    expect(flags.canDelete).toBe(true)
    expect(flags.canSync).toBe(false)
    expect(flags.canExport).toBe(false)
  })
  it('denies after grants are removed and for anonymous users', () => {
    expect(pagePermissionFlags({ ...user, page_permissions: [] }, 'hr:contracts:contracts-ledger').canDelete).toBe(false)
    expect(pagePermissionFlags(null, undefined).canQuery).toBe(false)
  })
  it('preserves administrator authority', () => {
    expect(pagePermissionFlags({ ...user, role: 'admin' }, undefined).canSync).toBe(true)
  })
})
