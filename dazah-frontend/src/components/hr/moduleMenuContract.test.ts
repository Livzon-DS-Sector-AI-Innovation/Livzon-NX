import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('HR migrated menu contract', () => {
  it('exposes employees, contracts, training and settings', () => {
    const hr = moduleMenus.find((menu) => menu.moduleCode === 'hr')
    const paths = JSON.stringify(hr?.children ?? [])

    expect(paths).toContain('/hr/employee-management')
    expect(paths).toContain('/hr/contracts')
    expect(paths).toContain('/hr/training')
    expect(paths).toContain('/hr/settings/feishu')
  })
})
