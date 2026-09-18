import { describe, expect, it } from 'vitest'
import { isSystemAdministrator, isSystemSettingsPath } from './administrator-role'

describe('system administrator distinction', () => {
  it('allows the system administrator into system settings', () => {
    expect(isSystemAdministrator({ role: 'admin', roles: ['super_admin'] })).toBe(true)
  })

  it('keeps ordinary administrators out of system settings', () => {
    expect(isSystemAdministrator({ role: 'admin', roles: ['ordinary_admin'] })).toBe(false)
  })

  it('keeps regular users out of system settings', () => {
    expect(isSystemAdministrator({ role: 'user', roles: [] })).toBe(false)
  })
})

describe('system settings paths', () => {
  it.each(['/settings', '/settings/', '/system/roles', '/system/user-roles'])(
    'protects %s', (path) => expect(isSystemSettingsPath(path)).toBe(true),
  )
  it('keeps business settings separate', () => {
    expect(isSystemSettingsPath('/purchasing/settings')).toBe(false)
  })
})
