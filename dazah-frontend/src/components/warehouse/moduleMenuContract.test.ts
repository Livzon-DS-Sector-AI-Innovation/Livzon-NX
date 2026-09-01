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
      expect.arrayContaining(['raw-material', 'packaging', 'product'])
    )
    expect(topLevelItems.map((item) => item.label)).not.toEqual(
      expect.arrayContaining(['成品', '原辅料及包材', '五金'])
    )
  })

  it('exposes product details subgroup and the merged settings entry', () => {
    const warehouse = moduleMenus.find((menu) => menu.moduleCode === 'warehouse')
    const topLevelItems = warehouse?.children ?? []

    // 数据台账叶子必须带与后端 FEISHU_WAREHOUSE_MATERIAL_PAGES 一致的裸 key
    const materials = topLevelItems.find((item) => item.key === 'materials')
    const rawSummary = materials?.children?.find((item) => item.key === 'raw-summary')
    expect(rawSummary?.feishuPageKey).toBe('raw-summary')

    const hardware = topLevelItems.find((item) => item.key === 'hardware')
    // 菜单 key 带 hardware- 前缀（hardware- + pageKey），但 feishuPageKey 用裸 key
    const hardwareChild = hardware?.children?.find(
      (item) => item.key === 'hardware-hardware-summary',
    )
    expect(hardwareChild?.feishuPageKey).toBe('hardware-summary')

    // 产品明细子组：10 个产品明细页（页面路由已存在，菜单需可达）
    const productInventory = topLevelItems.find((item) => item.key === 'product-inventory')
    const details = productInventory?.children?.find((item) => item.key === 'product-details')
    expect(details?.children).toHaveLength(10)
    expect(details?.children?.[0]?.path).toBe('/warehouse/product/details/l-phenylalanine')

    // 设置页合并：唯一「仓储设置」入口（页面映射 + 飞书数据源二合一），
    // feishu-config 旧路由保留重定向、不再单独出现在菜单
    const settings = topLevelItems.find((item) => item.key === 'warehouse-settings')
    expect(settings?.path).toBe('/warehouse/settings')
    expect(topLevelItems.some((item) => item.key === 'warehouse-feishu-config')).toBe(false)

    // 非数据页（AI 分析/设置）显式不映射
    expect(topLevelItems.find((item) => item.key === 'ai-analysis')?.feishuPageKey).toBe('')
    expect(settings?.feishuPageKey).toBe('')
  })
})
