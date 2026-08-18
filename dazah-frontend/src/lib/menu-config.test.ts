import { describe, expect, it } from 'vitest'
import { moduleMenus } from './menu-config'

describe('procurement menu structure', () => {
  it('adds the new request categories and nests labor categories', () => {
    const purchasing = moduleMenus.find((menu) => menu.key === 'purchasing')
    const request = purchasing?.children.find((item) => item.key === 'request')

    expect(request?.children?.map((item) => item.key)).toEqual(
      expect.arrayContaining([
        'request-advertising-printing',
        'request-fire',
        'request-packaging',
        'request-labor',
        'request-urgent',
      ])
    )

    const labor = request?.children?.find((item) => item.key === 'request-labor')
    expect(labor?.children?.map((item) => item.key)).toEqual([
      'request-labor-special',
      'request-labor-miscellaneous',
    ])
    expect(request?.children?.some((item) => item.key === 'request-labor-protection')).toBe(false)
  })

  it('keeps approval labor categories under a collapsible labor parent', () => {
    const purchasing = moduleMenus.find((menu) => menu.key === 'purchasing')
    const approval = purchasing?.children.find((item) => item.key === 'approval')
    const labor = approval?.children?.find((item) => item.key === 'approval-labor')
    const advertisingPrinting = approval?.children?.find(
      (item) => item.key === 'approval-advertising-printing'
    )
    const urgent = approval?.children?.find((item) => item.key === 'approval-urgent')
    const hardware = approval?.children?.find((item) => item.key === 'approval-hardware')
    const electrical = approval?.children?.find((item) => item.key === 'approval-electrical')

    expect(advertisingPrinting?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/advertising-printing/department-head',
      '/purchasing/approval/advertising-printing/responsible-leader',
      '/purchasing/approval/advertising-printing/supervising-leader',
    ])
    expect(urgent?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/urgent/hardware-warehouse',
      '/purchasing/approval/urgent/department-head',
      '/purchasing/approval/urgent/responsible-leader',
      '/purchasing/approval/urgent/supervising-leader',
      '/purchasing/approval/urgent/finance-director',
      '/purchasing/approval/urgent/general-manager',
    ])
    expect(hardware?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/hardware/hardware-warehouse',
      '/purchasing/approval/hardware/department-head',
      '/purchasing/approval/hardware/responsible-leader',
      '/purchasing/approval/hardware/supervising-leader',
      '/purchasing/approval/hardware/general-manager',
    ])
    expect(electrical?.children?.map((item) => item.path)).toEqual([
      '/purchasing/approval/electrical/hardware-warehouse',
      '/purchasing/approval/electrical/equipment-power',
      '/purchasing/approval/electrical/department-head',
      '/purchasing/approval/electrical/responsible-leader',
      '/purchasing/approval/electrical/supervising-leader',
    ])
    expect(labor?.children?.map((item) => item.key)).toEqual([
      'approval-labor-special',
      'approval-labor-miscellaneous',
    ])
    expect(labor?.children?.[0]?.children?.[0]?.path).toBe(
      '/purchasing/approval/labor-special/safety-officer'
    )
  })

  it('exposes procurement settings only as an admin menu item', () => {
    const settings = moduleMenus
      .find((menu) => menu.key === 'purchasing')
      ?.children.find((item) => item.key === 'settings')

    expect(settings).toMatchObject({
      label: '采购设置',
      path: '/purchasing/settings',
      adminOnly: true,
    })
  })

  it('exposes the material code library to procurement users', () => {
    const materialLibrary = moduleMenus
      .find((menu) => menu.key === 'purchasing')
      ?.children.find((item) => item.key === 'material-library')

    expect(materialLibrary).toMatchObject({
      label: '物料编码库',
      path: '/purchasing/material-library',
    })
    expect(materialLibrary?.adminOnly).toBeUndefined()
  })
})
