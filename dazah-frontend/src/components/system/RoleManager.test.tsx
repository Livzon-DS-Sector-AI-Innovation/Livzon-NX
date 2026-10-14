/* @vitest-environment happy-dom */
import React from 'react'
import { App, ConfigProvider, theme } from 'antd'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { RoleManager } from './RoleManager'

vi.mock('@/actions/admin', () => ({ createRole: vi.fn(), updateRole: vi.fn(), deleteRole: vi.fn() }))
vi.mock('./RolePagePermissionsDrawer', () => ({ RolePagePermissionsDrawer: () => null }))

describe('role operation availability', () => {
  it.each([
    ['quality_qc', true, '系统内置角色，可编辑'],
    ['product_qa', true, '系统内置角色，可编辑'],
    ['change_qa', true, '系统内置角色，可编辑'],
    ['validation_qa', true, '系统内置角色，可编辑'],
    ['system_qa', true, '系统内置角色，可编辑'],
    ['material_qa', true, '系统内置角色，可编辑'],
    ['other_builtin', true, '系统内置角色，可编辑'],
    ['super_admin', true, '原有职责说明'],
    ['ordinary_admin', true, '原有职责说明'],
    ['custom_role', false, '原有职责说明'],
    ['quality_qc', false, '原有职责说明'],
  ])('shows the unified description only for editable built-in roles: %s, built-in: %s', (code, isSystem, expected) => {
    const html = renderToStaticMarkup(<App><RoleManager initialDepartments={[]} initialRoles={[
      { id: 'role-1', code, name: '测试角色', description: '原有职责说明', is_system: isSystem, permissions: [] },
    ]} /></App>)
    const container = document.createElement('div')
    container.innerHTML = html
    const cell = container.querySelectorAll('tbody tr[data-row-key] td')[4]
    expect(cell.textContent).toBe(expected)
    expect(cell.getAttribute('title')).toBe(expected)
  })

  it.each(['light', 'dark'])('keeps long role details accessible in a compact %s table', (appearance) => {
    const role = {
      id: 'role-long',
      code: 'probe-role-0c4d1c78174e460987a370ce97d96340',
      name: '用于验证长名称展示的自定义角色',
      description: '负责质量管理中的审核、查询及相关业务记录维护',
      grant_version: 7,
      is_system: false,
      permissions: [],
    }
    const html = renderToStaticMarkup(
      <ConfigProvider theme={{ algorithm: appearance === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
        <App><RoleManager initialDepartments={[]} initialRoles={[role]} /></App>
      </ConfigProvider>,
    )
    const container = document.createElement('div')
    container.innerHTML = html
    const table = container.querySelector('table')!
    expect(table.style.tableLayout).toBe('fixed')
    expect(table.style.minWidth).toBe('100%')
    expect(table.style.width).toBe('900px')
    const columns = Array.from(table.querySelectorAll('col'))
    expect(columns.map(column => column.style.width)).toEqual(['120px', '180px', '110px', '120px', '', '240px'])
    const cells = Array.from(table.querySelectorAll('tbody tr[data-row-key] td'))
    for (const [index, value] of [[0, role.name], [1, role.code], [4, role.description]] as const) {
      expect(cells[index].classList.contains('ant-table-cell-ellipsis')).toBe(true)
      expect(cells[index].getAttribute('title')).toBe(value)
    }
    expect(cells[3].textContent).toBe('7')
    expect(cells[5].querySelectorAll('button')).toHaveLength(3)
  })

  it.each([
    ['super_admin', true, '系统管理员', 'ant-tag-purple'],
    ['super_admin', false, '系统管理员', 'ant-tag-purple'],
    ['ordinary_admin', true, '普通管理员', 'ant-tag-blue'],
    ['ordinary_admin', false, '普通管理员', 'ant-tag-blue'],
    ['material_qa', true, '系统内置', 'ant-tag-gold'],
    ['custom_role', false, '自定义', 'ant-tag-green'],
  ])('distinguishes the role type by code and color: %s, built-in: %s', (code, isSystem, label, colorClass) => {
    const html = renderToStaticMarkup(<App><RoleManager initialDepartments={[]} initialRoles={[
      { id: 'role-1', code, name: '测试角色', is_system: isSystem, permissions: [] },
    ]} /></App>)
    const container = document.createElement('div')
    container.innerHTML = html
    const tag = container.querySelector('tbody .ant-tag')!
    expect(tag.textContent).toBe(label)
    if (colorClass) expect(tag.classList.contains(colorClass)).toBe(true)
    else {
      expect(tag.classList.contains('ant-tag-purple')).toBe(false)
      expect(tag.classList.contains('ant-tag-blue')).toBe(false)
      expect(tag.classList.contains('ant-tag-gold')).toBe(false)
    }
  })

  it.each([
    ['material_qa', true, false],
    ['custom_role', false, false],
    ['super_admin', true, true],
    ['super_admin', false, true],
    ['ordinary_admin', true, true],
    ['ordinary_admin', false, true],
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
