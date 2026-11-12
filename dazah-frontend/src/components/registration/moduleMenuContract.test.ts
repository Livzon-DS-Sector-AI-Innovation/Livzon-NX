import { describe, expect, it } from 'vitest'
import { moduleMenus } from '@/lib/menu-config'

describe('registration migrated menu contract', () => {
  it('identifies first-level routes that open a dashboard', () => {
    const registration = moduleMenus.find((menu) => menu.moduleCode === 'registration')
    expect(registration?.children.filter((item) => item.dashboard).map((item) => item.path)).toEqual([
      '/registration/project',
      '/registration/certificate-management',
      '/registration/fees',
    ])
  })

  it('lists the top-level registration menu entries in order', () => {
    const registration = moduleMenus.find((menu) => menu.moduleCode === 'registration')

    expect(registration?.children.map((item) => item.label)).toEqual([
      '申报项目',
      '授权书管理',
      '证书管理',
      '法规跟踪',
      '注册费用',
      '注册知识库',
      '申报资料撰写',
      '注册设置',
    ])
    expect(registration?.children.find((item) => item.key === 'dossier-writer')?.path)
      .toBe('/registration/dossier-writer')
  })

  it('keeps the existing secondary menu trees', () => {
    const registration = moduleMenus.find((menu) => menu.moduleCode === 'registration')
    const project = registration?.children.find((item) => item.key === 'project')
    const certificates = registration?.children.find((item) => item.key === 'certificate-management')
    const fees = registration?.children.find((item) => item.key === 'fees')

    expect(project?.children?.map((item) => item.key)).toEqual([
      'project-ledger',
      'declaration-progress',
    ])
    expect(certificates?.children?.map((item) => item.key)).toEqual([
      'international-registration',
      'domestic-registration',
      'domestic-gmp',
      'international-gmp',
    ])
    expect(fees?.children?.map((item) => item.key)).toEqual([
      'fee-ledger',
      'inspection-contacts',
    ])
  })
})
