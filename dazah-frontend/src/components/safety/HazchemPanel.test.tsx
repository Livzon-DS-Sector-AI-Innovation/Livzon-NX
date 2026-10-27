/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  canDelete: true,
  getHazardousChemicals: vi.fn(),
  getChemicalInventories: vi.fn(),
  createHazardousChemical: vi.fn(),
  updateHazardousChemical: vi.fn(),
  deleteHazardousChemical: vi.fn(),
  uploadChemicalMsds: vi.fn(),
  downloadChemicalMsds: vi.fn(),
  createChemicalInventory: vi.fn(),
  updateChemicalInventory: vi.fn(),
  deleteChemicalInventory: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getHazardousChemicals: mocks.getHazardousChemicals,
  getChemicalInventories: mocks.getChemicalInventories,
  createHazardousChemical: mocks.createHazardousChemical,
  updateHazardousChemical: mocks.updateHazardousChemical,
  deleteHazardousChemical: mocks.deleteHazardousChemical,
  uploadChemicalMsds: mocks.uploadChemicalMsds,
  downloadChemicalMsds: mocks.downloadChemicalMsds,
  createChemicalInventory: mocks.createChemicalInventory,
  updateChemicalInventory: mocks.updateChemicalInventory,
  deleteChemicalInventory: mocks.deleteChemicalInventory,
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
    FileTextOutlined: Icon,
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
  const Button = ({ children, onClick, disabled, icon }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), 'data-icon': icon ? 'y' : 'n', onClick: onClick as never },
      children as ReactNode
    )
  const Table = ({
    columns,
    dataSource,
    rowClassName,
  }: {
    columns?: Column[]
    dataSource?: Array<Record<string, unknown>>
    rowClassName?: (row: Record<string, unknown>) => string
  }) =>
    createElement(
      'tbody',
      null,
      (dataSource ?? []).map((row, rowIndex) =>
        createElement(
          'tr',
          {
            key: String(row.id ?? rowIndex),
            'data-row': String(row.id ?? rowIndex),
            class: rowClassName ? rowClassName(row) : undefined,
          },
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
  const Upload = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const App = Object.assign(({ children }: AnyProps) => createElement('div', null, children as ReactNode), {
    useApp: () => ({ message: mocks.message }),
  })

  return {
    App,
    Button,
    Card: Box,
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

import HazchemPanel from './HazchemPanel'

const PAGE_KEY = 'safety:site-mgmt:hazchem-msds'

const CHEMICALS = [
  {
    id: 'c-1',
    name: '乙醇',
    alias: '酒精',
    cas_no: '64-17-5',
    category: 'flammable_liquid',
    hazard_statements: '高度易燃液体',
    storage_requirements: '阴凉通风',
    msds_file_path: 'uploads/safety/hazchem/msds.pdf',
    msds_file_name: '乙醇MSDS.pdf',
    remark: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const INVENTORIES = [
  {
    id: 'inv-1',
    chemical_id: 'c-1',
    chemical_name: '乙醇',
    category: 'flammable_liquid',
    workshop: 'daba',
    quantity: 4.6,
    upper_limit: 3,
    over_limit: true,
    over_pct: 53.3,
    unit: 'kg',
    remark: '',
    updated_at: '2026-10-26T00:00:00Z',
  },
  {
    id: 'inv-2',
    chemical_id: 'c-1',
    chemical_name: '乙醇',
    category: 'flammable_liquid',
    workshop: 'extraction_2b',
    quantity: 1,
    upper_limit: 8,
    over_limit: false,
    over_pct: null,
    unit: 'kg',
    remark: '',
    updated_at: '2026-10-26T00:00:00Z',
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
      createElement(HazchemPanel, {
        pageKey: PAGE_KEY,
        initialChemicals: CHEMICALS,
        initialInventories: INVENTORIES,
        initialError: null,
      })
    )
  })
}

describe('HazchemPanel', () => {
  it('renders chemical catalog with MSDS download and inventory over-limit tags', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('危化品与 MSDS 管理')
    expect(container.querySelector('[data-row="c-1"]')).not.toBeNull()
    expect(markup).toContain('乙醇')
    expect(markup).toContain('64-17-5')
    expect(markup).toContain('超储 53.3%')
    expect(container.querySelector('[data-row="inv-2"]')).not.toBeNull()
  })

  it('toggles over-limit-only filter', async () => {
    mocks.getChemicalInventories.mockResolvedValue({
      code: 200,
      data: { items: INVENTORIES.slice(0, 1), total: 1 },
    })
    await renderPanel()
    const toggle = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('只看超储')
    )
    expect(toggle).toBeDefined()
    await act(async () => {
      toggle!.click()
    })
    expect(mocks.getChemicalInventories).toHaveBeenCalledWith(
      expect.objectContaining({ over_limit_only: true })
    )
  })

  it('disables create buttons without operate permission', async () => {
    mocks.canOperate = false
    await renderPanel()
    const createButtons = [...container.querySelectorAll('button')].filter((button) =>
      button.textContent?.includes('新增危化品')
    )
    expect(createButtons.length).toBeGreaterThan(0)
    expect(createButtons.every((button) => button.disabled)).toBe(true)
  })
})
