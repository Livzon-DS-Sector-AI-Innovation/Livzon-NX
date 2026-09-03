import { describe, expect, it } from 'vitest'
import type { UserPagePermissionsOut } from '@/actions/users'
import { initialPageEditableState, roleBaselineState } from './ModulePermissionsDrawer'

function permissionResult(
  overrides: Partial<UserPagePermissionsOut> = {}
): UserPagePermissionsOut {
  return {
    user_id: '00000000-0000-0000-0000-000000000001',
    grant_version: 3,
    definitions: [
      {
        page_key: 'hr:employee-management:profile',
        module_code: 'hr',
        page_name: '员工管理',
        route_path: '/hr/employee-management',
        supported_scope_types: ['department_tree', 'departments', 'all'],
      },
    ],
    grants: [],
    custom_page_keys: [],
    module_rollouts: { hr: 'draft' },
    ...overrides,
  }
}

describe('page permission editor state', () => {
  it('restores actual role permissions and scope instead of stale user overrides', () => {
    const state = roleBaselineState(permissionResult({ custom_page_keys: ['hr:employee-management:profile'],
      grants: [{ page_key: 'hr:employee-management:profile', module_code: 'hr', permissions: [],
        data_scope: { scope_type: 'all' }, source: 'none' }],
      role_grants: [{ page_key: 'hr:employee-management:profile', module_code: 'hr', permissions: ['access', 'query'],
        data_scope: { scope_type: 'departments', department_ids: ['od-1'] }, source: 'role' }],
    }))['hr:employee-management:profile']
    expect(state.mode).toBe('inherit')
    expect(state.permissions).toEqual(['access', 'query'])
    expect(state.scopeType).toBe('departments')
    expect(state.departmentIds).toEqual(['od-1'])
  })
  it('does not grant an unconfigured page by default', () => {
    const editable = initialPageEditableState(permissionResult())
    expect(editable['hr:employee-management:profile']).toEqual({
      mode: 'inherit',
      permissions: [],
      sensitiveActions: [],
      scopeType: 'department_tree',
      departmentIds: [],
    })
  })

  it('preserves a user exact deny instead of restoring the role baseline', () => {
    const editable = initialPageEditableState(
      permissionResult({
        custom_page_keys: ['hr:employee-management:profile'],
        grants: [
          {
            page_key: 'hr:employee-management:profile',
            module_code: 'hr',
            permissions: [],
            sensitive_actions: [],
            data_scope: { scope_type: 'department_tree', department_ids: [] },
            source: 'none',
            source_role_names: [],
          },
        ],
      })
    )
    expect(editable['hr:employee-management:profile'].mode).toBe('custom')
    expect(editable['hr:employee-management:profile'].permissions).toEqual([])
  })

  it('normalizes operation into query and access for display', () => {
    const editable = initialPageEditableState(
      permissionResult({
        grants: [
          {
            page_key: 'hr:employee-management:profile',
            module_code: 'hr',
            permissions: ['operate'],
            sensitive_actions: ['delete'],
            data_scope: { scope_type: 'all', department_ids: [] },
            source: 'role',
            source_role_names: ['人事经办员'],
          },
        ],
      })
    )
    expect(editable['hr:employee-management:profile'].permissions).toEqual([
      'access',
      'query',
      'operate',
    ])
  })
})
