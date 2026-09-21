/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ModuleMenu } from '@/lib/menu-config'
import type { User } from '@/types/user'

const navigation = vi.hoisted(() => ({
  pathname: '/production',
  searchParams: new URLSearchParams('auth_token=preview'),
}))

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => navigation.searchParams,
}))

vi.mock('next/link', () => ({
  default: ({ href, children, onClick, prefetch: _prefetch, ...props }: {
    href: string
    children: ReactNode
    onClick?: (event: MouseEvent) => void
    prefetch?: boolean
  }) => {
    void _prefetch
    return createElement('a', {
      ...props,
      href,
      onClick: (event: MouseEvent) => { event.preventDefault(); onClick?.(event) },
    }, children)
  },
}))

vi.mock('antd', () => ({ Avatar: () => createElement('span', null, '头像') }))
vi.mock('@ant-design/icons', () => ({
  LoadingOutlined: () => createElement('span', { 'data-loading': 'true' }),
  UserOutlined: () => null,
}))
vi.mock('@/components/icons', () => ({
  ModuleIcon: () => createElement('span', { 'data-module-icon': 'true' }),
  SearchIcon: () => null,
  BellIcon: () => null,
}))

import { TopNav } from './TopNav'

const user: User = {
  id: 'test-user', name: '测试用户', role: 'admin', status: 'active',
  auth_source: 'local', grant_version: 1, module_codes: [], page_permissions: [],
  page_permission_rollouts: {},
}
const modules: ModuleMenu[] = [
  { key: 'production', moduleCode: 'production', label: '生产管理', icon: 'factory', path: '/production', children: [] },
  { key: 'quality', moduleCode: 'quality', label: '质量管理', icon: 'quality', path: '/quality', children: [] },
]

afterEach(() => {
  navigation.pathname = '/production'
  navigation.searchParams = new URLSearchParams('auth_token=preview')
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

describe('TopNav module feedback', () => {
  it('marks the current module and shows pending feedback until navigation completes', async () => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    try {
      await act(async () => root.render(createElement(TopNav, { user, modules })))
      const production = host.querySelector<HTMLAnchorElement>('a[href^="/production"]')
      const quality = host.querySelector<HTMLAnchorElement>('a[href^="/quality"]')
      expect(production?.getAttribute('aria-current')).toBe('location')
      expect(quality?.getAttribute('href')).toBe('/quality?auth_token=preview')
      expect(quality?.hasAttribute('data-pending')).toBe(false)

      await act(async () => quality?.dispatchEvent(new MouseEvent('click', { bubbles: true, ctrlKey: true })))
      expect(quality?.hasAttribute('data-pending')).toBe(false)

      await act(async () => quality?.click())
      expect(quality?.getAttribute('data-pending')).toBe('true')
      expect(quality?.querySelector('[data-loading]')).not.toBeNull()

      navigation.pathname = '/quality'
      await act(async () => root.render(createElement(TopNav, { user, modules })))
      expect(quality?.getAttribute('aria-current')).toBe('location')
      expect(quality?.hasAttribute('data-pending')).toBe(false)
    } finally {
      await act(async () => root.unmount())
    }
  })
})
