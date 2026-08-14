import { describe, expect, it } from 'vitest'

import type { SubMenuItem } from '@/lib/menu-config'

import { filterMenuItemsByRole } from './Sidebar'

const menuItems: SubMenuItem[] = [
  { key: 'requests', label: '采购申请', path: '/purchasing/request' },
  {
    key: 'settings',
    label: '采购设置',
    path: '/purchasing/settings',
    placement: 'bottom',
    adminOnly: true,
  },
]

describe('Sidebar role filtering', () => {
  it('hides procurement settings from non-admin users', () => {
    expect(filterMenuItemsByRole(menuItems, false)).toEqual([menuItems[0]])
  })

  it('keeps procurement settings visible for administrators', () => {
    expect(filterMenuItemsByRole(menuItems, true)).toEqual(menuItems)
  })
})
