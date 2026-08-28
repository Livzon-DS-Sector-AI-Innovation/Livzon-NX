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

  it('removes the retired warehouse sidebar entry points', () => {
    const warehouse = moduleMenus.find((menu) => menu.moduleCode === 'warehouse')
    const topLevelItems = warehouse?.children ?? []

    expect(topLevelItems.map((item) => item.key)).not.toEqual(
      expect.arrayContaining(['raw-material', 'packaging', 'product', 'feishu-config'])
    )
    expect(topLevelItems.map((item) => item.label)).not.toEqual(
      expect.arrayContaining(['成品', '原辅料及包材', '五金', '飞书设置', '飞书配置'])
    )
  })
})
