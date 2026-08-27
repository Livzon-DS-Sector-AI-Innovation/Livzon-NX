import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('quality migrated menu contract', () => {
  it('matches the quality landing entry order and keeps existing submenu groups', () => {
    const quality = moduleMenus.find((menu) => menu.moduleCode === 'quality')
    const children = quality?.children ?? []

    expect(children.map((item) => item.key)).toEqual([
      'feishu-settings',
      'documents',
      'deviations',
      'capas',
      'complaints',
      'department-contacts',
      'inspection',
      'oos-oot',
      'product-quality',
      'return-recalls',
      'suppliers',
      'change',
      'validation',
    ])
    expect(children.find((item) => item.key === 'product-quality')).toMatchObject({
      label: '产品质量回顾',
      path: '/quality/product-quality',
    })
    expect(children.find((item) => item.key === 'feishu-settings')?.placement).toBeUndefined()
    expect(children.some((item) => item.key === 'cpv' || item.key === 'feishu-data')).toBe(false)

    expect(children.find((item) => item.key === 'deviations')?.children?.map((item) => item.key)).toEqual([
      'deviation-records',
      'deviation-investigations',
      'deviation-ledger',
    ])
    expect(children.find((item) => item.key === 'capas')?.children?.map((item) => item.key)).toEqual([
      'capa-ledger',
      'capa-plans',
    ])
    expect(children.find((item) => item.key === 'inspection')?.children?.map((item) => item.key)).toEqual([
      'inspection-items',
      'inspection-instruments',
      'inspection-finished',
      'inspection-solid',
      'inspection-liquid',
    ])
    expect(children.find((item) => item.key === 'oos-oot')?.children?.map((item) => item.key)).toEqual([
      'oos-oot-report-records',
      'oos-oot-investigation-push',
      'oos-ledger',
      'oot-ledger',
      'oot-limits',
      'product-departments',
    ])
    expect(children.find((item) => item.key === 'return-recalls')?.children?.map((item) => item.key)).toEqual([
      'return-application',
      'return-ledger',
    ])
    expect(children.find((item) => item.key === 'suppliers')?.children?.map((item) => item.key)).toEqual([
      'supplier-qualification',
    ])
    expect(children.find((item) => item.key === 'validation')?.children?.map((item) => item.key)).toEqual([
      'validation-plans',
      'equipment-qualification',
      'process-validation',
      'cleaning-validation',
      'other-validations',
    ])
    expect(children.find((item) => item.key === 'change')?.children?.map((item) => item.key)).toEqual([
      'change-ledger',
      'file-change-ledger',
      'change-action-plans',
    ])
  })
})
