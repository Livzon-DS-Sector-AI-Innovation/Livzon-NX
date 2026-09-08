/* @vitest-environment happy-dom */
import React from 'react'
import { App } from 'antd'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { RoleManager } from './RoleManager'

vi.mock('@/actions/admin', () => ({ createRole: vi.fn(), updateRole: vi.fn(), deleteRole: vi.fn() }))
vi.mock('./RolePagePermissionsDrawer', () => ({ RolePagePermissionsDrawer: () => null }))

describe('role operation availability', () => {
  it.each([
    ['material_qa', true, false],
    ['custom_role', false, false],
    ['super_admin', true, true],
    ['super_admin', false, true],
  ])('protects operations by role code: %s, built-in: %s', (code, isSystem, disabled) => {
    const html = renderToStaticMarkup(<App><RoleManager initialDepartments={[]} initialRoles={[
      { id: 'role-1', code, name: '测试角色', is_system: isSystem, permissions: [] },
    ]} /></App>)
    const container = document.createElement('div')
    container.innerHTML = html
    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>('tbody button'))
    expect(buttons.map(button => button.textContent?.replace(/\s/g, ''))).toEqual(['页面权限', '编辑信息', '删除'])
    for (const button of buttons) expect(button.disabled).toBe(disabled)
  })
})
