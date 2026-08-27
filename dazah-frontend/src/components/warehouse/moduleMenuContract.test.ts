import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('warehouse migrated menu contract', () => {
  it('exposes materials, hardware, product ledger and AI analysis', () => {
    const warehouse = moduleMenus.find((menu) => menu.moduleCode === 'warehouse')
    const paths = JSON.stringify(warehouse?.children ?? [])

    expect(paths).toContain('/warehouse/materials/dashboard')
    expect(paths).toContain('/warehouse/hardware/dashboard')
    expect(paths).toContain('/warehouse/product/dashboard')
    expect(paths).toContain('/warehouse/ai-analysis')
  })
})
