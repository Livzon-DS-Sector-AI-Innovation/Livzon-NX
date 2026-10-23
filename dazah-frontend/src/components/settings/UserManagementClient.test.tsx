/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntdApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getUsers: vi.fn(),
  createUser: vi.fn(),
  resetUserPassword: vi.fn(),
  syncFeishuUsers: vi.fn(),
  updateUser: vi.fn(),
}))
const navigation = vi.hoisted(() => ({ query: '', replace: vi.fn() }))

vi.mock('@/actions/users', () => mocks)
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
  usePathname: () => '/settings',
  useRouter: () => ({ replace: navigation.replace }),
}))

import UserManagementClient from './UserManagementClient'

describe('UserManagementClient permission entry', () => {
  let host: HTMLDivElement

  beforeEach(() => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    navigation.query = ''
    navigation.replace.mockReset()
    host = document.createElement('div')
    document.body.append(host)
    mocks.getUsers.mockResolvedValue({
      items: [{
        id: 'user-1',
        name: '测试用户',
        username: 'tester',
        role: 'user',
        status: 'active',
        auth_source: 'local',
      }],
      total: 1,
    })
    mocks.syncFeishuUsers.mockResolvedValue({
      status: 'ok',
      message: '同步完成：用户 1 名。',
    })
  })

  afterEach(() => {
    host.remove()
    navigation.query = ''
    navigation.replace.mockReset()
    vi.clearAllMocks()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('removes the page permission entry after it is migrated to user roles', async () => {
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    expect(host.textContent).toContain('测试用户')
    expect(host.textContent).toContain('同步飞书用户')
    expect(host.textContent).not.toContain('模块权限')
    expect(host.textContent).not.toContain('页面权限')

    await act(async () => root.unmount())
  })

  it.each([
    ['admin', ['ordinary_admin'], '普通管理员', 'ant-tag-blue'],
    ['admin', ['super_admin'], '系统管理员', 'ant-tag-purple'],
    ['admin', ['ordinary_admin', 'super_admin'], '系统管理员', 'ant-tag-purple'],
    ['admin', [], '系统管理员', 'ant-tag-purple'],
    ['user', [], '普通用户', 'ant-tag-green'],
  ])('labels user role %s with codes %s and its identity color', async (role, roles, label, colorClass) => {
    mocks.getUsers.mockResolvedValue({
      items: [{
        id: 'ordinary-1', name: '普通管理员甲', username: 'ordinary',
        role, roles, status: 'active', auth_source: 'local',
      }],
      total: 1,
    })
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(host.textContent).toContain('普通管理员甲')
    const roleTag = host.querySelector('tbody td:nth-child(2) .ant-tag')!
    expect(roleTag.textContent).toBe(label)
    expect(roleTag.classList.contains(colorClass)).toBe(true)
    expect(host.querySelector('h3')?.textContent).toBe('用户列表')
    await act(async () => root.unmount())
  })

  it('restores a filtered server-side page from the URL', async () => {
    navigation.query = 'tab=users&q=alice&page=2&size=20'
    mocks.getUsers.mockResolvedValue({
      items: Array.from({ length: 10 }, (_, index) => ({
        id: `user-${index + 21}`,
        name: `姓名${index + 21}`,
        username: `account-${index + 21}`,
        role: 'user',
        status: 'active',
        auth_source: 'local',
      })),
      total: 31,
      offset: 20,
      limit: 20,
    })
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    expect(mocks.getUsers).toHaveBeenCalledWith(expect.objectContaining({
      keyword: 'alice', offset: 20, limit: 20,
    }))
    expect(host.querySelector<HTMLInputElement>('.ant-input-search input')?.value).toBe('alice')
    expect(host.querySelector('.ant-pagination-item-active')?.textContent).toContain('2')
    expect(host.textContent).toContain('姓名21')
    expect(host.textContent).toContain('共 31 个账号')

    await act(async () => host.querySelector<HTMLElement>('.ant-pagination-item-1')?.click())
    expect(navigation.replace).toHaveBeenCalledWith(
      '/settings?tab=users&q=alice&page=1&size=20',
      { scroll: false },
    )

    await act(async () => root.unmount())
  })

  it('requests the last page instead of slicing a full user list on the client', async () => {
    navigation.query = 'tab=users&page=11&page_size=10'
    mocks.getUsers.mockResolvedValue({
      items: [{
        id: 'user-101', name: '第101人', username: 'account-101',
        role: 'user', status: 'active', auth_source: 'local',
      }],
      total: 101,
      offset: 100,
      limit: 10,
    })
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    expect(mocks.getUsers).toHaveBeenCalledWith(expect.objectContaining({ offset: 100, limit: 10 }))
    expect(host.textContent).toContain('第101人')
    expect(host.textContent).toContain('共 101 个账号')

    await act(async () => root.unmount())
  })

  it('does not expose or submit role changes from the profile editor', async () => {
    mocks.updateUser.mockResolvedValue({})
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    await act(async () => host.querySelector<HTMLButtonElement>('tbody .ant-btn')?.click())
    const modal = document.querySelector<HTMLElement>('.ant-modal')
    expect(modal?.textContent).toContain('编辑用户')
    expect(modal?.textContent).not.toContain('初始角色')

    const ok = modal?.querySelector<HTMLButtonElement>('.ant-modal-footer .ant-btn-primary')
    await act(async () => ok?.click())
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    expect(mocks.updateUser).toHaveBeenCalledTimes(1)
    expect(mocks.updateUser.mock.calls[0][1]).not.toHaveProperty('role')

    await act(async () => root.unmount())
  })

  it('shows a retry action when the user list fails to load', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.getUsers.mockRejectedValueOnce(new Error('offline'))
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    expect(host.textContent).toContain('用户列表加载失败')
    const retry = host.querySelector<HTMLButtonElement>('.ant-alert-actions button')
    expect(retry).not.toBeNull()
    await act(async () => retry?.click())
    expect(mocks.getUsers).toHaveBeenCalledTimes(2)
    expect(host.textContent).not.toContain('用户列表加载失败')

    await act(async () => root.unmount())
  })

  it('writes submitted searches to the user-list URL', async () => {
    navigation.query = 'tab=users'
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    const input = host.querySelector<HTMLInputElement>('.ant-input-search input')
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
    await act(async () => {
      if (input) setValue?.call(input, '张超')
      input?.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const searchButton = host.querySelector<HTMLButtonElement>('.ant-input-search-btn')
    expect(searchButton).not.toBeNull()
    await act(async () => searchButton?.click())
    expect(navigation.replace).toHaveBeenCalledWith(
      '/settings?tab=users&q=%E5%BC%A0%E8%B6%85',
      { scroll: false },
    )

    await act(async () => root.unmount())
  })

  it('requires confirmation before disabling a user from the compact actions menu', async () => {
    mocks.updateUser.mockResolvedValue({})
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="测试用户的更多操作"]')?.click())
    const disable = [...document.body.querySelectorAll<HTMLElement>('[role="menuitem"]')]
      .find((item) => item.textContent?.includes('禁用用户'))
    expect(disable).toBeDefined()
    await act(async () => disable?.click())
    expect(mocks.updateUser).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('禁用后，该用户将无法继续登录')

    const confirm = document.body.querySelector<HTMLButtonElement>('.ant-modal-confirm-btns .ant-btn-primary')
    expect(confirm).not.toBeNull()
    await act(async () => confirm?.click())
    expect(mocks.updateUser).toHaveBeenCalledWith('user-1', { status: 'disabled' })

    await act(async () => root.unmount())
  })
})
