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
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: true,
    canQuery: true,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
  }),
}))

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
    () => createElement('input'),
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
    }
  )
  const useForm = () => [
    { setFieldsValue: vi.fn(), validateFields: vi.fn(async () => ({})) },
  ]
  const Form = Object.assign(
    ({ children }: AnyProps) => createElement('form', null, children as ReactNode),
    {
      useForm,
      Item: ({ children, label }: AnyProps) =>
        createElement(
          'div',
          null,
          label ? createElement('span', null, label as ReactNode) : null,
          children as ReactNode
        ),
    }
  )
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const App = Object.assign(({ children }: AnyProps) => createElement('div', null, children as ReactNode), {
    useApp: () => ({ message: mocks.message }),
  })

  return {
    App,
    Button,
    Card: Box,
    DatePicker: () => createElement('input'),
    Form,
    Input,
    InputNumber: () => createElement('input'),
    Modal: ({ children, open }: AnyProps) =>
      createElement('div', { 'data-modal-open': String(Boolean(open)) }, open ? (children as ReactNode) : null),
    Popconfirm: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
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

  it('disables create button without operate permission', async () => {
    mocks.canOperate = false
    await renderPanel()
    const createButton = [...container.querySelectorAll('button')].find((button) =>
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
})
