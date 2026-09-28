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
const navigation = vi.hoisted(() => ({ query: '' }))

vi.mock('@/actions/users', () => mocks)
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
}))

import UserManagementClient from './UserManagementClient'

describe('UserManagementClient permission entry', () => {
  let host: HTMLDivElement

  beforeEach(() => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
    navigation.query = ''
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

  it('labels an assigned ordinary administrator accurately', async () => {
    mocks.getUsers.mockResolvedValue({
      items: [{
        id: 'ordinary-1', name: '普通管理员甲', username: 'ordinary',
        role: 'admin', roles: ['ordinary_admin'], status: 'active', auth_source: 'local',
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
    expect(host.textContent).toContain('普通管理员')
    expect(host.querySelector('h3')?.textContent).toBe('用户列表')
    await act(async () => root.unmount())
  })

  it('restores a filtered page from the URL', async () => {
    navigation.query = 'tab=users&q=alice&page=2&size=20'
    mocks.getUsers.mockResolvedValue({
      items: Array.from({ length: 31 }, (_, index) => ({
        id: `user-${index + 1}`,
        name: `姓名${index + 1}`,
        username: `account-${index + 1}`,
        role: 'user',
        status: 'active',
        auth_source: 'local',
      })),
      total: 31,
    })
    const root = createRoot(host)
    await act(async () => {
      root.render(createElement(AntdApp, null, createElement(UserManagementClient)))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

    expect(mocks.getUsers).toHaveBeenCalledWith({ keyword: 'alice' })
    expect(host.querySelector<HTMLInputElement>('.ant-input-search input')?.value).toBe('alice')
    expect(host.querySelector('.ant-pagination-item-active')?.textContent).toContain('2')
    expect(host.textContent).toContain('姓名21')

    const replaceState = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
    await act(async () => host.querySelector<HTMLElement>('.ant-pagination-item-1')?.click())
    expect(replaceState).toHaveBeenCalledWith(null, '', '/settings?tab=users&q=alice&size=20')

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
    const replaceState = vi.spyOn(window.history, 'replaceState').mockImplementation(() => {})
    const searchButton = host.querySelector<HTMLButtonElement>('.ant-input-search-btn')
    expect(searchButton).not.toBeNull()
    await act(async () => searchButton?.click())
    expect(replaceState).toHaveBeenCalledWith(null, '', '/settings?tab=users&q=%E5%BC%A0%E8%B6%85')

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
