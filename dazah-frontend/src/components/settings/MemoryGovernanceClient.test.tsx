/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getAgentMemoryTenantPolicy: vi.fn(),
  saveAgentMemoryTenantPolicy: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn() },
  modal: { confirm: vi.fn() },
}))

vi.mock('@/actions/settings', () => actions)

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) =>
    createElement('div', null, children)
  const Button = ({
    children,
    disabled,
    onClick,
  }: {
    children?: ReactNode
    disabled?: boolean
    onClick?: () => void
  }) => createElement('button', { disabled, onClick }, children)
  const Select = ({
    onChange,
    options,
    value,
    ...props
  }: {
    'aria-label'?: string
    onChange: (value: string) => void
    options: Array<{ disabled?: boolean; label: string; value: string }>
    value: string
  }) => createElement(
    'select',
    {
      'aria-label': props['aria-label'],
      value,
      onChange: (event: Event) =>
        onChange((event.target as HTMLSelectElement).value),
    },
    options.map((option) => createElement(
      'option',
      { disabled: option.disabled, key: option.value, value: option.value },
      option.label,
    )),
  )
  const Alert = ({
    action,
    description,
    message,
  }: {
    action?: ReactNode
    description?: ReactNode
    message?: ReactNode
  }) => createElement('div', { role: 'alert' }, message, description, action)

  return {
    Alert,
    App: { useApp: () => ({ message: ui.message, modal: ui.modal }) },
    Button,
    Select,
    Skeleton: { Input: Wrapper },
    Space: Wrapper,
    Tag: Wrapper,
    Typography: { Text: Wrapper },
  }
})

import MemoryGovernanceClient, {
  canTightenTenantMemoryPolicy,
  modeLabels,
} from './MemoryGovernanceClient'
import { agentManagementTabKeys } from './FeishuSettingsClient'

const automaticPolicy = {
  tenant_id: 'tenant-a',
  global_mode: 'auto' as const,
  tenant_mode: 'auto' as const,
  effective_mode: 'auto' as const,
  policy_version: 1,
}

describe('MemoryGovernanceClient contracts', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('uses the governed memory modes exposed by the backend contract', () => {
    expect(modeLabels).toEqual({
      auto: '自动记忆',
      explicit_only: '仅显式记忆',
      disabled: '禁用记忆',
    })
  })

  it('is embedded in capability policies instead of using a separate tab', () => {
    expect(agentManagementTabKeys).not.toContain('memory')
    expect(agentManagementTabKeys).toContain('tools')
  })

  it('allows only equal or stricter tenant policies', () => {
    expect(canTightenTenantMemoryPolicy('auto', 'explicit_only')).toBe(true)
    expect(canTightenTenantMemoryPolicy('explicit_only', 'disabled')).toBe(true)
    expect(canTightenTenantMemoryPolicy('disabled', 'auto')).toBe(false)
  })

  it('loads policy and saves a confirmed stricter mode', async () => {
    actions.getAgentMemoryTenantPolicy.mockResolvedValue(automaticPolicy)
    actions.saveAgentMemoryTenantPolicy.mockResolvedValue({
      ...automaticPolicy,
      tenant_mode: 'explicit_only',
      effective_mode: 'explicit_only',
      policy_version: 2,
    })

    act(() => root.render(<MemoryGovernanceClient />))
    await act(async () => vi.runOnlyPendingTimersAsync())

    expect(container.textContent).toContain('实际上限')
    const select = container.querySelector('select') as HTMLSelectElement
    act(() => {
      select.value = 'explicit_only'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '保存',
    )
    act(() => saveButton?.click())
    expect(ui.modal.confirm).toHaveBeenCalledWith(expect.objectContaining({
      title: '确认收紧租户记忆策略？',
    }))

    await act(async () => {
      await ui.modal.confirm.mock.calls[0][0].onOk()
    })

    expect(actions.saveAgentMemoryTenantPolicy).toHaveBeenCalledWith({
      mode: 'explicit_only',
    })
    expect(ui.message.success).toHaveBeenCalledWith('租户记忆策略已保存')
  })

  it('shows load errors, retries, and reports save failures', async () => {
    actions.getAgentMemoryTenantPolicy
      .mockRejectedValueOnce(new Error('策略读取失败'))
      .mockResolvedValueOnce(automaticPolicy)
    actions.saveAgentMemoryTenantPolicy.mockRejectedValue(new Error('策略写入失败'))

    act(() => root.render(<MemoryGovernanceClient />))
    await act(async () => vi.runOnlyPendingTimersAsync())
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      '策略读取失败',
    )

    const retryButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '重试',
    )
    await act(async () => retryButton?.click())

    const select = container.querySelector('select') as HTMLSelectElement
    act(() => {
      select.value = 'disabled'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '保存',
    )
    act(() => saveButton?.click())
    await act(async () => {
      await ui.modal.confirm.mock.calls[0][0].onOk()
    })

    expect(ui.message.error).toHaveBeenCalledWith('策略写入失败')
  })
})
