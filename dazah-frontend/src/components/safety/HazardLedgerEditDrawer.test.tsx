/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const actions = vi.hoisted(() => ({
  updateHazardIdentification: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
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
  }) =>
    createElement(
      'button',
      { disabled: disabled || loading, onClick, type: 'button', 'data-btn': String(children) },
      children
    )
  const Text = ({ children }: { children?: ReactNode }) =>
    createElement('span', null, children)
  const Space = ({ children }: { children?: ReactNode }) =>
    createElement('div', null, children)
  const Input = ({
    value,
    onChange,
    placeholder,
  }: {
    value?: string
    onChange?: (e: { target: { value: string } }) => void
    placeholder?: string
  }) =>
    createElement('input', {
      value,
      placeholder,
      onChange: (e: unknown) => onChange?.(e as { target: { value: string } }),
    })
  Input.TextArea = ({
    value,
    onChange,
    placeholder,
  }: {
    value?: string
    onChange?: (e: { target: { value: string } }) => void
    placeholder?: string
  }) =>
    createElement('textarea', {
      value,
      placeholder,
      onChange: (e: unknown) => onChange?.(e as { target: { value: string } }),
    })
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button,
    Drawer: ({
      open,
      title,
      children,
      footer,
    }: {
      open: boolean
      title?: ReactNode
      children?: ReactNode
      footer?: ReactNode
    }) => (open ? createElement('div', null, title, children, footer) : null),
    Input,
    InputNumber: ({
      value,
      onChange,
    }: {
      value?: number | null
      onChange?: (v: number | null) => void
    }) =>
      createElement('input', {
        type: 'number',
        value: value ?? '',
        onChange: (e: Event) => {
          const raw = (e.target as HTMLInputElement).value
          onChange?.(raw === '' ? null : Number(raw))
        },
      }),
    Select: ({
      value,
      options,
    }: {
      value?: string
      options?: Array<{ value: string; label: string }>
    }) =>
      createElement(
        'select',
        { value, 'data-testid': 'level-select' },
        (options || []).map((option) =>
          createElement(
            'option',
            { key: option.value, value: option.value },
            option.label
          )
        )
      ),
    Space,
    Typography: { Text },
  }
})

vi.mock('@ant-design/icons', () => ({
  SaveOutlined: () => null,
}))

import HazardLedgerEditDrawer from './HazardLedgerEditDrawer'
import type { HazardIdentification } from '@/types/safety'

const RECORD: HazardIdentification = {
  id: 'hid-1',
  hazard_id_no: 'IMP-ABC123',
  department: '101-102车间',
  position: '消毒',
  production_step: '罐内发酵',
  specific_activity: '打开进料阀门',
  hazard_type: '常规作业',
  possible_accident: '其他伤害',
  unsafe_behavior: '管道憋压',
  l_inherent: 1,
  e_inherent: 6,
  c_inherent: 1,
  d_inherent: 6,
  inherent_risk_level: 'level_4',
  existing_engineering_controls: '加防护罩',
  existing_management_controls: '定期检查',
  existing_ppe: '手套',
  existing_emergency_measures: '应急卡',
  ai_node_progress: 'completed',
  overall_status: 'completed',
  script1_review_status: 'approved',
  script2_review_status: 'approved',
  script3_review_status: 'approved',
  script4_review_status: 'approved',
  script5_review_status: 'approved',
  script6_review_status: 'approved',
  script7_review_status: 'approved',
  created_at: '2026-10-20T00:00:00Z',
  updated_at: '2026-10-20T00:00:00Z',
  notes: '来源：导入《清单.xlsx》',
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement {
  const buttons = Array.from(container.querySelectorAll('button'))
  const matched = buttons.find((btn) => btn.textContent?.includes(text))
  if (!matched) {
    throw new Error(`button ${text} not found`)
  }
  return matched as HTMLButtonElement
}

function setValue(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto =
    input.tagName === 'TEXTAREA'
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('HazardLedgerEditDrawer', () => {
  let container: HTMLDivElement
  let root: Root
  const onClose = vi.fn()
  const onSaved = vi.fn()

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

  function render() {
    act(() => {
      root.render(
        <HazardLedgerEditDrawer
          record={RECORD}
          open
          onClose={onClose}
          onSaved={onSaved}
        />
      )
    })
  }

  it('编辑危险源描述并保存，提交变更字段并回调刷新', async () => {
    actions.updateHazardIdentification.mockResolvedValue({ code: 200 })
    render()

    const textareas = container.querySelectorAll('textarea')
    const hazardTextarea = Array.from(textareas).find(
      (ta) => (ta as HTMLTextAreaElement).value === '管道憋压'
    ) as HTMLTextAreaElement
    await act(async () => {
      setValue(hazardTextarea, '管道憋压伤人')
    })

    await act(async () => {
      findButton(container, '保存').click()
    })

    expect(actions.updateHazardIdentification).toHaveBeenCalledTimes(1)
    const [calledId, payload] = actions.updateHazardIdentification.mock.calls[0]
    expect(calledId).toBe('hid-1')
    expect(payload.unsafe_behavior).toBe('管道憋压伤人')
    expect(payload.department).toBe('101-102车间')
    expect(payload.inherent_risk_level).toBe('level_4')
    expect(ui.message.success).toHaveBeenCalledWith('保存成功')
    expect(onSaved).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('修改 L/E/C 联动重算 D 与等级', async () => {
    render()

    // 按位置取 L/E/C/D 输入（L=1, E=6, C=1, D=6）
    const numbers = Array.from(
      container.querySelectorAll('input[type="number"]')
    ) as HTMLInputElement[]
    expect(numbers.length).toBeGreaterThanOrEqual(4)
    const [lInput, , cInput, dInput] = numbers
    expect(lInput.value).toBe('1')
    expect(dInput.value).toBe('6')

    await act(async () => {
      setValue(lInput, '10')
    })
    // L=10, E=6, C=1 → D=60 → level_4
    expect(dInput.value).toBe('60')

    // 继续改 C=7 → D=420 → level_1
    await act(async () => {
      setValue(cInput, '7')
    })
    const dAfter = container.querySelectorAll('input[type="number"]')
    const dValue = Array.from(dAfter).find(
      (input) => Number((input as HTMLInputElement).value) === 420
    )
    expect(dValue).toBeTruthy()
    const selects = Array.from(
      container.querySelectorAll('select')
    ) as HTMLSelectElement[]
    const levelSelect = selects.find((select) =>
      Array.from(select.options).some((option) => option.value === 'level_1')
    )
    expect(levelSelect?.value).toBe('level_1')
  })

  it('保存失败时提示且不关闭抽屉', async () => {
    actions.updateHazardIdentification.mockResolvedValue({
      code: 500,
      message: '服务器错误',
    })
    render()

    await act(async () => {
      findButton(container, '保存').click()
    })

    expect(ui.message.error).toHaveBeenCalledWith('服务器错误')
    expect(onClose).not.toHaveBeenCalled()
    expect(onSaved).not.toHaveBeenCalled()
  })
})
