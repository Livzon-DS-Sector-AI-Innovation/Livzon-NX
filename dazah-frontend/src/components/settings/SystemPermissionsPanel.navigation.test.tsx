/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'

vi.mock('@/components/system', () => ({
  RoleManager: () => <div>角色设置内容</div>,
  UserRoleManager: () => <div>用户角色内容</div>,
  DeptRoleMapper: () => <div>部门映射内容</div>,
  PermissionVerification: () => <div>权限检查内容</div>,
}))

import SystemPermissionsPanel from './SystemPermissionsPanel'

it('switches between authorization and checks without exposing menu management', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<SystemPermissionsPanel roles={[]} departments={[]} deptRules={[]} />))
    expect(host.querySelector('nav[aria-label="权限管理子导航"]')?.textContent).toContain('角色管理')
    expect(host.textContent).toContain('角色设置内容')
    expect(host.textContent).not.toContain('菜单管理')
    const tabs = Array.from(host.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
    expect(tabs.map((tab) => tab.textContent)).toEqual(['角色与授权', '权限检查'])
    await act(async () => tabs[1].click())
    expect(tabs[1].getAttribute('aria-selected')).toBe('true')
    expect(host.querySelector('nav[aria-label="权限管理子导航"]')).toBeNull()
    expect(host.textContent).toContain('权限检查内容')
    expect(host.textContent).not.toContain('角色设置内容')
    expect(host.textContent).not.toContain('菜单管理')

    await act(async () => tabs[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true })))
    expect(tabs[0].getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(tabs[0])
    const nav = host.querySelector('nav[aria-label="权限管理子导航"]')
    expect(nav?.textContent).toContain('角色管理')
    expect(nav?.textContent).toContain('用户角色')
    expect(nav?.textContent).toContain('部门角色映射')
    const userRoles = Array.from(nav!.querySelectorAll<HTMLButtonElement>('button')).find((button) => button.textContent?.includes('用户角色'))!
    await act(async () => userRoles.click())
    expect(userRoles.getAttribute('aria-current')).toBe('page')
    expect(host.textContent).toContain('用户角色内容')
    expect(host.textContent).not.toContain('权限检查内容')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
