/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  canDelete: true,
  getSafetyTargets: vi.fn(),
  getSafetyTargetStats: vi.fn(),
  getSafetyTarget: vi.fn(),
  createSafetyTarget: vi.fn(),
  updateSafetyTarget: vi.fn(),
  deleteSafetyTarget: vi.fn(),
  upsertSafetyTargetRecord: vi.fn(),
  deleteSafetyTargetRecord: vi.fn(),
  getSafetyTargetAgreements: vi.fn(),
  getSafetyTargetAgreementStats: vi.fn(),
  createSafetyTargetAgreement: vi.fn(),
  updateSafetyTargetAgreement: vi.fn(),
  deleteSafetyTargetAgreement: vi.fn(),
  getSafetyDutyAssessments: vi.fn(),
  getSafetyDutyAssessmentStats: vi.fn(),
  getSafetyDutyAssessmentTemplate: vi.fn(),
  createSafetyDutyAssessment: vi.fn(),
  updateSafetyDutyAssessment: vi.fn(),
  deleteSafetyDutyAssessment: vi.fn(),
  downloadAgreementImportTemplate: vi.fn(),
  importAgreementSigns: vi.fn(),
  downloadDutyAssessmentImportTemplate: vi.fn(),
  importDutyAssessmentResults: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyTargets: mocks.getSafetyTargets,
  getSafetyTargetStats: mocks.getSafetyTargetStats,
  getSafetyTarget: mocks.getSafetyTarget,
  createSafetyTarget: mocks.createSafetyTarget,
  updateSafetyTarget: mocks.updateSafetyTarget,
  deleteSafetyTarget: mocks.deleteSafetyTarget,
  upsertSafetyTargetRecord: mocks.upsertSafetyTargetRecord,
  deleteSafetyTargetRecord: mocks.deleteSafetyTargetRecord,
  getSafetyTargetAgreements: mocks.getSafetyTargetAgreements,
  getSafetyTargetAgreementStats: mocks.getSafetyTargetAgreementStats,
  createSafetyTargetAgreement: mocks.createSafetyTargetAgreement,
  updateSafetyTargetAgreement: mocks.updateSafetyTargetAgreement,
  deleteSafetyTargetAgreement: mocks.deleteSafetyTargetAgreement,
  getSafetyDutyAssessments: mocks.getSafetyDutyAssessments,
  getSafetyDutyAssessmentStats: mocks.getSafetyDutyAssessmentStats,
  getSafetyDutyAssessmentTemplate: mocks.getSafetyDutyAssessmentTemplate,
  createSafetyDutyAssessment: mocks.createSafetyDutyAssessment,
  updateSafetyDutyAssessment: mocks.updateSafetyDutyAssessment,
  deleteSafetyDutyAssessment: mocks.deleteSafetyDutyAssessment,
  downloadAgreementImportTemplate: mocks.downloadAgreementImportTemplate,
  importAgreementSigns: mocks.importAgreementSigns,
  downloadDutyAssessmentImportTemplate: mocks.downloadDutyAssessmentImportTemplate,
  importDutyAssessmentResults: mocks.importDutyAssessmentResults,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: true,
    canQuery: true,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
  }),
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: (props: { message?: string; description?: string }) =>
      createElement(
        'div',
        { 'data-notice': String(props.message ?? '') },
        props.message,
        props.description
      ),
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  type AnyProps = Record<string, unknown>
  interface Column {
    title?: unknown
    dataIndex?: string
    render?: (value: unknown, row: Record<string, unknown>) => ReactNode
  }
  const Box = ({ children, title }: AnyProps) =>
    createElement('div', null, title as ReactNode, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode
    )
  const Table = ({
    columns,
    dataSource,
  }: {
    columns?: Column[]
    dataSource?: Array<Record<string, unknown>>
  }) =>
    createElement(
      'tbody',
      null,
      (dataSource ?? []).map((row, rowIndex) =>
        createElement(
          'tr',
          { key: String(row.id ?? rowIndex), 'data-row': String(row.id ?? rowIndex) },
          (columns ?? []).map((column, columnIndex) =>
            createElement(
              'td',
              { key: column.dataIndex ?? columnIndex },
              column.render
                ? (column.render(row[column.dataIndex ?? ''], row) as ReactNode)
                : ((row[column.dataIndex ?? ''] as ReactNode) ?? null)
            )
          )
        )
      )
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
            onClick: () => (onChange as (v: unknown) => void)?.(option.value),
          },
          option.label
        )
      )
    )
  const Input = Object.assign(
    (props: AnyProps) => createElement('input', props as never),
    {
      Search: ({ placeholder, onSearch }: AnyProps) =>
        createElement(
          'button',
          {
            type: 'button',
            'data-search': String(placeholder ?? ''),
            onClick: () => (onSearch as (v: string) => void)?.(''),
          },
          'search'
        ),
      TextArea: (props: AnyProps) => createElement('textarea', props as never),
    }
  )
  const useForm = () => [
    {
      setFieldsValue: vi.fn(),
      validateFields: vi.fn(async () => ({})),
      getFieldValue: vi.fn(() => ''),
    },
  ]
  const Form = Object.assign(
    ({ children }: AnyProps) => createElement('form', null, children as ReactNode),
    {
      useForm,
      useWatch: () => undefined,
      Item: ({ children, label }: AnyProps) =>
        createElement(
          'div',
          null,
          label ? createElement('span', null, label as ReactNode) : null,
          children as ReactNode
        ),
      List: ({ children }: AnyProps) =>
        createElement(
          'div',
          null,
          (children as (...args: unknown[]) => ReactNode)(
            [],
            { add: vi.fn(), remove: vi.fn() }
          )
        ),
    }
  )
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const App = Object.assign(({ children }: AnyProps) => createElement('div', null, children as ReactNode), {
    useApp: () => ({ message: mocks.message }),
  })
  const Tabs = ({ items }: AnyProps) =>
    createElement(
      'div',
      null,
      ((items as Array<{ key: string; label: string; children: ReactNode }>) ?? []).map((item) =>
        createElement(
          'section',
          { key: item.key, 'data-tab': item.key },
          createElement('h3', null, item.label),
          item.children
        )
      )
    )

  return {
    App,
    Button,
    Card: Box,
    DatePicker: () => createElement('input'),
    Form,
    Input,
    InputNumber: () => createElement('input'),
    Modal: ({ children, open, onOk, footer, title }: AnyProps) =>
      createElement(
        'div',
        { 'data-modal-open': String(Boolean(open)) },
        open ? createElement('h2', null, title as ReactNode) : null,
        open && onOk
          ? createElement('button', { type: 'button', 'data-modal-ok': 'y', onClick: onOk as never }, '确定')
          : null,
        open ? (children as ReactNode) : null,
        open && Array.isArray(footer)
          ? (footer as ReactNode[]).map((node, idx) =>
              createElement('span', { key: idx }, node)
            )
          : null
      ),
    Upload: ({ children, onChange }: AnyProps) =>
      createElement(
        'button',
        {
          type: 'button',
          'data-upload': 'y',
          onClick: () =>
            (onChange as (info: unknown) => void)?.({
              file: { originFileObj: { name: '导入.xlsx' }, name: '导入.xlsx' },
            }),
        },
        children as ReactNode
      ),
    Popconfirm: ({ children, onConfirm }: AnyProps) =>
      createElement(
        'span',
        null,
        children as ReactNode,
        onConfirm
          ? createElement('button', { type: 'button', 'data-popconfirm-ok': 'y', onClick: onConfirm as never }, '确认删')
          : null
      ),
    Segmented,
    Select: ({ options }: AnyProps) =>
      createElement(
        'select',
        null,
        ((options as Array<{ label: string }>) ?? []).map((option) =>
          createElement('option', { key: option.label }, option.label)
        )
      ),
    Space: Box,
    Table,
    Tabs,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text }
    ),
  }
})

import TargetPerformancePanel from './TargetPerformancePanel'

const PAGE_KEY = 'safety:governance:target-performance'

const TARGETS = [
  {
    id: 't-1',
    year: 2026,
    title: '杜绝重伤及以上事故',
    category: '事故控制',
    metric: '重伤事故起数',
    target_value: '0',
    unit: '起',
    owner_department: '安环部',
    owner_name: '张三',
    deadline: null,
    status: 'in_progress',
    remark: '',
    records: [
      {
        id: 'r-1',
        target_id: 't-1',
        period: '2026-Q1',
        actual_value: '0',
        completion_pct: 100,
        note: '',
        created_at: '2026-04-01T00:00:00Z',
        updated_at: '2026-04-01T00:00:00Z',
      },
    ],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const STATS = {
  total: 1,
  achieved: 0,
  in_progress: 1,
  not_achieved: 0,
  categories: ['事故控制'],
  departments: [
    { department: '安环部', total: 1, achieved: 0, not_achieved: 0, in_progress: 1 },
  ],
}

const AGREEMENTS = [
  {
    id: 'a-1',
    year: 2026,
    department: '安全部',
    position: '负责人',
    category: '部门/车间负责人',
    party_a: '',
    party_b: '',
    status: 'unsigned',
    signed_date: null,
    expires_date: null,
    goals_text: '不发生B级及以上事故\n隐患整改率100%',
    remark: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const AGREEMENT_STATS = {
  total: 49,
  signed: 3,
  unsigned: 46,
  sign_rate: 6.1,
  departments: [{ department: '安全部', total: 1, signed: 0 }],
}

const ASSESSMENTS = [
  {
    id: 'd-1',
    year: 2026,
    quarter: 1,
    department: '安全部',
    person_name: '负责人',
    assessor: '安全部',
    assessment_date: '2026-01-20',
    total_score: 96.0,
    grade: '优秀',
    remark: '',
    items: [
      {
        id: 'di-1',
        assessment_id: 'd-1',
        sort_order: 0,
        content: '认真贯彻执行安全生产法律、法规',
        rule: '未按要求执行，每项扣2分',
        standard_score: 10,
        deduction_score: 0,
        score: 10,
        remark: '',
      },
    ],
    created_at: '2026-01-20T00:00:00Z',
    updated_at: '2026-01-20T00:00:00Z',
  },
]

const ASSESSMENT_STATS = {
  total: 1,
  avg_score: 96.0,
  excellent: 1,
  good: 0,
  qualified: 0,
  unqualified: 0,
  quarters: [{ quarter: 1, count: 1, avg_score: 96.0 }],
  departments: [{ department: '安全部', count: 1, avg_score: 96.0 }],
}

let root: Root | null = null
let container: HTMLElement

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  mocks.canOperate = true
  mocks.canDelete = true
})

afterEach(() => {
  root?.unmount()
  container.remove()
  vi.clearAllMocks()
})

async function renderPanel(props: Record<string, unknown> = {}) {
  root = createRoot(container)
  await act(async () => {
    root!.render(
      createElement(TargetPerformancePanel, {
        pageKey: PAGE_KEY,
        initialTargets: TARGETS,
        initialStats: STATS,
        initialAgreements: AGREEMENTS,
        initialAgreementStats: AGREEMENT_STATS,
        initialAssessments: ASSESSMENTS,
        initialAssessmentStats: ASSESSMENT_STATS,
        initialError: null,
        ...props,
      })
    )
  })
}

describe('TargetPerformancePanel', () => {
  it('renders targets, progress records and stats from initial data', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('目标责任与绩效')
    expect(markup).toContain('杜绝重伤及以上事故')
    expect(markup).toContain('2026-Q1')
    expect(markup).toContain('100%')
    expect(container.querySelector('[data-row="t-1"]')).not.toBeNull()
  })

  it('renders agreement ledger with sign-rate stats', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('安全目标责任书')
    expect(markup).toContain('应签总数')
    expect(markup).toContain('6.1%')
    expect(container.querySelector('[data-row="a-1"]')).not.toBeNull()
    expect(markup).toContain('未签订')
  })

  it('signs an agreement through the quick action', async () => {
    mocks.updateSafetyTargetAgreement.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await renderPanel()
    const signBtn = [...container.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === '签订'
    )
    expect(signBtn).toBeDefined()
    await act(async () => {
      signBtn!.click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
    await act(async () => {
      ok!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.updateSafetyTargetAgreement).toHaveBeenCalled()
  })

  it('renders quarterly assessments with grade stats', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('安全生产责任制考核')
    expect(markup).toContain('平均分')
    expect(markup).toContain('96')
    expect(container.querySelector('[data-row="d-1"]')).not.toBeNull()
    expect(markup).toContain('优秀')
  })

  it('warns when prefilling template without department', async () => {
    await renderPanel()
    const createBtn = [...container.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === '发起季度考核'
    )
    await act(async () => {
      createBtn!.click()
    })
    const prefill = [...container.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === '按部门预填考核项'
    )
    expect(prefill).toBeDefined()
    await act(async () => {
      prefill!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.message.warning).toHaveBeenCalled()
    expect(mocks.getSafetyDutyAssessmentTemplate).not.toHaveBeenCalled()
  })

  it('disables create button without operate permission', async () => {
    mocks.canOperate = false
    await renderPanel()
    const createButton = [...container.querySelectorAll<HTMLButtonElement>('button')].find((button) =>
      button.textContent?.includes('新增安全目标')
    )
    expect(createButton).toBeDefined()
    expect(createButton!.disabled).toBe(true)
  })

  it('refreshes list when status segmented changes', async () => {
    mocks.getSafetyTargets.mockResolvedValue({
      code: 200,
      data: { items: TARGETS, total: TARGETS.length },
    })
    mocks.getSafetyTargetStats.mockResolvedValue({ code: 200, data: STATS })
    await renderPanel()
    const achieved = container.querySelector('[data-segmented="achieved"]')
    expect(achieved).not.toBeNull()
    await act(async () => {
      ;(achieved as HTMLElement).click()
    })
    expect(mocks.getSafetyTargets).toHaveBeenCalledWith(
      expect.objectContaining({ year: expect.any(Number), status: 'achieved' })
    )
  })

  it('creates a target through the modal submit', async () => {
    mocks.createSafetyTarget.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const createButton = [...container.querySelectorAll<HTMLButtonElement>('button')].find((button) =>
      button.textContent?.includes('新增安全目标'),
    )
    expect(createButton).toBeDefined()
    await act(async () => {
      createButton!.click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
    expect(ok).not.toBeNull()
    await act(async () => {
      ok!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.createSafetyTarget).toHaveBeenCalled()
  })

  it('编辑目标后提交更新', async () => {
    mocks.updateSafetyTarget.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const ledger = container.querySelector('[data-tab="targets"]')
    const editBtn = [...(ledger?.querySelectorAll<HTMLButtonElement>('button') ?? [])].find((b) => b.textContent === '编辑')
    expect(editBtn).toBeDefined()
    await act(async () => { editBtn!.click() })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector<HTMLButtonElement>('button[data-modal-ok]')
    await act(async () => {
      ok!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(mocks.updateSafetyTarget).toHaveBeenCalled()
  })

  it('删除目标（Popconfirm 确认后调用）', async () => {
    mocks.deleteSafetyTarget.mockResolvedValue({ code: 200, message: 'success', data: null })
        mocks.getSafetyTargets.mockResolvedValue({ code: 200, message: 'success', data: [], meta: { total: 0 } })
await renderPanel()
    const ledger = container.querySelector('[data-tab="targets"]')
    const confirms = ledger?.querySelectorAll<HTMLButtonElement>('button[data-popconfirm-ok]') ?? []
    const target = Array.from(confirms).at(-1)!
    expect(target).toBeDefined()
    await act(async () => {
      target.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(mocks.deleteSafetyTarget).toHaveBeenCalled()
  })

  it('imports agreement signs through the modal', async () => {
    mocks.importAgreementSigns.mockResolvedValue({
      code: 200,
      data: { updated: 3, created: 1, errors: [] },
    })
    await renderPanel()
    const importBtn = [...container.querySelectorAll<HTMLButtonElement>('button')].find(
      (b) => b.textContent === '批量导入'
    )
    expect(importBtn).toBeDefined()
    await act(async () => {
      importBtn!.click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const pick = modal!.querySelector<HTMLButtonElement>('button[data-upload]')
    await act(async () => {
      pick!.click()
    })
    const start = [...(modal as HTMLElement).querySelectorAll<HTMLButtonElement>('button')].find(
      (b) => b.textContent === '开始导入'
    )
    expect(start).toBeDefined()
    expect(start!.disabled).toBe(false)
    await act(async () => {
      start!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.importAgreementSigns).toHaveBeenCalled()
    expect(container.innerHTML).toContain('更新登记 3 条，新增 1 条')
  })

  it('downloads assessment import template with selected period', async () => {
    mocks.downloadDutyAssessmentImportTemplate.mockResolvedValue(undefined)
    await renderPanel()
    const importBtns = [...container.querySelectorAll<HTMLButtonElement>('button')].filter(
      (b) => b.textContent === '批量导入'
    )
    expect(importBtns.length).toBeGreaterThanOrEqual(2)
    await act(async () => {
      importBtns[importBtns.length - 1].click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    expect(modal!.innerHTML).toContain('批量导入季度考核（2026 年 Q1）')
    const download = [...(modal as HTMLElement).querySelectorAll<HTMLButtonElement>('button')].find(
      (b) => b.textContent?.includes('下载 2026 Q1 考核模板')
    )
    expect(download).toBeDefined()
    await act(async () => {
      download!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.downloadDutyAssessmentImportTemplate).toHaveBeenCalledWith(2026, 1)
  })

  it('deletes a progress record and hits update failure branch', async () => {
    mocks.deleteSafetyTargetRecord.mockResolvedValue({ code: 200, message: 'success', data: null })
    mocks.getSafetyTargets.mockResolvedValue({ code: 200, message: 'success', data: [], meta: { total: 0 } })
    await renderPanel()
    const first = container.querySelector<HTMLButtonElement>('button[data-popconfirm-ok]')
    if (first) {
      await act(async () => {
        first.click()
        await new Promise((r) => setTimeout(r, 30))
      })
    }

    mocks.updateSafetyTarget.mockResolvedValue({ code: 500, message: '保存失败' })
    const ledger = container.querySelector('[data-tab="targets"]')
    const editBtn = [...(ledger?.querySelectorAll<HTMLButtonElement>('button') ?? [])].find((b) => b.textContent === '编辑')
    if (editBtn) {
      await act(async () => { editBtn.click() })
      const ok = container.querySelector<HTMLButtonElement>('[data-modal-open="true"] button[data-modal-ok]')
      await act(async () => {
        ok!.click()
        await new Promise((r) => setTimeout(r, 30))
      })
    }
  })
})
