/* @vitest-environment happy-dom */

// 新建工单抽屉：责任人新建可选、紧急警示条、dispatched 提示分叉与提交流程。

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const store = vi.hoisted(() => ({
  workOrderDrawerOpen: true,
  editingWorkOrder: null as Record<string, unknown> | null,
  closeWorkOrderDrawer: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  createWorkOrder: vi.fn(),
  updateWorkOrder: vi.fn(),
}))

vi.mock('@/stores/equipment', () => ({ useEquipmentStore: () => store }))
vi.mock('@/actions/equipment', () => actions)
vi.mock('@/lib/api/equipment-client', () => ({
  fetchAllUsersClient: vi.fn().mockResolvedValue([
    { name: '张三', employee_no: 'E1', user_id: 'u1' },
  ]),
}))

const message = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const passthrough = ({ children }: { children?: unknown }) =>
    createElement('div', null, children as never)
  // Drawer/Form.Item 的 extra 挂操作按钮与字段提示，需一并渲染
  const withExtra = ({ children, extra }: { children?: unknown; extra?: unknown }) =>
    createElement('div', null, children as never, extra as never)
  const Drawer = withExtra
  const Form = Object.assign(
    ({ children }: { children?: unknown }) =>
      createElement('form', null, children as never),
    {
      Item: withExtra,
      // useWatch 固定返回"紧急"：覆盖紧急警示分支
      useWatch: () => '紧急',
      useForm: () => [
        {
          validateFields: async () => ({
            equipment_id: 'eq-1',
            order_type: '故障维修',
            priority: '紧急',
            fault_description: '泄漏',
          }),
          setFieldsValue: vi.fn(),
        },
      ],
    },
  )
  const Select = passthrough
  const Input = Object.assign(passthrough, { TextArea: passthrough })
  const Button = ({ children, onClick }: { children?: unknown; onClick?: () => void }) =>
    createElement('button', { onClick, 'data-testid': 'drawer-submit' }, children as never)
  const Space = passthrough
  const App = Object.assign(passthrough, { useApp: () => ({ message }) })
  const theme = { useToken: () => ({ token: { colorInfoBg: '', colorInfo: '', colorSuccessBg: '', colorSuccess: '', colorWarningBg: '', colorWarning: '', colorErrorBg: '', colorError: '', borderRadiusLG: 8, colorText: '' } }) }
  const Typography = Object.assign(passthrough, { Text: passthrough, Title: passthrough, Paragraph: passthrough })
  // PlatformNotice 内部还会引用 Alert/Modal/Button
  const Alert = passthrough
  const Modal = Object.assign(passthrough, { useModal: () => ({ modal: {} }) })
  return { Drawer, Form, Input, Select, Button, Space, App, theme, Typography, Alert, Modal }
})

import { WorkOrderDrawer } from './WorkOrderDrawer'

describe('WorkOrderDrawer', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    store.editingWorkOrder = null
    store.closeWorkOrderDrawer.mockClear()
    actions.createWorkOrder.mockReset()
    actions.updateWorkOrder.mockReset()
    message.success.mockClear()
    message.warning.mockClear()
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  const render = () =>
    act(async () => {
      root.render(
        <WorkOrderDrawer
          equipments={[
            {
              id: 'eq-1',
              name: '离心泵A',
              equipment_no: 'LB-1',
            } as never,
          ]}
          symptoms={[]}
        />,
      )
      await Promise.resolve()
    })

  // Drawer extra 有"取消/提交"两个按钮，按文案取提交
  const findSubmitButton = () => {
    const btn = Array.from(
      container.querySelectorAll('button'),
    ).find((el) => el.textContent?.includes('提交')) as HTMLElement
    expect(btn).toBeTruthy()
    return btn
  }

  it('新建模式：责任人可选提示与紧急警示条渲染', async () => {
    await render()
    const text = container.textContent ?? ''
    expect(text).toContain('留空由维修群接单指派')
    // Form.useWatch 返回"紧急" → PlatformNotice 警示条
    expect(text).toContain('紧急工单要求维修人员 5 分钟内接单')
  })

  it('提交后按 dispatched=true 提示已派发', async () => {
    actions.createWorkOrder.mockResolvedValue({ dispatched: true })
    await render()

    const submit = findSubmitButton()
    await act(async () => {
      submit.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(actions.createWorkOrder).toHaveBeenCalledTimes(1)
    expect(message.success).toHaveBeenCalledWith('工单已创建，维修群已收到派单卡片')
    expect(message.warning).not.toHaveBeenCalled()
    expect(store.closeWorkOrderDrawer).toHaveBeenCalled()
  })

  it('提交后按 dispatched=false 提示电话通知', async () => {
    actions.createWorkOrder.mockResolvedValue({ dispatched: false })
    await render()

    const submit = findSubmitButton()
    await act(async () => {
      submit.click()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(message.warning).toHaveBeenCalledWith(
      '工单已创建，但未配置维修群，请电话通知维修',
    )
    expect(message.success).not.toHaveBeenCalled()
  })
})
