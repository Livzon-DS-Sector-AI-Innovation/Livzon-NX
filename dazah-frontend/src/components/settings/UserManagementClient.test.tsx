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

vi.mock('@/actions/users', () => mocks)

import UserManagementClient from './UserManagementClient'

describe('UserManagementClient permission entry', () => {
  let host: HTMLDivElement

  beforeEach(() => {
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
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
    vi.clearAllMocks()
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
})
