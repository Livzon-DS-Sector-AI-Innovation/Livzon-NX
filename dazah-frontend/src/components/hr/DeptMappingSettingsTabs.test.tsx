/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchFeishuMemberDepartments: vi.fn(),
  fetchTrainingDepartments: vi.fn(),
  fetchTrainingDeptMappings: vi.fn(),
  fetchFeishuMembers: vi.fn(),
  fetchDeptScopes: vi.fn(),
  fetchCustomTrainingDepartments: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  createTrainingDeptMappingAction: vi.fn(),
  updateTrainingDeptMappingAction: vi.fn(),
  deleteTrainingDeptMappingAction: vi.fn(),
  saveDeptScopeAction: vi.fn(),
  clearDeptScopeAction: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))
const permissions = vi.hoisted(() => ({ canQuery: true, canSync: true, canDelete: true }))

const MAPPINGS = vi.hoisted(() => [
  {
    id: 'm-dept-1',
    source_name: '201二车间（多拉）',
    target_name: '201二车间（DR）',
    match_level: 'both' as const,
    mapping_type: 'special' as const,
    priority: 10,
    enabled: true,
    remark: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 'm-person-1',
    source_name: '安志刚',
    target_name: '201二车间（DR）',
    match_level: 'both' as const,
    mapping_type: 'person' as const,
    priority: 10,
    enabled: true,
    remark: '调入DR，飞书未改',
    created_at: null,
    updated_at: null,
  },
])

vi.mock('@/lib/api/client/hr', () => api)
vi.mock('@/actions/hr', () => actions)
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => permissions,
}))
vi.mock('./trainingDept', () => ({
  refreshDeptMappings: vi.fn(async () => undefined),
  ensureDeptMappings: vi.fn(async () => MAPPINGS),
  resolveTrainingDept: (d: string | null | undefined) => d,
  unifyDept: (d: string | undefined | null) => d,
  getModalRules: () => ({ drop: new Set(), noExpand: new Set(), extra: [] as string[] }),
  useDeptMappings: () => ({ version: 1 }),
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const Button = ({
    children,
    disabled,
    loading,
    onClick,
  }: {
    children?: ReactNode
    disabled?: boolean
    loading?: boolean
    onClick?: () => void
  }) => createElement('button', { disabled: disabled || loading, onClick }, children)
  const Table = ({
    columns = [],
    dataSource = [],
    rowKey,
  }: {
    columns?: Array<{ title?: ReactNode; dataIndex?: string; render?: (value: unknown, record: Record<string, unknown>) => ReactNode }>
    dataSource?: Array<Record<string, unknown>>
    rowKey?: string
  }) =>
    createElement(
      'table',
      null,
      createElement(
        'tbody',
        null,
        dataSource.map((record) =>
          createElement(
            'tr',
            { key: rowKey ? String(record[rowKey]) : undefined },
            columns.map((column, ci) =>
              createElement(
                'td',
                { key: ci },
                column.render
                  ? column.render(column.dataIndex ? record[column.dataIndex] : undefined, record)
                  : column.dataIndex
                    ? String(record[column.dataIndex] ?? '')
                    : null,
              ),
            ),
          ),
        ),
      ),
    )
  const Select = (props: {
    disabled?: boolean
    mode?: string
    value?: unknown
    onChange?: (v: unknown) => void
    options?: Array<{ value: string; label: ReactNode }>
  }) => {
    if (props.mode === 'multiple') {
      return createElement(
        'div',
        null,
        (props.options || []).map((o) =>
          createElement(
            'button',
            {
              key: o.value,
              disabled: props.disabled,
              onClick: () =>
                props.onChange?.([...(Array.isArray(props.value) ? (props.value as string[]) : []), o.value]),
            },
            `pick-${o.value}`,
          ),
        ),
      )
    }
    return createElement(
      'select',
      {
        value: String(props.value ?? ''),
        disabled: props.disabled,
        onChange: (e: { target: { value: string } }) => props.onChange?.(e.target.value),
      },
      (props.options || []).map((o) =>
        createElement('option', { key: o.value, value: o.value }, o.label),
      ),
    )
  }
  const Popconfirm = ({
    title,
    onConfirm,
    children,
  }: {
    title?: ReactNode
    onConfirm?: () => void
    children?: ReactNode
  }) =>
    createElement(
      'span',
      null,
      children,
      createElement('button', { onClick: onConfirm }, title ?? 'popconfirm-ok'),
    )
  const Typography = {
    Title: ({ children }: { children?: ReactNode }) => createElement('h5', null, children),
    Paragraph: ({ children }: { children?: ReactNode }) => createElement('p', null, children),
    Text: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
  }
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    Card: Wrapper,
    Input: Object.assign((props: Record<string, unknown>) => createElement('input', props), {
      Search: () => createElement('input'),
    }),
    Popconfirm,
    Result: ({ title }: { title?: ReactNode }) => createElement('div', null, title),
    Select,
    Space: Wrapper,
    Switch: ({ checked }: { checked?: boolean }) => createElement('input', { type: 'checkbox', checked: !!checked }),
    Table,
    Tabs: ({ items = [] }: { items?: Array<{ key: string; label: ReactNode; children?: ReactNode }> }) =>
      createElement(
        'div',
        null,
        createElement(
          'div',
          { 'data-testid': 'tab-buttons' },
          items.map((it) => createElement('button', { key: it.key }, it.label)),
        ),
        items.map((it) => createElement('div', { key: `pane-${it.key}` }, it.children)),
      ),
    Tag: Wrapper,
    Tooltip: Wrapper,
    Typography,
    Modal: ({ open, children, onOk }: { open?: boolean; children?: ReactNode; onOk?: () => void }) =>
      open ? createElement('div', { 'data-testid': 'modal' }, children,
        createElement('button', { onClick: onOk }, 'modal-save')) : null,
  }
})

import DeptMappingSettingsClient from './DeptMappingSettingsClient'
import DeptScopeSettingsClient from './DeptScopeSettingsClient'

describe('DeptMappingSettingsClient 双 Tab 与人员归属', () => {
  const pickPerson = async (label: string) => {
    let btn: HTMLButtonElement | undefined
    for (let i = 0; i < 10 && !btn; i++) {
      btn = Array.from(container.querySelectorAll('button')).find((b) =>
        b.textContent === `pick-${label}`,
      )
      if (!btn) await act(async () => { await Promise.resolve() })
    }
    expect(btn).toBeTruthy()
    act(() => {
      btn?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })
  }

  const findDeptSelect = () =>
    Array.from(container.querySelectorAll('select')).find((sel) =>
      Array.from(sel.options).some((o) => o.value === '201二车间（DR）'),
    ) as HTMLSelectElement | undefined

  const setDept = async () => {
    const deptSelect = findDeptSelect()
    act(() => {
      if (deptSelect) {
        deptSelect.value = '201二车间（DR）'
        deptSelect.dispatchEvent(new Event('change', { bubbles: true }))
      }
    })
    await act(async () => {
      await Promise.resolve()
    })
  }

  const clickSave = async () => {
    const saveButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('批量配置'),
    )
    act(() => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }


  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(permissions, { canQuery: true, canSync: true, canDelete: true })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    api.fetchFeishuMemberDepartments.mockResolvedValue([])
    api.fetchDeptScopes.mockResolvedValue([{ user_id: 'test-user', user_name: '测试用户',
      user_department: '质量部', visible_depts: ['质量部'] }])
    api.fetchCustomTrainingDepartments.mockResolvedValue([])
    api.fetchTrainingDepartments.mockResolvedValue([
      '201二车间（MC）',
      '201二车间（DR）',
      '质量部',
    ])
    api.fetchTrainingDeptMappings.mockResolvedValue(MAPPINGS)
    api.fetchFeishuMembers.mockResolvedValue({
      code: 200,
      data: [
        { name: '安志刚', department: '201二车间' },
        { name: '徐增超', department: '201二车间' },
        { name: '测新人', department: '质量部' },
      ],
    })
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  const renderPage = async () => {
    act(() => {
      root.render(createElement(DeptMappingSettingsClient))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('双 Tab 渲染：人员归属面板列出 person 行（姓名/归属部门）', async () => {
    await renderPage()

    expect(container.textContent).toContain('部门映射')
    expect(container.textContent).toContain('人员归属')
    expect(container.textContent).toContain('安志刚')
    expect(container.textContent).toContain('201二车间（DR）')
  })

  it('页面查询授权可打开配置，写入和删除分别授权，撤销后不再放行', async () => {
    Object.assign(permissions, { canQuery: true, canSync: false, canDelete: false })
    await renderPage()
    const buttons = () => Array.from(container.querySelectorAll('button'))
    const batch = () => buttons().find((button) => button.textContent === '批量配置')!
    expect(container.textContent).toContain('安志刚')
    expect(batch().disabled).toBe(true)
    expect(buttons().find((button) => button.textContent === '新增映射')?.disabled).toBe(true)
    expect(buttons().find((button) => button.textContent === '删除')?.disabled).toBe(true)
    permissions.canSync = true
    await renderPage()
    expect(batch().disabled).toBe(false)
    expect(buttons().find((button) => button.textContent === '删除')?.disabled).toBe(true)
    permissions.canSync = false
    await renderPage()
    expect(batch().disabled).toBe(true)
    act(() => batch().click())
    expect(actions.createTrainingDeptMappingAction).not.toHaveBeenCalled()
  })

  it('部门权限配置的保存、清除和移除按页面敏感操作授权', async () => {
    Object.assign(permissions, { canQuery: true, canSync: false, canDelete: false })
    const renderScopes = async () => {
      await act(async () => root.render(createElement(DeptScopeSettingsClient)))
      await act(async () => { await Promise.resolve(); await Promise.resolve() })
    }
    const button = (text: string) => Array.from(container.querySelectorAll('button'))
      .find((item) => item.textContent === text)!
    await renderScopes()
    expect(container.textContent).toContain('测试用户')
    expect(button('清除').disabled).toBe(true)
    expect(button('移除').disabled).toBe(true)
    permissions.canSync = true
    await renderScopes()
    expect(button('清除').disabled).toBe(false)
    expect(button('移除').disabled).toBe(true)
    permissions.canDelete = true
    await renderScopes()
    expect(button('移除').disabled).toBe(false)
    Object.assign(permissions, { canSync: false, canDelete: false })
    await renderScopes()
    expect(button('清除').disabled).toBe(true)
    expect(button('移除').disabled).toBe(true)
    act(() => {
      button('清除').click()
      button('移除').click()
    })
    expect(actions.saveDeptScopeAction).not.toHaveBeenCalled()
    expect(actions.clearDeptScopeAction).not.toHaveBeenCalled()
  })

  it('仅有配置授权时原地更新映射，保留匹配规则且无需删除权限', async () => {
    permissions.canDelete = false
    actions.updateTrainingDeptMappingAction.mockResolvedValue({ code: 200 })
    await renderPage()
    const row = Array.from(container.querySelectorAll('tr')).find((item) => item.textContent?.includes('201二车间（多拉）'))!
    act(() => row.querySelector('button')?.click())
    const modal = container.querySelector('[data-testid="modal"]')!
    const selects = modal.querySelectorAll('select')
    for (const select of selects) {
      act(() => {
        select.value = '201二车间（DR）'
        select.dispatchEvent(new Event('change', { bubbles: true }))
      })
    }
    await act(async () => {
      Array.from(modal.querySelectorAll('button')).find((button) => button.textContent === 'modal-save')?.click()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(actions.updateTrainingDeptMappingAction).toHaveBeenCalledWith('m-dept-1', expect.objectContaining({
      target_name: '201二车间（DR）', match_level: 'both', priority: 10,
    }))
    expect(actions.deleteTrainingDeptMappingAction).not.toHaveBeenCalled()
  })

  it('人员归属批量配置：多选人员后按 person 类型逐条创建', async () => {
    actions.createTrainingDeptMappingAction.mockResolvedValue({ code: 200, data: {} })
    await renderPage()

    act(() => {
      container.querySelector('button') // 占位保证容器存在
    })
    const pickButtons = Array.from(container.querySelectorAll('button')).filter((b) =>
      b.textContent?.startsWith('pick-'),
    )
    expect(pickButtons.length).toBe(3)
    await pickPerson('徐增超')
    await pickPerson('测新人') // 安志刚已有 person 配置，批量时应跳过

    await setDept()
    await clickSave()
    expect(actions.createTrainingDeptMappingAction).toHaveBeenCalledTimes(2)
    const first = actions.createTrainingDeptMappingAction.mock.calls[0][0]
    expect(first.mapping_type).toBe('person')
    expect(first.target_name).toBe('201二车间（DR）')
    expect(ui.message.success).toHaveBeenCalled()
  })

  it('批量配置失败：提示真实错误且不误报成功', async () => {
    actions.createTrainingDeptMappingAction.mockRejectedValue(new Error('没有 hr:write 权限'))
    await renderPage()

    await pickPerson('徐增超')
    await setDept()
    await clickSave()

    expect(ui.message.error).toHaveBeenCalledWith('没有 hr:write 权限')
    expect(ui.message.success).not.toHaveBeenCalled()
  })
})
