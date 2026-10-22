/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  submitFireEquipmentInspection: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  submitFireEquipmentInspection: mocks.submitFireEquipmentInspection,
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ message, description }: { message: ReactNode; description?: ReactNode }) =>
      createElement('div', { 'data-notice': String(message) }, description),
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown>
  const Box = ({ children, title }: AnyProps) =>
    createElement('div', null, title as ReactNode, children as ReactNode)
  const Button = ({ children, onClick, disabled, loading }: AnyProps) =>
    createElement(
      'button',
      {
        type: 'button',
        disabled: Boolean(disabled || loading),
        onClick: onClick as never,
      },
      children as ReactNode
    )
  const changeHandler = (onChange: unknown) => (node: HTMLInputElement | null) => {
    if (!node) return
    node.oninput = () => (onChange as (event: { target: { value: string } }) => void)?.({ target: { value: node.value } })
  }
  const Input = Object.assign(
    ({ value, onChange, placeholder }: AnyProps) =>
      createElement('input', {
        value: (value as string) ?? '',
        placeholder: placeholder as string,
        ref: changeHandler(onChange),
      }),
    {
      TextArea: ({ value, onChange, placeholder }: AnyProps) =>
        createElement('textarea', {
          value: (value as string) ?? '',
          placeholder: placeholder as string,
          ref: (node: HTMLTextAreaElement | null) => {
            if (!node) return
            node.oninput = () =>
              (onChange as (event: { target: { value: string } }) => void)?.({ target: { value: node.value } })
          },
        }),
    }
  )
  const Segmented = ({ options, value, onChange }: AnyProps) =>
    createElement(
      'span',
      null,
      (options as Array<{ label: string; value: string }>).map((option) =>
        createElement(
          'button',
          {
            key: option.value,
            type: 'button',
            'data-segmented': String(option.value),
            'data-active': String(option.value === value),
            onClick: () => (onChange as (v: string) => void)?.(option.value),
          },
          option.label
        )
      )
    )
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)

  return {
    Button,
    Card: Box,
    Input,
    Segmented,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(({ children }: AnyProps) => createElement('div', null, children as ReactNode), {
      Text,
      Title: Text,
    }),
    message: mocks.message,
  }
})

import FireInspectionScanView from './FireInspectionScanView'

const PAGE_KEY = 'safety:emergency-accident:fire-equipment-inspection'

const DETAIL = {
  equipment: {
    id: 'eq-1',
    equipment_type: 'hydrant',
    equipment_type_label: '消防栓',
    equipment_no: 'XFS-101',
    department: '101一车间',
    location: '一楼楼梯口',
    tab_name: '主表',
    table_id: 'tbl1',
    record_id: 'rec1',
    fields: { '型号': 'MFZ/ABC4', '干粉': '4kg' },
    expiry_date: '2026-11-09',
    expiry_days_left: 20,
    expiry_status: 'expiring',
    last_inspected_at: null,
    last_inspection_result: null,
    month_status: 'uninspected',
    last_synced_at: null,
  },
  checklist: [
    { key: 'signage', label: '消防栓箱有明显的消防栓字样及说明或标识。' },
    { key: 'passage', label: '消防栓箱附近1米范围内，通道无杂物阻挡，箱门便于开启。' },
    { key: 'accessories', label: '消防栓箱内水枪、水带、消防栓阀门配件齐全。' },
  ],
  recent_inspections: [],
}

function renderView(props: Partial<Parameters<typeof FireInspectionScanView>[0]> = {}) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      createElement(FireInspectionScanView, {
        pageKey: PAGE_KEY,
        inspectorName: '张三',
        detail: DETAIL as never,
        error: null,
        ...props,
      })
    )
  })
  return { container, root }
}

async function click(
  container: HTMLElement,
  target: string | HTMLElement
) {
  const button =
    typeof target === 'string' ? container.querySelector(target) : target
  expect(button).not.toBeNull()
  await act(async () => {
    button!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

describe('FireInspectionScanView', () => {
  let root: Root | null = null
  let container: HTMLElement | null = null

  beforeEach(() => {
    mocks.message.success.mockClear()
    mocks.message.warning.mockClear()
    mocks.message.error.mockClear()
    mocks.submitFireEquipmentInspection.mockReset()
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = null
    container = null
  })

  it('renders equipment info and full checklist', () => {
    const view = renderView()
    root = view.root
    container = view.container
    expect(container.textContent).toContain('XFS-101')
    expect(container.textContent).toContain('消防栓箱有明显的消防栓字样')
    // 扫码可见多维表格中的器材信息
    expect(container.textContent).toContain('器材信息（多维表格）')
    expect(container.textContent).toContain('MFZ/ABC4')
    // 有效期临近时显示提醒标示与到期日
    expect(container.textContent).toContain('有效期仅剩20天')
    expect(container.textContent).toContain('有效期至：2026-11-09')
    // 检查卡整卡展示
    const segmented = container.querySelectorAll('[data-segmented="ok"]')
    expect(segmented.length).toBe(3)
  })

  it('submits all items ok by default with scan source', async () => {
    mocks.submitFireEquipmentInspection.mockResolvedValue({
      code: 200,
      data: {
        id: 'insp-1',
        result: 'pass',
        inspector_name: '张三',
        items: [],
        failed_items: [],
        inspected_at: '2026-10-20T02:00:00Z',
      },
    })
    const view = renderView()
    root = view.root
    container = view.container
    const submitButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('提交点检结果')
    )
    expect(submitButton).toBeDefined()
    await click(container, submitButton!)
    expect(mocks.submitFireEquipmentInspection).toHaveBeenCalledWith(
      expect.objectContaining({
        pageKey: PAGE_KEY,
        equipmentId: 'eq-1',
        data: expect.objectContaining({
          source: 'scan',
          items: [
            { key: 'signage', result: 'ok', remark: null },
            { key: 'passage', result: 'ok', remark: null },
            { key: 'accessories', result: 'ok', remark: null },
          ],
        }),
      })
    )
    expect(mocks.message.success).toHaveBeenCalledWith('点检提交成功')
  })

  it('requires abnormal action when any item fails', async () => {
    const view = renderView()
    root = view.root
    container = view.container

    // 第一项改为不合格 → 出现异常处理措施输入
    await click(container, '[data-segmented="fail"]')
    const textarea = container.querySelector('textarea')
    expect(textarea).not.toBeNull()

    // 未填异常处理措施时提交被拦截
    const submitButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('提交点检结果')
    )
    expect(submitButton).toBeDefined()
    await act(async () => {
      submitButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(mocks.message.warning).toHaveBeenCalled()
    expect(mocks.submitFireEquipmentInspection).not.toHaveBeenCalled()
  })

  it('shows error notice when detail failed to load', () => {
    const view = renderView({ detail: null, error: '器材不存在' })
    root = view.root
    container = view.container
    expect(container.querySelector('[data-notice="器材信息加载失败"]')).not.toBeNull()
  })
})
