/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const actions = vi.hoisted(() => ({
  exportSopPdf: vi.fn(),
  updateSopContent: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
  modal: { confirm: vi.fn() },
}))

vi.mock('@/actions/safety', () => actions)
vi.mock('antd', async () => {
  const { createElement } = await import('react')
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
  return {
    App: { useApp: () => ({ message: ui.message, modal: ui.modal }) },
    Button,
    Modal: () => null,
  }
})

vi.mock('@ant-design/icons', () => ({
  ArrowLeftOutlined: () => null,
  CheckCircleFilled: () => null,
  DeleteOutlined: () => null,
  DownloadOutlined: () => null,
  DownOutlined: () => null,
  PlusOutlined: () => null,
  RightOutlined: () => null,
  SaveOutlined: () => null,
  ThunderboltOutlined: () => null,
  UndoOutlined: () => null,
}))

import SopContentEditor from './SopContentEditor'

const initialContent = `**文件编号:** SOP-001
**生效日期:** 2026-08-20
**颁发部门:** 安全管理科

## 1. 目的

保障生产安全。`

function changeInput(input: HTMLInputElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  valueSetter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

describe('SopContentEditor lifecycle', () => {
  let container: HTMLDivElement
  let root: Root
  const onBack = vi.fn()
  const onSaved = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    actions.updateSopContent.mockResolvedValue(undefined)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  async function mount() {
    await act(async () => {
      root.render(
        <SopContentEditor
          regulationId="regulation-1"
          regulationName="反应岗位安全操作规程"
          content={initialContent}
          onBack={onBack}
          onSaved={onSaved}
        />,
      )
      await Promise.resolve()
    })
  }

  it('saves edited content through the safety action and notifies the parent', async () => {
    await mount()
    const documentNumber = container.querySelector('input[placeholder="编号"]') as HTMLInputElement
    act(() => {
      changeInput(documentNumber, 'SOP-002')
    })

    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '仅保存',
    )
    expect(saveButton?.disabled).toBe(false)
    await act(async () => saveButton?.click())

    expect(actions.updateSopContent).toHaveBeenCalledWith(
      'regulation-1',
      expect.stringContaining('SOP-002'),
      'reviewed',
    )
    expect(onSaved).toHaveBeenCalledOnce()
    expect(container.textContent).toContain('已保存')
  })

  it('requires confirmation before leaving with unsaved edits', async () => {
    await mount()
    const department = container.querySelector('input[placeholder="部门名称"]') as HTMLInputElement
    act(() => {
      changeInput(department, '生产部')
    })
    const backButton = Array.from(container.querySelectorAll('div')).find(
      (element) => element.textContent === '返回列表',
    )
    act(() => backButton?.click())

    expect(ui.modal.confirm).toHaveBeenCalledWith(expect.objectContaining({ title: '未保存的修改' }))
    expect(onBack).not.toHaveBeenCalled()
    act(() => ui.modal.confirm.mock.calls[0][0].onOk())
    expect(onBack).toHaveBeenCalledOnce()
  })
})
