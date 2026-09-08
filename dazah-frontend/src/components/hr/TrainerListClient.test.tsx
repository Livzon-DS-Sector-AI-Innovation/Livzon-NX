/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchTrainers: vi.fn(),
  fetchTrainingDepartments: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  createTrainer: vi.fn(),
  updateTrainer: vi.fn(),
  deleteTrainer: vi.fn(),
  importTrainers: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

// 表单实例状态：回填捕获 + 受控的 validateFields 返回值
const formState = vi.hoisted(() => ({
  validateValues: {} as Record<string, unknown>,
  setCalls: [] as Array<Record<string, unknown>>,
}))

vi.mock('@/lib/api/client/hr', () => api)
vi.mock('@/actions/hr', () => actions)

vi.mock('@ant-design/icons', () => ({
  PlusOutlined: () => null,
  ExportOutlined: () => null,
  ImportOutlined: () => null,
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
  const Form = ({ children }: { children?: ReactNode }) => createElement('form', null, children)
  const FormItem = ({ children, label }: { children?: ReactNode; label?: ReactNode }) =>
    createElement('div', null, label, '：', children)
  ;(Form as unknown as Record<string, unknown>).Item = FormItem
  const formInstance = {
    resetFields: () => undefined,
    validateFields: () => Promise.resolve(formState.validateValues),
    setFieldsValue: (values: Record<string, unknown>) => {
      formState.setCalls.push(values)
    },
    getFieldsValue: () => ({}),
  }
  ;(Form as unknown as Record<string, unknown>).useForm = () => [formInstance]
  const Input = (props: Record<string, unknown>) => createElement('input', props)
  ;(Input as unknown as Record<string, unknown>).TextArea = (props: Record<string, unknown>) =>
    createElement('textarea', props)
  ;(Input as unknown as Record<string, unknown>).Search = (props: Record<string, unknown>) =>
    createElement('input', props)
  const Modal = ({
    open,
    onOk,
    children,
  }: {
    open?: boolean
    onOk?: () => void
    children?: ReactNode
  }) =>
    open
      ? createElement(
          'div',
          { 'data-testid': 'modal' },
          children,
          createElement('button', { onClick: onOk }, 'modal-ok'),
        )
      : null
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    DatePicker: () => createElement('input', { type: 'date' }),
    Form,
    Input,
    Modal,
    Popconfirm: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
    Select: ({ options = [] }: { options?: Array<{ label: ReactNode; value: string }> }) =>
      createElement(
        'select',
        null,
        options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label)),
      ),
    Space: Wrapper,
    Table,
    Upload: Wrapper,
  }
})

import TrainerListClient from './TrainerListClient'

function makeTrainer() {
  return {
    id: 'trainer-1',
    name: '张三',
    department: '质量部',
    position: '高级工程师',
    approval_date: '2025-03-21',
    remarks: '原备注',
  }
}

describe('TrainerListClient 编辑修复', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    formState.validateValues = {}
    formState.setCalls = []
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    api.fetchTrainers.mockResolvedValue({
      code: 200,
      data: [makeTrainer()],
      total: 1,
    })
    api.fetchTrainingDepartments.mockResolvedValue(['质量部', '生产部'])
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  const renderAndOpenEditModal = async () => {
    act(() => {
      root.render(createElement(TrainerListClient))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    const editButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('编辑'),
    )
    expect(editButton).toBeTruthy()
    act(() => {
      editButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })
  }

  it('编辑回填：部门以数组形态进 tags 控件，批准时间为有效日期', async () => {
    await renderAndOpenEditModal()

    expect(formState.setCalls.length).toBeGreaterThan(0)
    const filled = formState.setCalls[formState.setCalls.length - 1]
    expect(filled.department).toEqual(['质量部'])
    expect(filled.name).toBe('张三')
    // dayjs 对象（有 format 方法）而非字符串/Invalid Date
    const approval = filled.approval_date as { format: (f: string) => string }
    expect(typeof approval.format).toBe('function')
    expect(approval.format('YYYY-MM-DD')).toBe('2025-03-21')
  })

  it('提交归一：tags 数组转字符串、空字段显式传 null 允许清空', async () => {
    actions.updateTrainer.mockResolvedValue({ code: 200, message: '更新成功' })
    formState.validateValues = {
      name: '张三',
      department: ['质量部'],
      position: undefined,
      approval_date: { format: () => '2025-03-21' },
      remarks: undefined,
    }

    await renderAndOpenEditModal()
    const okButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('modal-ok'),
    )
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(actions.updateTrainer).toHaveBeenCalledWith('trainer-1', {
      name: '张三',
      department: '质量部',
      position: null,
      approval_date: '2025-03-21',
      remarks: null,
    })
    expect(ui.message.error).not.toHaveBeenCalled()
  })

  it('失败透传：显示后端真实错误原因而非笼统「操作失败」', async () => {
    actions.updateTrainer.mockRejectedValue(new Error('没有 hr:write 权限'))
    formState.validateValues = {
      name: '张三',
      department: ['质量部'],
      position: '高级工程师',
      approval_date: undefined,
      remarks: '原备注',
    }

    await renderAndOpenEditModal()
    const okButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('modal-ok'),
    )
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(ui.message.error).toHaveBeenCalledWith('没有 hr:write 权限')
    expect(ui.message.success).not.toHaveBeenCalled()
  })
})
