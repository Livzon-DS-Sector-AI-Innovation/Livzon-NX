/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const qualityApi = vi.hoisted(() => ({
  fetchDocumentDepartments: vi.fn(),
  fetchDocumentEntries: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => qualityApi)

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  // 表格：选择型表格渲染真实复选框（还原 getCheckboxProps.disabled 与选中态），
  // 行内单元格按 dataIndex 取值
  const Table = ({
    columns = [],
    dataSource = [],
    rowKey,
    rowSelection,
  }: {
    columns?: Array<{ title?: ReactNode; dataIndex?: string; render?: (value: unknown, record: Record<string, unknown>) => ReactNode }>
    dataSource?: Array<Record<string, unknown>>
    rowKey?: string
    rowSelection?: {
      selectedRowKeys?: Array<string | number>
      onChange?: (keys: Array<string | number>, rows: Array<Record<string, unknown>>) => void
      getCheckboxProps?: (record: Record<string, unknown>) => { disabled?: boolean }
    }
  }) =>
    createElement(
      'table',
      null,
      createElement(
        'tbody',
        null,
        dataSource.map((record) => {
          const key = rowKey ? String(record[rowKey]) : ''
          const checkbox = rowSelection?.onChange
            ? createElement('input', {
                key: 'selection-checkbox',
                type: 'checkbox',
                checked: rowSelection.selectedRowKeys?.includes(key) ?? false,
                disabled: rowSelection.getCheckboxProps?.(record)?.disabled ?? false,
                onChange: (event: Event) => {
                  if ((event.target as HTMLInputElement).checked) {
                    rowSelection.onChange?.([key], [record])
                  }
                },
              })
            : null
          return createElement(
            'tr',
            { key },
            columns.map((column, ci) =>
              createElement(
                'td',
                { key: ci },
                ci === 0 && checkbox ? [checkbox as ReactNode] : null,
                column.render
                  ? column.render(column.dataIndex ? record[column.dataIndex] : undefined, record)
                  : column.dataIndex
                    ? String(record[column.dataIndex] ?? '')
                    : null,
              ),
            ),
          )
        }),
      ),
    )
  const Modal = ({
    open,
    title,
    children,
    onOk,
    okText,
    okButtonProps,
  }: {
    open?: boolean
    title?: ReactNode
    children?: ReactNode
    onOk?: () => void
    okText?: string
    okButtonProps?: { disabled?: boolean }
  }) =>
    open
      ? createElement(
          'div',
          { role: 'dialog' },
          createElement('h2', null, title),
          children,
          createElement('button', { onClick: onOk, disabled: okButtonProps?.disabled }, okText ?? '确定'),
        )
      : null
  const Input = (props: Record<string, unknown>) => createElement('input', props)
  ;(Input as unknown as Record<string, unknown>).Search = (props: Record<string, unknown>) =>
    createElement('input', props)
  const Select = ({
    value,
    options = [],
  }: {
    value?: string
    options?: Array<{ label: ReactNode; value: string }>
  }) =>
    createElement(
      'select',
      { value },
      options.map((option) =>
        createElement('option', { key: option.value, value: option.value }, option.label),
      ),
    )
  return { Modal, Select, Input, Space: Wrapper, Table, Tag: Wrapper }
})

import DocumentCatalogPickerModal from './DocumentCatalogPickerModal'

const DEPARTMENTS = [{ id: 'd1', name: '工艺规程' }]

const ENTRIES = {
  items: [
    { id: 'e1', code: 'KP-FT3-MC-001/17', name: '霉酚酸提练工艺规程', effective_date: '2026-01-01' },
    { id: 'e2', code: 'KP-XT-LV-002/01', name: '洛伐他汀提炼混合工艺规程', effective_date: '2026-01-01' },
  ],
  total: 2,
}

function findRowCheckbox(scope: HTMLElement, rowText: string) {
  const row = Array.from(scope.querySelectorAll('tr')).find((tr) =>
    tr.textContent?.includes(rowText),
  )
  return (row?.querySelector('input[type="checkbox"]') ?? null) as HTMLInputElement | null
}

describe('从文件管理选择培训内容弹窗', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    qualityApi.fetchDocumentDepartments.mockResolvedValue(DEPARTMENTS)
    qualityApi.fetchDocumentEntries.mockResolvedValue(ENTRIES)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('excludeNames 中的文件置灰不可勾选，其余文件保持可选', async () => {
    const onConfirm = vi.fn()
    act(() => {
      root.render(
        createElement(DocumentCatalogPickerModal, {
          open: true,
          onClose: vi.fn(),
          onConfirm,
          // 场景：文件 e1 名称已在 excludeNames（如本份培训已勾选），e2 不在
          excludeNames: ['霉酚酸提练工艺规程'],
        }),
      )
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(qualityApi.fetchDocumentEntries).toHaveBeenCalledWith(
      expect.objectContaining({ department_id: 'd1' }),
    )
    const excluded = findRowCheckbox(container, '霉酚酸提练工艺规程')
    const selectable = findRowCheckbox(container, '洛伐他汀提炼混合工艺规程')
    expect(excluded?.disabled).toBe(true)
    expect(selectable?.disabled).toBe(false)

    // 确定按钮在未勾选时禁用
    const okButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('确认录入'),
    )
    expect(okButton?.disabled).toBe(true)
  })

  it('勾选可选文件后确认录入，带回名称、编码与条目 ID', async () => {
    const onConfirm = vi.fn()
    act(() => {
      root.render(
        createElement(DocumentCatalogPickerModal, {
          open: true,
          onClose: vi.fn(),
          onConfirm,
          excludeNames: [],
        }),
      )
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    const selectable = findRowCheckbox(container, '洛伐他汀提炼混合工艺规程')
    // 原生 click 切换 checked 并触发 React onChange（组件收到 [e2] 勾选）
    act(() => {
      selectable?.click()
    })
    await act(async () => {
      await Promise.resolve()
    })

    const okButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('确认录入'),
    )
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(onConfirm).toHaveBeenCalledWith([
      { name: '洛伐他汀提炼混合工艺规程', code: 'KP-XT-LV-002/01', entryId: 'e2' },
    ])
  })
})
