import { describe, expect, it } from 'vitest'
import { getModuleByKey, moduleMenus } from '@/lib/menu-config'

// 2026-11 车间名称更正回归：201 二车间同时生产 MC（霉酚酸）与 DR（多拉菌素），
// 菜单不再出现「201三车间」。
describe('批次管理车间命名（MC/DR 同属 201 二车间）', () => {
  it('批次管理子菜单显示 201二车间（MC）与 201二车间（DR）', () => {
    const production = moduleMenus.find((menu) => menu.moduleCode === 'production')
    expect(production).toBeTruthy()
    const batches = production?.children?.find((item) => item.key === 'batches')
    expect(batches).toBeTruthy()
    const children = batches?.children ?? []
    const mc = children.find((item) => item.path === '/production/batches/workshop/201-2')
    const dr = children.find((item) => item.path === '/production/batches/workshop/201-3')
    expect(mc?.label).toBe('201二车间（MC）')
    expect(dr?.label).toBe('201二车间（DR）')
    expect(children.some((item) => item.label === '201三车间')).toBe(false)
  })

  it('模块菜单可通过 key 检索生产管理', () => {
    expect(getModuleByKey('production')).toBeTruthy()
  })
})
