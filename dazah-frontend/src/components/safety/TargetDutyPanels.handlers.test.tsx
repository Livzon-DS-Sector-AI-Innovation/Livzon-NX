/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 目标签约/履职评估面板的 handler 级用例：stub antd 使 Form 校验与
 * Modal 提交直接执行提交体（真实 antd 的交互流由 TargetDutyPanels.test 覆盖）。
 */

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  getSafetyTargetAgreements: vi.fn(),
  getSafetyTargetAgreementStats: vi.fn(),
  createSafetyTargetAgreement: vi.fn(),
  updateSafetyTargetAgreement: vi.fn(),
  deleteSafetyTargetAgreement: vi.fn(),
  importAgreementSigns: vi.fn(),
  getSafetyDutyAssessments: vi.fn(),
  getSafetyDutyAssessmentStats: vi.fn(),
  getSafetyDutyAssessmentTemplate: vi.fn(),
  createSafetyDutyAssessment: vi.fn(),
  updateSafetyDutyAssessment: vi.fn(),
  deleteSafetyDutyAssessment: vi.fn(),
  canOperate: true,
  canDelete: true,
}))

vi.mock('@/actions/safety', () => ({
  getSafetyTargetAgreements: mocks.getSafetyTargetAgreements,
  getSafetyTargetAgreementStats: mocks.getSafetyTargetAgreementStats,
  createSafetyTargetAgreement: mocks.createSafetyTargetAgreement,
  updateSafetyTargetAgreement: mocks.updateSafetyTargetAgreement,
  deleteSafetyTargetAgreement: mocks.deleteSafetyTargetAgreement,
  importAgreementSigns: mocks.importAgreementSigns,
  getSafetyDutyAssessments: mocks.getSafetyDutyAssessments,
  getSafetyDutyAssessmentStats: mocks.getSafetyDutyAssessmentStats,
  getSafetyDutyAssessmentTemplate: mocks.getSafetyDutyAssessmentTemplate,
  createSafetyDutyAssessment: mocks.createSafetyDutyAssessment,
  updateSafetyDutyAssessment: mocks.updateSafetyDutyAssessment,
  deleteSafetyDutyAssessment: mocks.deleteSafetyDutyAssessment,
  downloadAgreementImportTemplate: vi.fn(),
  downloadDutyAssessmentImportTemplate: vi.fn(),
  importDutyAssessmentResults: vi.fn(),
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
    canView: true,
  }),
}))

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  type AnyProps = Record<string, unknown> & { children?: ReactNode }

  const Box = ({ children, title }: AnyProps) =>
    createElement('div', null, title as ReactNode, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode,
    )
  const useForm = () => [
    {
      setFieldsValue: vi.fn(),
      validateFields: vi.fn(async () => ({
        year: 2026,
        department: '101一车间',
        responsible_person: '张三',
        category: '部门级',
        goals_text: '杜绝事故',
        status: 'signed',
        quarter: 'Q1',
        assessor: '安环部',
        person_name: '张三',
        items: [],
      })),
      getFieldValue: vi.fn(() => '101一车间'),
      resetFields: vi.fn(),
    },
  ]
  const Form = Object.assign(
    ({ children }: AnyProps) => createElement('form', null, children as ReactNode),
    {
      Item: ({ children, label }: AnyProps) =>
        createElement('div', null, label as ReactNode, children as ReactNode),
      useForm,
      useWatch: () => undefined,
      List: ({ children }: AnyProps) =>
        createElement('div', null, children as ReactNode),
    },
  )
  return {
    App: Object.assign(({ children }: AnyProps) => createElement('div', null, children as ReactNode), {
      useApp: () => ({ message: mocks.message }),
    }),
    Button,
    Card: Box,
    Col: Box,
    DatePicker: Object.assign(() => createElement('input'), {
      RangePicker: () => createElement('input'),
    }),
    Form,
    Input: Object.assign(() => createElement('input'), {
      TextArea: () => createElement('textarea'),
      Search: ({ onSearch }: AnyProps) =>
        createElement('button', { type: 'button', onClick: onSearch as never }, 'search'),
    }),
    InputNumber: () => createElement('input'),
    Modal: ({ children, open, onOk }: AnyProps) =>
      createElement(
        'div',
        { 'data-modal-open': String(Boolean(open)) },
        open ? (children as ReactNode) : null,
        open && onOk
          ? createElement(
              'button',
              { type: 'button', 'data-modal-ok': 'y', onClick: onOk as never },
              '确定',
            )
          : null,
      ),
    Popconfirm: ({ children, onConfirm }: AnyProps) =>
      createElement(
        'span',
        null,
        children as ReactNode,
        onConfirm
          ? createElement(
              'button',
              { type: 'button', 'data-pop-ok': 'y', onClick: onConfirm as never },
              '确认',
            )
          : null,
      ),
    Row: Box,
    Select: () => createElement('select'),

    Segmented: ({ options, value, onChange }: AnyProps) =>
      createElement(
        'span',
        null,
        (options as Array<{ label: string; value: string }>).map((option) =>
          createElement('button', {
            key: option.value,
            type: 'button',
            'data-segmented': option.value,
            'data-active': String(option.value === value),
            onClick: () => (onChange as ((v: string) => void) | undefined)?.(option.value),
          }, option.label),
        ),
      ),
    Space: Box,
    Table: ({ columns, dataSource }: AnyProps) => {
      const cols = (columns ?? []) as Array<{
        dataIndex?: string
        render?: (value: unknown, row: Record<string, unknown>) => ReactNode
      }>
      const rows = (dataSource ?? []) as Array<Record<string, unknown>>
      return createElement(
        'tbody',
        null,
        rows.map((row, rowIndex) =>
          createElement(
            'tr',
            { key: String(row.id ?? rowIndex) },
            cols.map((column, columnIndex) => {
              const key = column.dataIndex ?? ''
              const cell: ReactNode = column.render
                ? column.render(row[key], row)
                : ((row[key] as ReactNode) ?? null)
              return createElement('td', { key: key || columnIndex }, cell)
            }),
          ),
        ),
      )
    },
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
      {
        Text: ({ children }: AnyProps) =>
          createElement('span', null, children as ReactNode),
        Title: ({ children }: AnyProps) =>
          createElement('h3', null, children as ReactNode),
      },
    ),
    message: mocks.message,
    Tooltip: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Upload: ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
  }
})

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ title, description }: { title?: ReactNode; description?: ReactNode }) =>
      createElement('div', null, title as ReactNode, description as ReactNode),
  }
})

import DutyAssessmentPanel from './DutyAssessmentPanel'
import TargetAgreementPanel from './TargetAgreementPanel'

const AGREEMENT = {
  id: 'a1',
  year: 2026,
  department: '101一车间',
  responsible_person: '张三',
  category: '部门级',
  goals_text: '杜绝重伤事故',
  status: 'signed',
  created_at: '2026-01-15T08:00:00',
}
const AGREEMENT_STATS = { total: 1, signed: 1, unsigned: 0, sign_rate: 100, departments: [] }
const ASSESSMENT = {
  id: 'd1',
  year: 2026,
  quarter: 'Q1',
  department: '101一车间',
  assessor: '安环部',
  person_name: '张三',
  total_score: 95,
  grade: '优秀',
  assessment_date: '2026-04-01',
  created_at: '2026-04-01T08:00:00',
}
const ASSESSMENT_STATS = { avg_score: 95, excellent: 1, departments: [] }

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 30))
}

describe('目标签约/履职评估 handler 流', () => {
  let root: Root | undefined
  let container: HTMLElement | undefined

  beforeEach(() => {
    mocks.getSafetyTargetAgreements.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { items: [AGREEMENT], total: 1 },
    })
    mocks.getSafetyTargetAgreementStats.mockResolvedValue({
      code: 200,
      message: 'success',
      data: AGREEMENT_STATS,
    })
    mocks.getSafetyDutyAssessments.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { items: [ASSESSMENT], total: 1 },
    })
    mocks.getSafetyDutyAssessmentStats.mockResolvedValue({
      code: 200,
      message: 'success',
      data: ASSESSMENT_STATS,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = undefined
    container = undefined
    vi.clearAllMocks()
  })

  function render(node: React.ReactNode) {
    act(() => {
      root!.render(node)
    })
  }

  const buttons = (text: string) =>
    Array.from(container!.querySelectorAll<HTMLButtonElement>('button')).filter((b) =>
      b.textContent?.includes(text),
    )

  it('签约：登记提交 → 创建调用；编辑提交 → 更新调用；删除确认', async () => {
    mocks.createSafetyTargetAgreement.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    mocks.updateSafetyTargetAgreement.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    mocks.deleteSafetyTargetAgreement.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    render(
      createElement(TargetAgreementPanel as never, {
        pageKey: 'k',
        initialAgreements: [AGREEMENT],
        initialStats: AGREEMENT_STATS,
        initialError: null,
      }),
    )
    await act(flush)

    // 登记 → 提交
    const register = buttons('登记责任书')[0]
    expect(register).toBeTruthy()
    await act(async () => {
      register!.click()
    })
    const ok = container!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
    expect(ok).toBeTruthy()
    await act(async () => {
      ok!.click()
      await flush()
    })
    expect(mocks.createSafetyTargetAgreement).toHaveBeenCalled()

    // 编辑 → 提交
    const edit = buttons('编辑')[0]
    expect(edit).toBeTruthy()
    await act(async () => {
      edit!.click()
    })
    const ok2 = container!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
    await act(async () => {
      ok2!.click()
      await flush()
    })
    expect(mocks.updateSafetyTargetAgreement).toHaveBeenCalled()

    // 删除确认
    const del = buttons('删除')[0]
    expect(del).toBeTruthy()
    const confirm = container!.querySelector<HTMLButtonElement>('button[data-pop-ok]')
    expect(confirm).toBeTruthy()
    await act(async () => {
      confirm!.click()
      await flush()
    })
    expect(mocks.deleteSafetyTargetAgreement).toHaveBeenCalled()
  })

  it('评估：发起登记并按模板预填、编辑、删除', async () => {
    mocks.getSafetyDutyAssessmentTemplate.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { matched: true, items: [{ key: 'a', label: '安全培训', max_score: 10 }] },
    })
    mocks.createSafetyDutyAssessment.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    mocks.updateSafetyDutyAssessment.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    mocks.deleteSafetyDutyAssessment.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    render(
      createElement(DutyAssessmentPanel as never, {
        pageKey: 'k',
        initialAssessments: [ASSESSMENT],
        initialStats: ASSESSMENT_STATS,
        initialError: null,
      }),
    )
    await act(flush)

    // 发起季度考核 → 按部门预填 → 提交
    const create = buttons('发起季度考核')[0]
    expect(create).toBeTruthy()
    await act(async () => {
      create!.click()
    })
    const prefill = buttons('按部门预填考核项')[0]
    expect(prefill).toBeTruthy()
    await act(async () => {
      prefill!.click()
      await flush()
    })
    expect(mocks.getSafetyDutyAssessmentTemplate).toHaveBeenCalled()

    const ok = container!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
    expect(ok).toBeTruthy()
    await act(async () => {
      ok!.click()
      await flush()
    })
    expect(mocks.createSafetyDutyAssessment).toHaveBeenCalled()

    // 编辑 → 提交更新
    const edit = buttons('编辑')[0]
    if (edit) {
      await act(async () => {
        edit.click()
      })
      const ok2 = container!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
      await act(async () => {
        ok2!.click()
        await flush()
      })
      expect(mocks.updateSafetyDutyAssessment).toHaveBeenCalled()
    }

    // 删除
    const confirm = container!.querySelector<HTMLButtonElement>('button[data-pop-ok]')
    expect(confirm).toBeTruthy()
    await act(async () => {
      confirm!.click()
      await flush()
    })
    expect(mocks.deleteSafetyDutyAssessment).toHaveBeenCalled()
  })
})
