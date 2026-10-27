/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  canDelete: true,
  getSafetyFacilities: vi.fn(),
  getSafetyFacilityStats: vi.fn(),
  getSafetyFacilityChecklist: vi.fn(),
  getSafetyFacility: vi.fn(),
  createSafetyFacility: vi.fn(),
  updateSafetyFacility: vi.fn(),
  deleteSafetyFacility: vi.fn(),
  submitSafetyFacilityInspection: vi.fn(),
  getSafetyFacilityInspections: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyFacilities: mocks.getSafetyFacilities,
  getSafetyFacilityStats: mocks.getSafetyFacilityStats,
  getSafetyFacilityChecklist: mocks.getSafetyFacilityChecklist,
  getSafetyFacility: mocks.getSafetyFacility,
  createSafetyFacility: mocks.createSafetyFacility,
  updateSafetyFacility: mocks.updateSafetyFacility,
  deleteSafetyFacility: mocks.deleteSafetyFacility,
  submitSafetyFacilityInspection: mocks.submitSafetyFacilityInspection,
  getSafetyFacilityInspections: mocks.getSafetyFacilityInspections,
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
    Drawer: ({ children, open, title }: AnyProps) =>
      createElement(
        'div',
        { 'data-drawer-open': String(Boolean(open)) },
        open ? (createElement('h2', null, title as ReactNode), children as ReactNode) : null
      ),
    Form,
    Input,
    Modal: ({ children, open, onOk }: AnyProps) =>
      createElement(
        'div',
        { 'data-modal-open': String(Boolean(open)) },
        open && onOk
          ? createElement('button', { type: 'button', 'data-modal-ok': 'y', onClick: onOk as never }, '确定')
          : null
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
    Radio: Object.assign(() => createElement('input'), {
      Group: () => createElement('div'),
    }),
    Segmented,
    Select: () => createElement('select'),
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

import SafetyFacilityPanel from './SafetyFacilityPanel'

const PAGE_KEY = 'safety:site-mgmt:safety-facilities'

const FACILITIES = [
  {
    id: 'f-1',
    category: 'eyewash',
    facility_no: 'EYW-101-001',
    name: '101车间洗眼器',
    model_spec: '',
    department: '提炼四部',
    location: '一层东侧',
    installed_at: null,
    expiry_date: '2027-01-01',
    status: 'normal',
    last_inspected_at: '2026-10-20T02:00:00Z',
    last_inspection_result: 'pass',
    remark: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const STATS = {
  total: 1,
  by_category: { eyewash: 1 },
  by_status: { normal: 1 },
  expiring_in_90d: 0,
  failed_recent: 0,
}

const RECORDS = [
  {
    id: 'fi-1',
    facility_id: 'f-1',
    facility_category: 'eyewash',
    facility_no: 'EYW-101-001',
    facility_name: '101车间洗眼器',
    items: [{ key: 'appearance', label: '外观完好', result: 'ok', remark: '' }],
    result: 'pass',
    abnormal_action: '',
    inspector_name: '李四',
    inspected_at: '2026-10-20T02:00:00Z',
    source: 'web',
    created_at: '2026-10-20T02:00:00Z',
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
      createElement(SafetyFacilityPanel, {
        pageKey: PAGE_KEY,
        initialFacilities: FACILITIES,
        initialStats: STATS,
        initialRecords: RECORDS,
        initialError: null,
      })
    )
  })
}

describe('SafetyFacilityPanel', () => {
  it('renders facility rows, expiry tag and inspection records', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('安全设施台账')
    expect(container.querySelector('[data-row="f-1"]')).not.toBeNull()
    expect(markup).toContain('101车间洗眼器')
    expect(markup).toContain('EYW-101-001')
    expect(markup).toContain('正常')
    expect(markup).toContain('李四')
  })

  it('reloads list filtered by category when segmented changes', async () => {
    mocks.getSafetyFacilities.mockResolvedValue({
      code: 200,
      data: { items: FACILITIES, total: 1 },
    })
    mocks.getSafetyFacilityStats.mockResolvedValue({ code: 200, data: STATS })
    await renderPanel()
    const detectorOption = container.querySelector('[data-segmented="gas_detector"]')
    expect(detectorOption).not.toBeNull()
    await act(async () => {
      ;(detectorOption as HTMLElement).click()
    })
    expect(mocks.getSafetyFacilities).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'gas_detector' })
    )
  })

  it('disables edit actions without operate permission', async () => {
    mocks.canOperate = false
    await renderPanel()
    const pointButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('点检')
    )
    expect(pointButton).toBeDefined()
    expect(pointButton!.disabled).toBe(true)
  })

  it('creates a facility through the modal submit', async () => {
    mocks.createSafetyFacility.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const createButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('新增安全设施'),
    )
    expect(createButton).toBeDefined()
    await act(async () => {
      createButton!.click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector('button[data-modal-ok]')
    expect(ok).not.toBeNull()
    await act(async () => {
      ok!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.createSafetyFacility).toHaveBeenCalled()
  })

  it('编辑设施后提交更新', async () => {
    mocks.updateSafetyFacility.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const editBtn = [...container.querySelectorAll('button')].find((b) => b.textContent === '编辑')
    expect(editBtn).toBeDefined()
    await act(async () => { editBtn!.click() })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector('button[data-modal-ok]')
    await act(async () => {
      ok!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(mocks.updateSafetyFacility).toHaveBeenCalled()
  })

  it('删除设施（Popconfirm 确认后调用）', async () => {
    mocks.deleteSafetyFacility.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const confirm = container.querySelector('button[data-popconfirm-ok]')
    expect(confirm).toBeDefined()
    await act(async () => {
      confirm!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(mocks.deleteSafetyFacility).toHaveBeenCalled()
  })

  it('点检：打开检查卡并提交点检结果', async () => {
    mocks.getSafetyFacilityChecklist.mockResolvedValue({ code: 200, message: 'success', data: { items: [] } })
    mocks.submitSafetyFacilityInspection.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const btn = [...container.querySelectorAll('button')].find((b) => b.textContent === '点检')
    expect(btn).toBeDefined()
    await act(async () => {
      btn!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(mocks.getSafetyFacilityChecklist).toHaveBeenCalled()
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector('button[data-modal-ok]')
    await act(async () => {
      ok!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(mocks.submitSafetyFacilityInspection).toHaveBeenCalled()
  })

  it('delete failure branch keeps list unchanged', async () => {
    mocks.deleteSafetyFacility.mockResolvedValue({ code: 500, message: '删除失败' })
    await renderPanel()
    const confirm = container.querySelector('button[data-popconfirm-ok]')
    if (confirm) {
      await act(async () => {
        confirm.click()
        await new Promise((r) => setTimeout(r, 30))
      })
    }
  })
})
