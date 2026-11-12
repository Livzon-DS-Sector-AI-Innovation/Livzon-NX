/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { App, ConfigProvider, theme } from 'antd'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { createRole, deleteRole, updateRole } from '@/actions/admin'
import { RoleManager } from './RoleManager'

vi.mock('@/actions/admin', () => ({ createRole: vi.fn(), updateRole: vi.fn(), deleteRole: vi.fn() }))

it.each(['light', 'dark'])('validates and saves the new role form in %s mode', async (appearance) => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const button = (label: string) => Array.from(document.querySelectorAll('button'))
    .find((item) => item.textContent?.replace(/\s/g, '') === label)
  const enter = (input: HTMLInputElement, value: string) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }
  const errors = (field: Element | null) => [...(field?.querySelectorAll('.ant-form-item-explain-error') ?? [])]
    .map((item) => item.textContent)
  const submit = async () => act(async () => button('保存')?.click())
  const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  const render = (roles: React.ComponentProps<typeof RoleManager>['initialRoles']) => root.render(
    <ConfigProvider theme={{ algorithm: appearance === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
      <App><RoleManager initialRoles={roles} /></App>
    </ConfigProvider>,
  )
  vi.mocked(createRole).mockReset()
  try {
    await act(async () => render([]))
    await act(async () => button('新建角色')?.click())
    const name = document.querySelector<HTMLInputElement>('input#name')!
    const code = document.querySelector<HTMLInputElement>('input#code')!
    const nameField = name.closest('.ant-form-item')
    const codeField = code.closest('.ant-form-item')
    expect(nameField?.querySelector('.ant-form-item-extra')?.textContent).toContain('1–100 个字符，支持中文和数字')
    const codeHint = codeField?.querySelector('.ant-form-item-extra')?.textContent
    expect(codeHint).toContain('1–64 个字符')
    expect(codeHint).toContain('不能与未删除的角色重复')

    for (const [nameValue, codeValue, nameError, codeError] of [
      [' \u3000 ', '  ', '请输入角色名称', '请输入角色标识'],
      ['质量 审核员', 'qa auditor', '角色名称中间不能有空白', '角色标识中间不能有空白'],
      ['审'.repeat(101), 'a'.repeat(65), '角色名称最多 100 个字符', '角色标识最多 64 个字符'],
    ]) {
      await act(async () => { enter(name, nameValue); enter(code, codeValue) })
      await submit()
      await vi.waitFor(() => {
        expect(errors(nameField)).toContain(nameError)
        expect(errors(codeField)).toContain(codeError)
      })
    }
    const validName = '审'.repeat(98) + '2🧪'
    await act(async () => { enter(name, ` ${validName}\u3000`); enter(code, '角色!') })
    await submit()
    await vi.waitFor(() => expect(errors(codeField)).toContain('角色标识只能使用英文字母、数字和 _ . : -'))
    expect(createRole).not.toHaveBeenCalled()

    vi.mocked(createRole).mockResolvedValueOnce({ ok: false, status: 409, message: '角色标识已存在，请更换' })
    await act(async () => enter(code, ' qa_auditor\u0085'))
    await submit()
    expect(createRole).toHaveBeenCalledExactlyOnceWith({ name: validName, code: 'qa_auditor' })
    await vi.waitFor(() => expect(errors(codeField)).toContain('角色标识已存在，请更换'))
    expect(name.getAttribute('aria-invalid')).toBeNull()
    expect(name.value).toBe(` ${validName}\u3000`)

    const newRole = { id: 'role-1', name: validName, code: 'QA_v2:review.1-', is_system: false, permissions: [] }
    vi.mocked(createRole).mockImplementationOnce(async () => {
      render([newRole])
      return { ok: true, data: newRole }
    })
    await act(async () => enter(code, ' QA_v2:review.1- '))
    expect(code.getAttribute('aria-invalid')).toBeNull()
    await submit()
    expect(createRole).toHaveBeenLastCalledWith({ name: validName, code: 'QA_v2:review.1-' })
    await vi.waitFor(() => expect(document.querySelector('.ant-drawer-open')).toBeNull())
    expect(reload).not.toHaveBeenCalled()
    expect(host.querySelector('tr[data-row-key="role-1"]')?.textContent).toContain(newRole.code)
  } finally {
    reload.mockRestore()
    await act(async () => root.unmount())
    host.remove()
  }
})

it('retains failed edits and shows the saved role without a document reload', async () => {
  const role = { id: 'role-1', code: 'custom_role', name: '原角色名称', is_system: false, permissions: [] }
  const updated = { ...role, name: '更新后的角色名称' }
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  const render = (item: typeof role) => root.render(<App><RoleManager initialRoles={[item]} /></App>)
  const roleRow = () => host.querySelector('tr[data-row-key="role-1"]')
  const click = (label: string) => act(async () => {
    Array.from(document.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === label)!.click()
  })
  try {
    await act(async () => render(role))
    await click('编辑信息')
    const name = document.querySelector<HTMLInputElement>('input#name')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(name, updated.name)
      name.dispatchEvent(new Event('input', { bubbles: true }))
    })
    vi.mocked(updateRole).mockRejectedValueOnce(new Error('保存失败'))
    await click('保存')
    expect(document.querySelector('.ant-drawer-open')).not.toBeNull()
    expect(name.value).toBe(updated.name)
    expect(roleRow()?.textContent).toContain(role.name)

    vi.mocked(updateRole).mockImplementationOnce(async () => {
      render(updated)
      return updated
    })
    await click('保存')
    expect(updateRole).toHaveBeenLastCalledWith(role.id, { name: updated.name, description: undefined })
    await vi.waitFor(() => expect(document.querySelector('.ant-drawer-open')).toBeNull())
    expect(roleRow()?.textContent).toContain(updated.name)
    expect(reload).not.toHaveBeenCalled()
  } finally {
    reload.mockRestore()
    await act(async () => root.unmount())
    host.remove()
  }
})

it.each(['light', 'dark'])('shows 20 roles per page and recovers after deleting the last row in %s mode', async (appearance) => {
  const roles = Array.from({ length: 21 }, (_, index) => ({
    id: `role-${index + 1}`,
    code: `custom_role_${index + 1}`,
    name: `自定义角色 ${index + 1}`,
    is_system: false,
    permissions: [],
  }))
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const rows = () => Array.from(host.querySelectorAll('tbody tr[data-row-key]'))
  const render = (items: typeof roles) => root.render(
    <ConfigProvider theme={{ algorithm: appearance === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
      <App><RoleManager initialRoles={items} /></App>
    </ConfigProvider>,
  )
  vi.mocked(deleteRole).mockClear()
  vi.mocked(deleteRole).mockImplementationOnce(async () => render(roles.slice(0, 20)))
  try {
    await act(async () => render(roles))
    expect(rows().map((row) => row.getAttribute('data-row-key'))).toEqual(roles.slice(0, 20).map((role) => role.id))
    expect(host.querySelector('.ant-pagination-options-size-changer')).toBeNull()

    await act(async () => host.querySelector<HTMLButtonElement>('.ant-pagination-next button')!.click())
    expect(rows().map((row) => row.getAttribute('data-row-key'))).toEqual(['role-21'])
    const deleteButton = Array.from(rows()[0].querySelectorAll('button'))
      .find((button) => button.textContent?.replace(/\s/g, '') === '删除')
    await act(async () => deleteButton!.click())
    expect(document.querySelector('.ant-popconfirm-message')?.textContent).toContain('自定义角色 21')
    await act(async () => document.querySelector<HTMLButtonElement>('.ant-popconfirm-buttons .ant-btn-primary')!.click())
    expect(deleteRole).toHaveBeenCalledExactlyOnceWith('role-21')
    expect(rows()).toHaveLength(20)
    expect(host.querySelector('.ant-pagination-item-active')?.textContent).toBe('1')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})

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
    const html = renderToStaticMarkup(<App><RoleManager initialRoles={[
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
        <App><RoleManager initialRoles={[role]} /></App>
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
    expect(cells[5].querySelectorAll('a, button')).toHaveLength(3)
  })

  it.each([
    ['super_admin', true, '系统管理员', 'ant-tag-purple'],
    ['super_admin', false, '系统管理员', 'ant-tag-purple'],
    ['ordinary_admin', true, '普通管理员', 'ant-tag-blue'],
    ['ordinary_admin', false, '普通管理员', 'ant-tag-blue'],
    ['material_qa', true, '系统内置', 'ant-tag-gold'],
    ['custom_role', false, '自定义', 'ant-tag-green'],
  ])('distinguishes the role type by code and color: %s, built-in: %s', (code, isSystem, label, colorClass) => {
    const html = renderToStaticMarkup(<App><RoleManager initialRoles={[
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
    const html = renderToStaticMarkup(<App><RoleManager initialRoles={[
      { id: 'role-1', code, name: '测试角色', is_system: isSystem, permissions: [] },
    ]} /></App>)
    const container = document.createElement('div')
    container.innerHTML = html
    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>('tbody button'))
    expect(buttons.map(button => button.textContent?.replace(/\s/g, ''))).toEqual(disabled
      ? ['页面权限', '编辑信息', '删除'] : ['编辑信息', '删除'])
    expect(container.querySelector('tbody a')?.getAttribute('href')).toBe(disabled
      ? undefined : '/system/roles/role-1/page-permissions')
    for (const button of buttons) expect(button.disabled).toBe(disabled)
  })
})
