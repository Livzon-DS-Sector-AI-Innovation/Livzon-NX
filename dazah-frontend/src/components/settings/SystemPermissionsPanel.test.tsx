import { describe, expect, it } from 'vitest'
import { SYSTEM_PERMISSION_PAGES } from './SystemPermissionsPanel'

describe('system permissions settings entry', () => {
  it('keeps all five permission pages under the settings entry', () => {
    expect(SYSTEM_PERMISSION_PAGES.map((page) => page.href)).toEqual([
      '/system/roles',
      '/system/user-roles',
      '/system/dept-roles',
      '/system/menus',
      '/system/permission-verification',
    ])
  })
})
