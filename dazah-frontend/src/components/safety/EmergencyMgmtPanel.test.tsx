/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  canDelete: true,
  getEmergencyPlans: vi.fn(),
  getEmergencyDrills: vi.fn(),
  getEmergencySupplies: vi.fn(),
  getEmergencyMgmtStats: vi.fn(),
  createEmergencyPlan: vi.fn(),
  updateEmergencyPlan: vi.fn(),
  deleteEmergencyPlan: vi.fn(),
  uploadEmergencyPlanFile: vi.fn(),
  downloadEmergencyPlanFile: vi.fn(),
  createEmergencyDrill: vi.fn(),
  updateEmergencyDrill: vi.fn(),
  deleteEmergencyDrill: vi.fn(),
  createEmergencySupply: vi.fn(),
  updateEmergencySupply: vi.fn(),
  deleteEmergencySupply: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getEmergencyPlans: mocks.getEmergencyPlans,
  getEmergencyDrills: mocks.getEmergencyDrills,
  getEmergencySupplies: mocks.getEmergencySupplies,
  getEmergencyMgmtStats: mocks.getEmergencyMgmtStats,
  createEmergencyPlan: mocks.createEmergencyPlan,
  updateEmergencyPlan: mocks.updateEmergencyPlan,
  deleteEmergencyPlan: mocks.deleteEmergencyPlan,
  uploadEmergencyPlanFile: mocks.uploadEmergencyPlanFile,
  downloadEmergencyPlanFile: mocks.downloadEmergencyPlanFile,
  createEmergencyDrill: mocks.createEmergencyDrill,
  updateEmergencyDrill: mocks.updateEmergencyDrill,
  deleteEmergencyDrill: mocks.deleteEmergencyDrill,
  createEmergencySupply: mocks.createEmergencySupply,
  updateEmergencySupply: mocks.updateEmergencySupply,
  deleteEmergencySupply: mocks.deleteEmergencySupply,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: true,
    canQuery: true,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
  }),
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    DownloadOutlined: Icon,
    UploadOutlined: Icon,
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
  const Tabs = ({ items }: { items?: Array<{ key: string; label: string; children: ReactNode }> }) =>
    createElement(
      'div',
      null,
      (items ?? []).map((item) =>
        createElement(
          'section',
          { key: item.key, 'data-tab': item.key },
          createElement('h3', null, item.label),
          item.children
        )
      )
    )
  const Input = Object.assign(() => createElement('input'), {
    TextArea: () => createElement('textarea'),
    Search: () => createElement('button'),
  })
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
  const Upload = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
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
    Select: () => createElement('select'),
    Space: Box,
    Table,
    Tabs,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text }
    ),
    Upload,
  }
})

import EmergencyMgmtPanel from './EmergencyMgmtPanel'

const PAGE_KEY = 'safety:emergency-accident:emergency-mgmt'

const PLANS = [
  {
    id: 'p-1',
    name: '液氨泄漏专项应急预案',
    plan_type: 'special',
    version: 'V2.0',
    issued_at: '2026-03-01',
    review_due_date: '2026-11-30',
    status: 'active',
    department: '安环部',
    file_path: 'uploads/safety/emergency/plan.pdf',
    file_name: '液氨泄漏预案.pdf',
    remark: '',
    created_at: '2026-03-01T00:00:00Z',
    updated_at: '2026-03-01T00:00:00Z',
  },
]

const DRILLS = [
  {
    id: 'd-1',
    name: '液氨泄漏实战演练',
    drill_type: 'practical',
    scenario: '液氨泄漏',
    plan_name: '液氨泄漏专项应急预案',
    planned_date: '2026-03-15',
    actual_date: '2026-03-15',
    location: '203车间',
    departments: '安环部、203车间',
    participants_count: 26,
    summary: '',
    issues: '',
    status: 'done',
    created_at: '2026-03-15T00:00:00Z',
    updated_at: '2026-03-15T00:00:00Z',
  },
]

const SUPPLIES = [
  {
    id: 's-1',
    name: '正压式空气呼吸器',
    category: 'protective',
    spec: 'RHZK6.8/30',
    location: '应急库房',
    department: '安环部',
    quantity: 4,
    unit: '套',
    status: 'good',
    expiry_date: null,
    last_checked_at: '2026-10-01',
    last_check_result: '完好',
    remark: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

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

async function renderPanel() {
  root = createRoot(container)
  await act(async () => {
    root!.render(
      createElement(EmergencyMgmtPanel, {
        pageKey: PAGE_KEY,
        initialPlans: PLANS,
        initialDrills: DRILLS,
        initialSupplies: SUPPLIES,
        initialError: null,
      })
    )
  })
}

describe('EmergencyMgmtPanel', () => {
  it('renders plans, drills and supplies tabs from initial data', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('应急管理')
    expect(container.querySelector('[data-tab="plans"]')).not.toBeNull()
    expect(container.querySelector('[data-tab="drills"]')).not.toBeNull()
    expect(container.querySelector('[data-tab="supplies"]')).not.toBeNull()
    expect(markup).toContain('液氨泄漏专项应急预案')
    expect(markup).toContain('液氨泄漏实战演练')
    expect(markup).toContain('正压式空气呼吸器')
    expect(container.querySelector('[data-row="p-1"]')).not.toBeNull()
    expect(container.querySelector('[data-row="d-1"]')).not.toBeNull()
    expect(container.querySelector('[data-row="s-1"]')).not.toBeNull()
  })

  it('opens the drill form modal on create click', async () => {
    await renderPanel()
    const drillTab = container.querySelector('[data-tab="drills"]')
    const createButton = drillTab
      ? [...drillTab.querySelectorAll('button')].find((button) =>
          button.textContent?.includes('新增演练')
        )
      : undefined
    expect(createButton).toBeDefined()
    expect(createButton!.disabled).toBe(false)
    await act(async () => {
      createButton!.click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    expect(modal!.innerHTML).toContain('演练名称')
  })

  it('disables create buttons without operate permission', async () => {
    mocks.canOperate = false
    await renderPanel()
    const createButtons = [...container.querySelectorAll('button')].filter((button) =>
      button.textContent?.includes('新增预案')
    )
    expect(createButtons.length).toBeGreaterThan(0)
    expect(createButtons.every((button) => button.disabled)).toBe(true)
  })
})
