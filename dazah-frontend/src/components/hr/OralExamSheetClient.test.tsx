/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  upsertTrainingSession: vi.fn(),
  upsertTrainingDocument: vi.fn(),
  generateOralExamResult: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/actions/hr', () => actions)

vi.mock('@ant-design/icons', () => ({
  PlusOutlined: () => null,
  DeleteOutlined: () => null,
  DownloadOutlined: () => null,
  RobotOutlined: () => null,
  CloseCircleOutlined: () => null,
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
  const Input = ({
    value,
    onChange,
    placeholder,
  }: {
    value?: string
    onChange?: (value: string) => void
    placeholder?: string
  }) =>
    createElement('input', {
      value: value ?? '',
      placeholder,
      onChange: (event: Event) => onChange?.((event.target as HTMLInputElement).value),
    })
  ;(Input as unknown as Record<string, unknown>).TextArea = Input
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Alert: Wrapper,
    Button,
    Input,
    Space: Wrapper,
  }
})

vi.mock('./trainingDept', () => ({
  unify201Dept: (value: string) => value,
  ensureDeptMappings: vi.fn(() => Promise.resolve()),
}))

vi.mock('./OralExamAiModal', () => ({ default: () => null }))
vi.mock('./trainingDocStyle', () => ({ default: ({ children }: { children?: ReactNode }) => children }))

import OralExamSheetClient from './OralExamSheetClient'
import type { TrainingSessionData } from '@/types/hr'

const sessionData: TrainingSessionData = {
  topic: 'GMP培训',
  training_date: '2026-08-25',
  assessment_method: '口试',
  department: '质量部',
  employee_names: ['李四'],
  employee_dept_map: { 李四: '质量部' },
}

describe('OralExamSheetClient', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  const render = (props: Record<string, unknown> = {}) => {
    act(() => {
      root.render(
        createElement(OralExamSheetClient, {
          sessionData,
          registerDocBuilder: vi.fn(),
          registerExporter: vi.fn(),
          ...props,
        } as never),
      )
    })
  }

  const remarkDashes = () =>
    Array.from(container.querySelectorAll('input')).filter((i) => (i as HTMLInputElement).value === '—')

  it('auto person rows default remark to em-dash', () => {
    render()
    expect(remarkDashes().length).toBe(1)
  })

  it('adds and removes person rows with default remark', () => {
    render()
    const add = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('增加人员行'))
    expect(add).toBeTruthy()
    act(() => { add?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(remarkDashes().length).toBe(2)
    const del = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('删除人员行'))
    expect(del).toBeTruthy()
    act(() => { del?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    expect(remarkDashes().length).toBe(1)
  })

  it('restores saved persons and normalizes empty remark to em-dash', () => {
    render({
      initialPayload: {
        content: '',
        training_date: '',
        questions: [],
        assessor: '',
        persons: [{ name: '王五', department: '质量部', question_nos: '', result: '', remark: '' }],
      },
    })
    expect(remarkDashes().length).toBe(1)
  })
})
