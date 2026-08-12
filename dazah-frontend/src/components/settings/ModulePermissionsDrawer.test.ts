import { describe, expect, it } from 'vitest'
import type { UserModulePermissionsOut } from '@/actions/users'
import {
  initialEditableState,
  permissionOptions,
} from './ModulePermissionsDrawer'

const modules = [
  {
    module_code: 'production',
    module_name: '生产管理',
    description: '生产管理',
  },
  {
    module_code: 'equipment',
    module_name: '设备管理',
    description: '设备管理',
  },
]

function permissionResult(
  grants: UserModulePermissionsOut['grants'] = []
): UserModulePermissionsOut {
  return {
    user_id: '00000000-0000-0000-0000-000000000001',
    grant_version: 0,
    available_modules: modules,
    grants,
  }
}

describe('module permission defaults', () => {
  it('enables every configurable permission for modules without a saved grant', () => {
    const editable = initialEditableState(permissionResult())
    const expected = permissionOptions.map((option) => option.value)

    expect(editable.production.permissions).toEqual(expected)
    expect(editable.equipment.permissions).toEqual(expected)
    expect(expected).toEqual([
      'module.view',
      'module.agent.read',
      'module.agent.execute',
      'module.agent.automate',
    ])
  })

  it('preserves saved choices and excludes the unused legacy governance permission', () => {
    const editable = initialEditableState(
      permissionResult([
        {
          module_code: 'production',
          module_name: '生产管理',
          permissions: ['module.view', 'module.admin'],
          data_scope: {},
          grant_version: 1,
          granted_by: '00000000-0000-0000-0000-000000000002',
          status: 'active',
          updated_at: '2026-08-11T00:00:00Z',
        },
      ])
    )

    expect(editable.production.permissions).toEqual(['module.view'])
    expect(editable.equipment.permissions).toEqual(
      permissionOptions.map((option) => option.value)
    )
  })
})
