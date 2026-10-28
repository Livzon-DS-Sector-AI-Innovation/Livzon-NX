/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  getSpecialOperationReports: vi.fn(),
  getSpecialOperationLedgerStats: vi.fn(),
}))

vi.mock('@/actions/safety', async () => {
  const actual = await vi.importActual<typeof import('@/actions/safety')>(
    '@/actions/safety'
  )
  return {
    ...actual,
    getSpecialOperationReports: mocks.getSpecialOperationReports,
    getSpecialOperationLedgerStats: mocks.getSpecialOperationLedgerStats,
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    AimOutlined: Icon,
    AlertOutlined: Icon,
    CarryOutOutlined: Icon,
    CheckCircleOutlined: Icon,
    ClockCircleOutlined: Icon,
    CloseCircleOutlined: Icon,
    DeleteOutlined: Icon,
    DropboxOutlined: Icon,
    EditOutlined: Icon,
    EnvironmentOutlined: Icon,
    ExpandOutlined: Icon,
    ExportOutlined: Icon,
    EyeOutlined: Icon,
    FireOutlined: Icon,
    PlusOutlined: Icon,
    RobotOutlined: Icon,
    SafetyCertificateOutlined: Icon,
    SearchOutlined: Icon,
    SendOutlined: Icon,
    ThunderboltOutlined: Icon,
    ToolOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown> & { children?: ReactNode }

  const Box = ({ children }: AnyProps) =>
    createElement('div', null, children as ReactNode)
  const Button = ({ children, onClick }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', onClick: onClick as never },
      children as ReactNode
    )
  const Text = ({ children }: AnyProps) =>
    createElement('span', null, children as ReactNode)
  const RangePicker = ({ onChange }: AnyProps) =>
    createElement('input', {
      'data-range-picker': 'true',
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () =>
          (onChange as ((value: null) => void) | undefined)?.(null)
      },
    })
  const Table = Box

  return {
    App: { useApp: () => ({ message: mocks.message }) },
    Button,
    Card: Box,
    Col: Box,
    DatePicker: Object.assign(() => null, { RangePicker }),
    Descriptions: Object.assign(Box, { Item: Box }),
    Drawer: Box,
    Form: Object.assign(Box, {
      Item: Box,
      useForm: () => [
        {
          setFieldsValue: vi.fn(),
          validateFields: vi.fn(async () => ({})),
          resetFields: vi.fn(),
        },
      ],
    }),
    Input: Object.assign(
      ({ value, onChange, placeholder }: AnyProps) =>
        createElement('input', {
          value: (value as string) ?? '',
          placeholder: placeholder as string,
          ref: (node: HTMLInputElement | null) => {
            if (!node) return
            node.onchange = () =>
              (onChange as unknown as (event: unknown) => void)?.({
                target: { value: node.value },
              })
          },
        }),
      { TextArea: Box }
    ),
    Modal: Box,
    Row: Box,
    Select: Box,
    Space: Box,
    Statistic: Box,
    Switch: Box,
    Table,
    Tag: Text,
    Tooltip: Box,
    Typography: { Text },
  }
})

import SpecialOpsManagement from './SpecialOpsManagement'

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

let root: Root | undefined
let container: HTMLDivElement | undefined

function render(props: Record<string, unknown> = {}) {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => {
    root?.render(createElement(SpecialOpsManagement, { initialStats: [], ...props }))
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getSpecialOperationReports.mockResolvedValue({
    code: 200,
    data: [],
    meta: { total: 0 },
  })
  mocks.getSpecialOperationLedgerStats.mockResolvedValue({
    code: 200,
    data: [],
  })
})

afterEach(() => {
  if (root) act(() => root?.unmount())
  container?.remove()
  root = undefined
  container = undefined
})

describe('SpecialOpsManagement 默认筛选', () => {
  it('首屏直出数据时不重复请求（服务端已按当天过滤）', async () => {
    render({
      initialData: [
        {
          id: 'r1',
          report_no: '202610130743',
          operation_type: 'hot_work',
          operation_level: 'grade2',
          status: 'submitted',
          is_critical: false,
        } as never,
      ],
      initialTotal: 1,
      initialStats: [{ operation_type: 'hot_work', count: 1, critical_count: 0 } as never],
      initialDateFilter: '2026-10-14',
    })
    await settle()

    expect(mocks.getSpecialOperationReports).not.toHaveBeenCalled()
    expect(mocks.getSpecialOperationLedgerStats).not.toHaveBeenCalled()
  })

  it('无服务端数据时客户端兜底请求当天范围，仪表盘同口径', async () => {
    render()
    await settle()

    // 组件用 dayjs()（运行时本地时区）算「今天」，期望值同口径；
    // 显式 Asia/Shanghai 会在 UTC 16:00-24:00（北京次日凌晨）窗口与组件分歧
    const today = new Date().toLocaleDateString('sv-SE')
    expect(mocks.getSpecialOperationReports).toHaveBeenCalledWith(
      expect.objectContaining({ date_from: today, date_to: today })
    )
    expect(mocks.getSpecialOperationLedgerStats).toHaveBeenCalledWith(
      expect.objectContaining({ date_from: today, date_to: today })
    )
  })

  it('清空日期范围后查看全部', async () => {
    render()
    await settle()

    const picker = container?.querySelector(
      '[data-range-picker]'
    ) as HTMLInputElement
    expect(picker).toBeTruthy()
    act(() => {
      picker.dispatchEvent(new Event('change'))
    })
    await settle()

    const lastCall = mocks.getSpecialOperationReports.mock.calls.at(-1)
      ?.[0] as Record<string, unknown>
    expect(lastCall.date_from).toBeUndefined()
    expect(lastCall.date_to).toBeUndefined()
  })

  it('台账只读：不渲染新建报备与审批流程入口', async () => {
    render()
    await settle()

    const buttons = Array.from(
      container?.querySelectorAll('button') ?? []
    ).map((button) => button.textContent)
    expect(buttons).not.toContain('新建报备')
    expect(buttons).not.toContain('提交')
    expect(buttons).not.toContain('审批')
    expect(buttons).not.toContain('驳回')
    expect(buttons).not.toContain('删除')
  })

  it('关键作业由规则判定：无人工开关、无审批时间列', async () => {
    render()
    await settle()

    // 人工开关已移除（关键作业按作业类型+级别自动判定）
    expect(container?.querySelectorAll('input[type="checkbox"]').length).toBe(0)
    // 审批在飞书完成，本地无审批时间列
    expect(container?.textContent).not.toContain('审批时间')
  })
})
