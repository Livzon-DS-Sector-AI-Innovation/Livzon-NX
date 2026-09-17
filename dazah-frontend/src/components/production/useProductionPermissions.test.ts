import { describe, expect, it } from 'vitest'
import {
  hasProductionPagePermission,
  PRODUCTION_PAGE_KEYS,
} from './useProductionPermissions'

const baseUser = {
  id: 'user-1',
  name: '生产用户',
  role: 'user' as const,
  page_permissions: [],
}

describe('production page permissions', () => {
  it('keeps the complete production page key set stable', () => {
    expect(Object.values(PRODUCTION_PAGE_KEYS)).toHaveLength(24)
    expect(new Set(Object.values(PRODUCTION_PAGE_KEYS)).size).toBe(24)
  })

  it('denies every level when no authenticated user is available', () => {
    expect(hasProductionPagePermission(null, PRODUCTION_PAGE_KEYS.overview, 'access')).toBe(false)
    expect(hasProductionPagePermission(undefined, PRODUCTION_PAGE_KEYS.overview, 'query')).toBe(false)
    expect(hasProductionPagePermission(null, PRODUCTION_PAGE_KEYS.overview, 'operate', 'delete')).toBe(false)
  })

  it('requires the requested page level', () => {
    const user = {
      ...baseUser,
      page_permissions: [{
        page_key: PRODUCTION_PAGE_KEYS.process,
        module_code: 'production',
        permissions: ['access', 'query'] as const,
      }],
    }

    expect(hasProductionPagePermission(user, PRODUCTION_PAGE_KEYS.process, 'access')).toBe(true)
    expect(hasProductionPagePermission(user, PRODUCTION_PAGE_KEYS.process, 'query')).toBe(true)
    expect(hasProductionPagePermission(user, PRODUCTION_PAGE_KEYS.process, 'operate')).toBe(false)
  })

  it('requires operate plus the matching sensitive action', () => {
    const user = {
      ...baseUser,
      page_permissions: [{
        page_key: PRODUCTION_PAGE_KEYS.pressure,
        module_code: 'production',
        permissions: ['access', 'query', 'operate'] as const,
        sensitive_actions: ['approve', 'sensitive_export'],
      }],
    }

    expect(hasProductionPagePermission(user, PRODUCTION_PAGE_KEYS.pressure, 'operate', 'approve')).toBe(true)
    expect(hasProductionPagePermission(user, PRODUCTION_PAGE_KEYS.pressure, 'operate', 'delete')).toBe(false)
    expect(hasProductionPagePermission(user, PRODUCTION_PAGE_KEYS.pressure, 'operate', 'sensitive_export')).toBe(true)
  })

  it('grants every production page to an administrator', () => {
    const admin = { ...baseUser, role: 'admin' as const }
    for (const pageKey of Object.values(PRODUCTION_PAGE_KEYS)) {
      expect(hasProductionPagePermission(admin, pageKey, 'access')).toBe(true)
      expect(hasProductionPagePermission(admin, pageKey, 'operate', 'delete')).toBe(true)
    }
  })
})
