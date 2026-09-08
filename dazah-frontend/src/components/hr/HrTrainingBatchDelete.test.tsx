/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchTrainingLedgersByDept: vi.fn(),
  fetchEsgRecordsByDept: vi.fn(),
  fetchEsgFilterOptions: vi.fn(),
  fetchSessionDocuments: vi.fn(),
  fetchTrainingSession: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  updateTrainingLedger: vi.fn(),
  deleteTrainingLedger: vi.fn(),
  batchDeleteTrainingLedgers: vi.fn(),
  createSecondLevelTraining: vi.fn(),
  generateOralExamResult: vi.fn(),
  generatePracticalExamResult: vi.fn(),
  createTrainingLedger: vi.fn(),
  updateEsgTrainingRecord: vi.fn(),
  deleteEsgTrainingRecord: vi.fn(),
  batchDeleteEsgTrainingRecords: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  modal: { confirm: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

vi.mock('@/lib/api/hr', () => api)
vi.mock('@/lib/api/client/hr', () => api)
vi.mock('@/actions/hr', () => actions)
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@ant-design/icons', () => ({
  EditOutlined: () => null,
  DeleteOutlined: () => null,
  EyeOutlined: () => null,
  FolderOpenOutlined: () => null,
  DownloadOutlined: () => null,
  FileExcelOutlined: () => null,
  PlusOutlined: () => null,
  FilterOutlined: () => null,
}))
vi.mock('./ImportExamScoresModal', () => ({ default: () => null }))

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
  // 表格：数据行 + rowSelection 模拟勾选按钮（select-<rowKey>）
  const Table = ({
    columns = [],
    dataSource = [],
    rowKey,
    rowSelection,
  }: {
    columns?: Array<{ title?: ReactNode; dataIndex?: string; render?: (value: unknown, record: Record<string, unknown>) => ReactNode }>
    dataSource?: Array<Record<string, unknown>>
    rowKey?: string
    rowSelection?: { onChange?: (keys: Array<string | number>) => void }
  }) => {
    const selects = rowSelection?.onChange
      ? dataSource.map((record) =>
          createElement(
            'button',
            { key: `sel-${String(record[rowKey ?? 'id'])}`, onClick: () => rowSelection.onChange?.([String(record[rowKey ?? 'id'])]) },
            `select-${String(record[rowKey ?? 'id'])}`,
          ),
        )
      : []
    return createElement(
      'table',
      null,
      ...selects,
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
  }
  const Drawer = ({ open, children, title }: { open?: boolean; children?: ReactNode; title?: ReactNode }) =>
    open ? createElement('div', { 'data-testid': 'drawer' }, title, children) : null
  const Descriptions = ({ children }: { children?: ReactNode }) => createElement('dl', null, children)
  const DescriptionsItem = ({ label, children }: { label?: ReactNode; children?: ReactNode }) =>
    createElement('div', null, label, '：', children)
  ;(Descriptions as unknown as Record<string, unknown>).Item = DescriptionsItem
  const Form = ({ children }: { children?: ReactNode }) => createElement('form', null, children)
  const formInstance = {
    resetFields: () => undefined,
    validateFields: () => Promise.resolve({}),
    setFieldsValue: () => undefined,
    getFieldsValue: () => ({}),
  }
  ;(Form as unknown as Record<string, unknown>).useForm = () => [formInstance]
  const Input = (props: Record<string, unknown>) => createElement('input', props)
  ;(Input as unknown as Record<string, unknown>).TextArea = (props: Record<string, unknown>) =>
    createElement('textarea', props)
  return {
    App: { useApp: () => ({ message: ui.message, modal: ui.modal }) },
    Button,
    DatePicker: () => createElement('input', { type: 'date' }),
    Descriptions,
    Drawer,
    Form,
    Input,
    InputNumber: (props: Record<string, unknown>) => createElement('input', props),
    Modal: ({ open, children }: { open?: boolean; children?: ReactNode }) =>
      open ? createElement('div', null, children) : null,
    Popconfirm: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
    Select: ({ options = [] }: { options?: Array<{ label: ReactNode; value: string }> }) =>
      createElement(
        'select',
        null,
        options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label)),
      ),
    Space: Wrapper,
    Spin: Wrapper,
    Switch: ({ checked }: { checked?: boolean }) => createElement('input', { type: 'checkbox', checked: !!checked }),
    Table,
    Tag: Wrapper,
    Tooltip: Wrapper,
  }
})

import AnnualTrainingStatsClient from './AnnualTrainingStatsClient'
import EsgTrainingReportClient from './EsgTrainingReportClient'

const LEDGER_PROPS = {
  department: '201二车间（DR）',
  dateFrom: '2026-01-01',
  dateTo: '2026-12-31',
  periodLabel: '全年',
  printRequest: 0,
}

const ESG_PROPS = { ...LEDGER_PROPS }

function findButton(scope: HTMLElement, text: string) {
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
}

describe('培训台账批量删除（两个 tab）', () => {
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

  it('年度培训统计表：勾选后批量删除走二次确认并调用 ids 数组', async () => {
    api.fetchTrainingLedgersByDept.mockResolvedValue({
      code: 200,
      data: [
        {
          id: 'ledger-1',
          training_date: '2026-08-20',
          training_subject: 'GMP培训',
          training_content: 'GMP培训内容',
          training_datetime: '2026-08-20 09:00',
          duration_hours: 2,
          teaching_dept: '201二车间',
          instructor: '张三',
          trainees: '李四',
          is_presented: true,
        },
      ],
      meta: { page: 1, page_size: 50, total: 1 },
    })
    actions.batchDeleteTrainingLedgers.mockResolvedValue({
      code: 200,
      message: '已删除1条培训台账记录',
      data: { deleted: 1, failed: [] },
    })

    act(() => {
      root.render(createElement(AnnualTrainingStatsClient, LEDGER_PROPS as never))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    // 未勾选时按钮禁用
    const batchButton = findButton(container, '批量删除')
    expect(batchButton).toBeTruthy()
    expect(batchButton?.disabled).toBe(true)

    // 勾选一行 → 按钮可用并显示已选条数
    const selectButton = findButton(container, 'select-ledger-1')
    act(() => {
      selectButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(findButton(container, '已选 1 条')).toBeTruthy()

    // 点击批量删除 → 二次确认内容含条数
    act(() => {
      findButton(container, '批量删除')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(ui.modal.confirm).toHaveBeenCalledTimes(1)
    const confirm = ui.modal.confirm.mock.calls[0][0] as {
      content: string
      onOk: () => Promise<void>
    }
    expect(confirm.content).toContain('1 条')

    // 确认 → 调用批量删除 action（ids 数组）并提示成功
    await act(async () => {
      await confirm.onOk()
    })
    expect(actions.batchDeleteTrainingLedgers).toHaveBeenCalledWith(['ledger-1'])
    expect(ui.message.success).toHaveBeenCalledWith('已删除1条培训台账记录')
    expect(actions.deleteTrainingLedger).not.toHaveBeenCalled()
  })

  it('ESG 培训报表：勾选后批量删除走二次确认并调用 ids 数组', async () => {
    api.fetchEsgRecordsByDept.mockResolvedValue({
      code: 200,
      data: [
        {
          id: 'esg-1',
          training_date: '2026-08-20',
          training_name: 'ESG质量培训',
          training_method: '线下',
          caliber: '部门组织',
          training_type: '质量类',
          employee_name: '李四',
          department: '201二车间（DR）',
        },
      ],
      meta: { page: 1, page_size: 50, total: 1 },
    })
    api.fetchEsgFilterOptions.mockResolvedValue({})
    actions.batchDeleteEsgTrainingRecords.mockResolvedValue({
      code: 200,
      message: '已删除1条ESG培训记录',
      data: { deleted: 1, failed: [] },
    })

    act(() => {
      root.render(createElement(EsgTrainingReportClient, ESG_PROPS as never))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    const selectButton = findButton(container, 'select-esg-1')
    expect(selectButton).toBeTruthy()
    act(() => {
      selectButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(findButton(container, '已选 1 条')).toBeTruthy()

    act(() => {
      findButton(container, '批量删除')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(ui.modal.confirm).toHaveBeenCalledTimes(1)
    const confirm = ui.modal.confirm.mock.calls[0][0] as {
      content: string
      onOk: () => Promise<void>
    }
    expect(confirm.content).toContain('1 条')

    await act(async () => {
      await confirm.onOk()
    })
    expect(actions.batchDeleteEsgTrainingRecords).toHaveBeenCalledWith(['esg-1'])
    expect(ui.message.success).toHaveBeenCalledWith('已删除1条ESG培训记录')
    expect(actions.deleteEsgTrainingRecord).not.toHaveBeenCalled()
  })

  it('ESG 批量删除部分失败：警告提示失败条数', async () => {
    api.fetchEsgRecordsByDept.mockResolvedValue({
      code: 200,
      data: [
        { id: 'esg-1', training_date: '2026-08-20', training_name: 'ESG质量培训', employee_name: '李四' },
      ],
      meta: { page: 1, page_size: 50, total: 1 },
    })
    api.fetchEsgFilterOptions.mockResolvedValue({})
    actions.batchDeleteEsgTrainingRecords.mockResolvedValue({
      code: 200,
      message: 'ok',
      data: { deleted: 0, failed: ['esg-1'] },
    })

    act(() => {
      root.render(createElement(EsgTrainingReportClient, ESG_PROPS as never))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    act(() => {
      findButton(container, 'select-esg-1')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(async () => {
      await Promise.resolve()
    })
    act(() => {
      findButton(container, '批量删除')?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const confirm = ui.modal.confirm.mock.calls[0][0] as { onOk: () => Promise<void> }
    await act(async () => {
      await confirm.onOk()
    })
    expect(ui.message.warning).toHaveBeenCalledWith('已删除 0 条，1 条不存在或已删除')
  })
})
