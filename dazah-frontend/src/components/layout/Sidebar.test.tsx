import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ModuleMenu, SubMenuItem } from '@/lib/menu-config'
import type { User } from '@/types/user'

const navigation = vi.hoisted(() => ({
  pathname: '/purchasing',
  push: vi.fn(),
  prefetch: vi.fn(),
  searchParams: new URLSearchParams(),
}))

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => ({ push: navigation.push, prefetch: navigation.prefetch }),
  useSearchParams: () => navigation.searchParams,
}))

vi.mock('@ant-design/icons', () => ({
  LoadingOutlined: () => createElement('span', { 'data-testid': 'loading-icon' }),
  SettingOutlined: () => null,
}))

vi.mock('antd', () => ({
  Menu: ({ items = [], onClick }: {
    items?: Array<{ key?: string | number; label?: ReactNode } | null>
    onClick?: (info: { key: string }) => void
  }) => createElement(
    'div',
    null,
    items.filter((item) => item?.key).map((item) => createElement(
      'button',
      {
        key: String(item?.key),
        'data-menu-key': String(item?.key),
        onClick: () => onClick?.({ key: String(item?.key) }),
      },
      item?.label,
    )),
  ),
}))

import { filterMenuItemsByRole, Sidebar } from './Sidebar'

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

const user: User = {
  id: 'test-user',
  name: '测试用户',
  role: 'user',
  status: 'active',
  auth_source: 'local',
  grant_version: 1,
  module_codes: ['procurement'],
  page_permissions: [],
  page_permission_rollouts: {},
}

afterEach(() => {
  navigation.pathname = '/purchasing'
  navigation.searchParams = new URLSearchParams()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe('Sidebar role filtering', () => {
  it('hides procurement settings from non-admin users', () => {
    expect(filterMenuItemsByRole(menuItems, false)).toEqual([menuItems[0]])
  })

  it('keeps procurement settings visible for administrators', () => {
    expect(filterMenuItemsByRole(menuItems, true)).toEqual(menuItems)
  })
})

describe('Sidebar navigation feedback', () => {
  it('shows a live pending message until the route changes', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    const modules: ModuleMenu[] = [{
      key: 'purchasing',
      moduleCode: 'procurement',
      label: '采购管理',
      icon: 'shopping',
      path: '/purchasing',
      children: menuItems,
    }]

    try {
      await act(async () => {
        root.render(createElement(Sidebar, { user, modules }))
      })

      const requestMenu = host.querySelector<HTMLButtonElement>('[data-menu-key="requests"]')
      expect(requestMenu).not.toBeNull()

      await act(async () => requestMenu?.click())

      expect(navigation.push).toHaveBeenCalledWith('/purchasing/request')
      expect(host.querySelector('[role="status"]')?.textContent).toContain('正在打开页面')
      expect(host.querySelector('[data-testid="loading-icon"]')).not.toBeNull()

      navigation.pathname = '/purchasing/request'
      await act(async () => {
        root.render(createElement(Sidebar, { user, modules }))
      })
      expect(host.querySelector('[role="status"]')).toBeNull()
    } finally {
      await act(async () => root.unmount())
    }
  })
})

describe('Sidebar parent navigation contract', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/components/layout/Sidebar.tsx'),
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
