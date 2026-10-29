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

vi.mock('antd', () => ({
  Avatar: ({ src, onError }: { src?: string; onError?: () => boolean }) =>
    createElement('span', { 'data-avatar': true }, '头像',
      src ? createElement('img', { src, alt: '用户头像', onError }) : null),
}))
vi.mock('@ant-design/icons', () => ({
  LoadingOutlined: () => createElement('span', { 'data-loading': 'true' }),
  UserOutlined: () => null,
}))
vi.mock('@/components/icons', () => ({
  ModuleIcon: () => createElement('span', { 'data-module-icon': 'true' }),
}))

import { TopNav } from './TopNav'

vi.mock('./ToolbarActions', () => ({ ToolbarActions: () => createElement('div', null,
  createElement('button', null, '反馈'), createElement('button', null, '我的待办'),
) }))

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
  window.localStorage.clear()
  document.body.replaceChildren()
})

it('renders module navigation and account actions without page search', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const getItem = vi.spyOn(Storage.prototype, 'getItem')
  const setItem = vi.spyOn(Storage.prototype, 'setItem')
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(createElement(TopNav, { user, modules })))
    expect(host.querySelector('input')).toBeNull()
    expect(host.querySelector('[aria-label="页面搜索结果"]')).toBeNull()
    expect(host.textContent).not.toContain('常搜索页面')
    expect([...host.querySelectorAll('nav[aria-label="业务模块"] a')].map((link) => link.getAttribute('href')))
      .toEqual(['/production', '/quality'])
    expect(host.textContent).toContain('测试用户')
    expect(host.textContent?.indexOf('我的待办')).toBeLessThan(host.textContent?.indexOf('头像') || 0)
    expect(host.textContent).toContain('反馈')
    expect(host.textContent).not.toContain('外观')
    expect(host.querySelector('a[href="/auth/logout"]')?.textContent).toBe('退出')
    expect(getItem).not.toHaveBeenCalled()
    expect(setItem).not.toHaveBeenCalled()
  } finally {
    await act(async () => root.unmount())
    getItem.mockRestore()
    setItem.mockRestore()
  }
})

describe('TopNav module feedback', () => {
  it('falls back after an avatar error and retries when the avatar URL changes', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    const initialUser = { ...user, avatar_url: 'https://avatar.example/old.png' }
    try {
      await act(async () => root.render(createElement(TopNav, { user: initialUser, modules })))
      const image = host.querySelector('img')
      expect(image?.getAttribute('src')).toBe(initialUser.avatar_url)
      await act(async () => image?.dispatchEvent(new Event('error')))
      expect(host.querySelector('img')).toBeNull()
      expect(host.querySelector('[data-avatar]')?.textContent).toBe('头像')
      expect(host.textContent).toContain('测试用户')

      await act(async () => root.render(createElement(TopNav, { user: { ...initialUser }, modules })))
      expect(host.querySelector('img')).toBeNull()

      const updatedUser = { ...user, avatar_url: 'https://avatar.example/new.png' }
      await act(async () => root.render(createElement(TopNav, { user: updatedUser, modules })))
      expect(host.querySelector('img')?.getAttribute('src')).toBe(updatedUser.avatar_url)
      await act(async () => host.querySelector('img')?.dispatchEvent(new Event('error')))
      expect(host.querySelector('img')).toBeNull()

      await act(async () => root.render(createElement(TopNav, { user, modules })))
      expect(host.querySelector('img')).toBeNull()
      expect(host.querySelector('a[href="/auth/logout"]')?.textContent).toBe('退出')
    } finally {
      await act(async () => root.unmount())
    }
  })

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
      expect(quality?.getAttribute('href')).toBe('/quality')
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
