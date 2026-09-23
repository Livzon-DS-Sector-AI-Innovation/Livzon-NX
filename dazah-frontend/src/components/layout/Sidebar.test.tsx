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
  MenuFoldOutlined: () => null,
  MenuUnfoldOutlined: () => null,
  SettingOutlined: () => null,
}))

vi.mock('antd', () => ({
  Menu: ({ items = [], onClick, onOpenChange, openKeys = [], mode, triggerSubMenuAction }: {
    items?: Array<{
      key?: string | number
      label?: ReactNode
      children?: Array<{ key: string; label: ReactNode }>
      popupClassName?: string
      onTitleClick?: () => void
    } | null>
    onClick?: (info: { key: string }) => void
    onOpenChange?: (keys: string[]) => void
    openKeys?: string[]
    mode?: string
    triggerSubMenuAction?: string
  }) => createElement(
    'div',
    { 'data-menu-mode': mode, 'data-menu-trigger': triggerSubMenuAction },
    items.filter((item) => item?.key).flatMap((item) => {
      const key = String(item?.key)
      const isOpen = openKeys.includes(key)
      return [
        createElement('button', {
          key,
          'data-menu-key': key,
          'data-popup-class': item?.popupClassName,
          'aria-expanded': item?.children ? isOpen : undefined,
          onMouseEnter: () => item?.children && onOpenChange?.([...openKeys, key]),
          onClick: () => item?.children ? item.onTitleClick?.() : onClick?.({ key }),
        }, item?.label),
        ...(isOpen ? item?.children?.map((child) => createElement('button', {
          key: child.key,
          'data-menu-key': child.key,
          onClick: () => onClick?.({ key: child.key }),
        }, child.label)) ?? [] : []),
      ]
    }),
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
  window.localStorage.clear()
})

describe('Sidebar width control', () => {
  const modules: ModuleMenu[] = [{
    key: 'purchasing', moduleCode: 'procurement', label: '采购管理',
    icon: 'shopping', path: '/purchasing', children: menuItems,
  }]

  it('collapses to a narrow rail and restores the menu', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(Sidebar, { user, modules })))
      await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="收起侧边栏"]')?.click())
      expect(host.querySelector('aside')?.classList.contains('w-11')).toBe(true)
      expect(host.querySelector('[data-menu-key="requests"]')).toBeNull()
      expect(window.localStorage.getItem(`dazah-sidebar-collapsed:${user.id}`)).toBe('true')
      await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="展开侧边栏"]')?.click())
      expect(host.querySelector('[data-menu-key="requests"]')).not.toBeNull()
    } finally {
      await act(async () => root.unmount())
    }
  })
})

describe('Sidebar role filtering', () => {
  it('hides procurement settings from non-admin users', () => {
    expect(filterMenuItemsByRole(menuItems, false)).toEqual([menuItems[0]])
  })

  it('keeps procurement settings visible for administrators', () => {
    expect(filterMenuItemsByRole(menuItems, true)).toEqual(menuItems)
  })
})

describe('system settings entry', () => {
  const modules: ModuleMenu[] = [{
    key: 'purchasing', moduleCode: 'procurement', label: '采购管理',
    icon: 'shopping', path: '/purchasing', children: menuItems,
  }]

  it.each([
    { roles: ['super_admin'], visible: true },
    { roles: ['ordinary_admin'], visible: false },
  ])('shows settings only to system administrators: $roles', async ({ roles, visible }) => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(Sidebar, {
        user: { ...user, role: 'admin', roles }, modules,
      })))
      expect(host.textContent?.includes('系统设置')).toBe(visible)
    } finally {
      await act(async () => root.unmount())
    }
  })
})

describe('Sidebar navigation feedback', () => {
  it.each([
    { key: 'purchasing', label: '采购管理', path: '/purchasing', detailPath: '/purchasing/request' },
    { key: 'safety', label: '安全管理', path: '/safety', detailPath: '/safety/scheduled-tasks' },
  ])('returns from a $label page to its module entry via the title', async ({ key, label, path, detailPath }) => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    navigation.pathname = detailPath
    const modules: ModuleMenu[] = [{
      key, moduleCode: key, label, icon: 'module', path,
      children: [{ key: 'detail', label: '详情', path: detailPath }],
    }]
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(Sidebar, { user, modules })))
      const heading = host.querySelector('h2')
      const title = heading?.querySelector<HTMLAnchorElement>('a')
      expect(heading?.className).toContain('text-[18px]')
      expect(heading?.className).toContain('font-semibold')
      expect(title?.textContent).toBe(label)
      expect(title?.getAttribute('aria-label')).toBe(`返回${label}首页`)
      expect(title?.getAttribute('title')).toBe(`点击返回${label}首页`)
      expect(title?.getAttribute('href')).toBe(path)
      expect(title?.className).toContain('hover:underline')
      expect(title?.className).toContain('cursor-pointer')
      expect(title?.tabIndex).toBe(0)

      await act(async () => title?.focus())
      expect(document.activeElement).toBe(title)
      expect(navigation.prefetch).toHaveBeenCalledWith(path)

      await act(async () => title?.click())
      expect(navigation.push).toHaveBeenCalledWith(path)
      expect(host.querySelector('[role="status"]')?.textContent).toContain('正在打开页面')

      navigation.pathname = path
      await act(async () => root.render(createElement(Sidebar, { user, modules })))
      expect(host.querySelector('[role="status"]')).toBeNull()
      await act(async () => title?.click())
      expect(navigation.push).toHaveBeenCalledTimes(1)
    } finally {
      await act(async () => root.unmount())
    }
  })

  it('shows a live pending message until the route changes', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    navigation.searchParams = new URLSearchParams('auth_token=preview')
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
      const status = host.querySelector<HTMLElement>('[role="status"]')
      expect(status?.textContent).toContain('正在打开页面')
      expect(status?.closest('aside')).toBeNull()
      expect(status?.classList.contains('fixed')).toBe(true)
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

describe('Sidebar flyout menu', () => {
  const modules: ModuleMenu[] = [{
    key: 'purchasing', moduleCode: 'procurement', label: '采购管理',
    icon: 'shopping', path: '/purchasing', children: [{
      key: 'orders', label: '订单管理', path: '/purchasing/orders', children: [
        { key: 'order-list', label: '订单列表', path: '/purchasing/orders' },
      ],
    }],
  }]

  it('opens to the right on hover or click and closes after navigation', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(Sidebar, { user, modules })))
      expect(host.querySelector('[data-menu-mode="vertical"][data-menu-trigger="hover"]')).not.toBeNull()
      const parent = host.querySelector<HTMLButtonElement>('[data-menu-key="orders"]')
      expect(parent?.dataset.popupClass).toBe('sidebar-submenu-popup')
      expect(parent?.getAttribute('aria-expanded')).toBe('false')

      await act(async () => parent?.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })))
      expect(parent?.getAttribute('aria-expanded')).toBe('true')
      await act(async () => parent?.click())
      expect(parent?.getAttribute('aria-expanded')).toBe('false')
      await act(async () => parent?.click())
      expect(parent?.getAttribute('aria-expanded')).toBe('true')

      await act(async () => host.querySelector<HTMLButtonElement>('[data-menu-key="order-list"]')?.click())
      expect(navigation.push).toHaveBeenCalledWith('/purchasing/orders')
      expect(parent?.getAttribute('aria-expanded')).toBe('false')

      await act(async () => parent?.click())
      expect(parent?.getAttribute('aria-expanded')).toBe('true')
      navigation.pathname = '/purchasing/orders'
      await act(async () => root.render(createElement(Sidebar, { user, modules })))
      expect(parent?.getAttribute('aria-expanded')).toBe('false')
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

describe('Sidebar dashboard entries', () => {
  const modules: ModuleMenu[] = [{
    key: 'quality', moduleCode: 'quality', label: '质量管理', icon: 'quality', path: '/quality',
    children: [
      { key: 'deviations', label: '偏差管理', path: '/quality/deviations', dashboard: true, children: [
        { key: 'deviation-ledger', label: '偏差台账', path: '/quality/deviations/ledger' },
      ] },
      { key: 'inspection', label: '质量检验', path: '/quality/inspection', children: [
        { key: 'items', label: '物品管理', path: '/quality/inspection/items' },
      ] },
    ],
  }]

  it('keeps dashboard labels plain while preserving direct navigation and group expansion', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    navigation.pathname = '/quality'
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(Sidebar, { user, modules })))
      const dashboard = host.querySelector<HTMLElement>('[aria-label="打开偏差管理仪表盘"]')
      expect(dashboard?.textContent).toBe('偏差管理')
      await act(async () => dashboard?.click())
      expect(navigation.push).toHaveBeenCalledWith('/quality/deviations')

      const inspection = host.querySelector<HTMLButtonElement>('[data-menu-key="inspection"]')
      expect(inspection?.textContent).not.toContain('仪表盘')
      await act(async () => inspection?.click())
      expect(inspection?.getAttribute('aria-expanded')).toBe('true')
      expect(navigation.push).not.toHaveBeenCalledWith('/quality/inspection')
    } finally {
      await act(async () => root.unmount())
    }
  })
})
