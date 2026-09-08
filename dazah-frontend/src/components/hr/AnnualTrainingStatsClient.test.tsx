/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchTrainingLedgersByDept: vi.fn(),
  fetchSessionDocuments: vi.fn(),
  fetchTrainingSession: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  updateTrainingLedger: vi.fn(),
  deleteTrainingLedger: vi.fn(),
  createSecondLevelTraining: vi.fn(),
  generateOralExamResult: vi.fn(),
  generatePracticalExamResult: vi.fn(),
  createTrainingLedger: vi.fn(),
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
}))
vi.mock('./ImportExamScoresModal', () => ({ default: () => null }))
vi.mock('./trainingDept', () => ({
  unify201Dept: (value: string) => value,
  ensureDeptMappings: vi.fn(() => Promise.resolve()),
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
  const Input = ({ defaultValue }: { defaultValue?: unknown }) => createElement('input', { defaultValue: String(defaultValue ?? '') })
  const Select = ({ options = [] }: { options?: Array<{ label: ReactNode; value: string }> }) =>
    createElement('select', null, options.map((option) => createElement('option', { key: option.value, value: option.value }, option.label)))
  const Modal = ({ open, children }: { open?: boolean; children?: ReactNode }) => (open ? createElement('div', null, children) : null)
  return {
    App: { useApp: () => ({ message: ui.message, modal: ui.modal }) },
    Alert: Wrapper,
    Button,
    DatePicker: () => createElement('input', { type: 'date' }),
    Descriptions,
    Divider: Wrapper,
    Drawer,
    Form,
    Input,
    Modal,
    Popconfirm: ({ children }: { children?: ReactNode }) => createElement('span', null, children),
    Select,
    Space: Wrapper,
    Spin: Wrapper,
    Switch: ({ checked }: { checked?: boolean }) => createElement('input', { type: 'checkbox', checked: !!checked }),
    Table,
    Tag: Wrapper,
    Tooltip: Wrapper,
  }
})

import AnnualTrainingStatsClient from './AnnualTrainingStatsClient'

describe('AnnualTrainingStatsClient', () => {
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

  it('shows attendance count in detail drawer while keeping it out of table columns', async () => {
    const ledger = {
      id: 'ledger-1',
      employee_number: 'E-1',
      training_date: '2026-08-20',
      training_subject: 'GMP培训',
      training_content: 'GMP培训内容',
      training_datetime: '2026-08-20 09:00',
      duration_hours: 2,
      teaching_dept: '质量部',
      instructor: '张三',
      level_category: '一级',
      involved_depts: '质量部',
      trainees: '李四、王五、赵六',
      attendance_count: 3,
      training_type: '质量培训',
      ledger_assessment_method: '笔试',
      plan_source: '年度计划',
      drug_category: '人药',
      score_summary: '合格',
      remarks: '备注',
      source_type: 'session',
      session_id: 'session-1',
    }
    api.fetchTrainingLedgersByDept.mockResolvedValue({ code: 200, message: 'ok', data: [ledger], meta: { page: 1, page_size: 500, total: 1 } })
    api.fetchSessionDocuments.mockResolvedValue([])
    api.fetchTrainingSession.mockResolvedValue({ department: '质量部' })
    act(() => {
      root.render(
        createElement(AnnualTrainingStatsClient, {
          department: '质量部',
          dateFrom: '2026-01-01',
          dateTo: '2026-12-31',
          periodLabel: '全年',
          printRequest: 0,
        } as never),
      )
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    // 表格页不出现"参训人员统计"列头，但详情按钮可打开
    expect(container.textContent).toContain('GMP培训内容')
    expect(container.textContent).not.toContain('参训人员统计')
    const detailButton = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('详情'))
    expect(detailButton).toBeTruthy()
    act(() => { detailButton?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await act(async () => {
      await Promise.resolve()
    })
    // 详情抽屉展示参训人员统计（3 人）
    expect(container.textContent).toContain('参训人员统计')
    expect(container.textContent).toContain('3 人')
  })
})
