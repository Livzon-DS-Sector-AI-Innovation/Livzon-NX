/* @vitest-environment happy-dom */

import { act, createElement, forwardRef, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ModuleMenu } from '@/lib/menu-config'
import type { User } from '@/types/user'

const navigation = vi.hoisted(() => ({
  pathname: '/production',
  searchParams: new URLSearchParams('auth_token=preview'),
  push: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => navigation.searchParams,
  useRouter: () => ({ push: navigation.push }),
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
  Avatar: () => createElement('span', null, '头像'),
  Input: forwardRef<HTMLInputElement, {
    onChange: (event: Event) => void
    onPressEnter: () => void
  }>(function MockInput({ onChange, onPressEnter, ...props }, ref) {
    return createElement('input', {
      ...props,
      ref,
      onChange,
      onKeyDown: (event: KeyboardEvent) => { if (event.key === 'Enter') onPressEnter() },
    })
  }),
}))
vi.mock('@ant-design/icons', () => ({
  LoadingOutlined: () => createElement('span', { 'data-loading': 'true' }),
  UserOutlined: () => null,
}))
vi.mock('@/components/icons', () => ({
  ModuleIcon: () => createElement('span', { 'data-module-icon': 'true' }),
  SearchIcon: () => null,
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
  navigation.push.mockClear()
  vi.unstubAllGlobals()
  document.body.replaceChildren()
})

it('searches only queryable menu pages and navigates with the preview token', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const restrictedUser: User = {
    ...user,
    role: 'user',
    page_permissions: [{
      page_key: 'production:pressure', module_code: 'production', permissions: ['access', 'query'],
      sensitive_actions: [], data_scope: { scope_type: 'all', department_ids: [] }, source: 'user',
    }],
  }
  const searchableModules: ModuleMenu[] = [{
    ...modules[0],
    children: [
      { key: 'pressure', label: '压差统计', path: '/production/pressure' },
      { key: 'label-verification', label: '标签复核', path: '/production/label-verification' },
      { key: 'disabled', label: '禁用页面', path: '/production/disabled', disabled: true },
      { key: 'admin', label: '管理员页面', path: '/production/admin', adminOnly: true },
    ],
  }]
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(createElement(TopNav, { user: restrictedUser, modules: searchableModules })))
    expect(host.querySelector('button[aria-label="通知"]')).toBeNull()
    const input = host.querySelector<HTMLInputElement>('input[aria-label="搜索页面名称"]')
    expect(input).not.toBeNull()
    expect(host.querySelector('button[aria-label="搜索"]')).toBeNull()
    expect(host.querySelector('[role="region"]')).toBeNull()
    await act(async () => input?.focus())
    expect(document.activeElement).toBe(input)
    expect(host.querySelector('[role="dialog"]')).toBeNull()
    expect(host.querySelector('[role="region"]')).not.toBeNull()
    await act(async () => {
      if (input) {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '生产')
        input.dispatchEvent(new Event('input', { bubbles: true }))
      }
    })
    expect(host.querySelectorAll('[role="region"] a')).toHaveLength(1)
    expect(host.querySelector<HTMLAnchorElement>('[role="region"] a')?.getAttribute('href'))
      .toBe('/production/pressure?auth_token=preview')
    expect(host.textContent).toContain('压差统计')
    expect(host.textContent).not.toContain('标签复核')
    expect(host.textContent).not.toContain('禁用页面')
    expect(host.textContent).not.toContain('管理员页面')

    await act(async () => input?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
    expect(navigation.push).toHaveBeenCalledWith('/production/pressure?auth_token=preview')
    expect(host.querySelector('[role="region"]')).toBeNull()
  } finally {
    await act(async () => root.unmount())
  }
})

it('keeps the search field visible while dismissing results on Escape or outside pointer down', async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(createElement(TopNav, { user, modules })))
    const input = host.querySelector<HTMLInputElement>('input[aria-label="搜索页面名称"]')!
    await act(async () => input.focus())
    expect(host.querySelector('[role="region"]')).not.toBeNull()
    await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    expect(host.querySelector('[role="region"]')).toBeNull()
    expect(host.querySelector('input[aria-label="搜索页面名称"]')).toBe(input)

    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '质量')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(host.querySelector('[role="region"]')).not.toBeNull()
    await act(async () => document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })))
    expect(host.querySelector('[role="region"]')).toBeNull()
    expect(host.querySelector('input[aria-label="搜索页面名称"]')).toBe(input)
  } finally {
    await act(async () => root.unmount())
  }
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
