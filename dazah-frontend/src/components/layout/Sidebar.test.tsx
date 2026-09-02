import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
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

describe('Sidebar parent navigation contract', () => {
  const source = readFileSync(
    fileURLToPath(new URL('./Sidebar.tsx', import.meta.url)),
    'utf8',
  )

  it('routes parent labels with a path without toggling collapse', () => {
    // 带 path 的父级（如仓储三个仪表盘入口）点击标签导航到落地页，
    // 且必须阻止事件冒泡以免同时触发展开/收起
    expect(source).toContain('onParentNavigate')
    expect(source).toContain('event.stopPropagation()')
    expect(source).toContain('onParentNavigate?.(item.path)')
  })
})
