/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchEmployees: vi.fn(),
  fetchOnboardingTrainingRecord: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/lib/api/hr', () => api)
vi.mock('@ant-design/icons', () => ({
  DownloadOutlined: () => null,
  FileTextOutlined: () => null,
  PrinterOutlined: () => null,
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
  const Select = ({
    onChange,
    options,
    value,
  }: {
    onChange: (value: string) => void
    options: Array<{ label: string; value: string }>
    value?: string
  }) => createElement(
    'select',
    { value: value ?? '', onChange: (event: Event) => onChange((event.target as HTMLSelectElement).value) },
    [createElement('option', { key: 'empty', value: '' }, '选择员工')].concat(
      options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label)),
    ),
  )
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    Card: Wrapper,
    Select,
    Space: Wrapper,
  }
})

import TrainingRecordClient from './TrainingRecordClient'
import type { Employee } from '@/types/hr'

const employee: Employee = {
  id: 'employee-1',
  employee_number: 'E001',
  name: '张三',
  department: '质量部',
  position: '检验员',
  hire_date: '2026-08-01',
  status: 'active',
  gender: '男',
}

describe('TrainingRecordClient', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'log').mockImplementation(() => undefined)
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
  })

  async function mount() {
    await act(async () => {
      root.render(<TrainingRecordClient />)
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('loads employees and exports the selected onboarding record', async () => {
    api.fetchEmployees.mockResolvedValue({ data: [employee] })
    api.fetchOnboardingTrainingRecord.mockResolvedValue(undefined)
    await mount()

    const select = container.querySelector('select') as HTMLSelectElement
    act(() => {
      select.value = employee.id
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(container.textContent).toContain('张三')
    expect(container.textContent).toContain('质量部')

    const exportButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '导出Word',
    )
    await act(async () => exportButton?.click())

    expect(api.fetchOnboardingTrainingRecord).toHaveBeenCalledWith(employee.id, employee.name)
    expect(ui.message.success).toHaveBeenCalledWith('培训记录已导出')
  })

  it('maps non-Error load and export failures to safe user messages', async () => {
    api.fetchEmployees.mockRejectedValueOnce({ reason: 'network' })
    await mount()
    expect(ui.message.error).toHaveBeenCalledWith('加载员工列表失败: {"reason":"network"}')

    api.fetchEmployees.mockResolvedValueOnce({ data: [employee] })
    await act(async () => {
      root.unmount()
      root = createRoot(container)
    })
    await mount()
    const select = container.querySelector('select') as HTMLSelectElement
    act(() => {
      select.value = employee.id
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    api.fetchOnboardingTrainingRecord.mockRejectedValueOnce('provider unavailable')
    const exportButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '导出Word',
    )
    await act(async () => exportButton?.click())
    expect(ui.message.error).toHaveBeenLastCalledWith('导出失败')
  })
})
