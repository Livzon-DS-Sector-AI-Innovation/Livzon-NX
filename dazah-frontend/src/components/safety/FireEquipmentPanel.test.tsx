/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  getFireEquipmentStats: vi.fn(),
  getFireEquipmentList: vi.fn(),
  getFireInspectionRecords: vi.fn(),
  syncFireEquipment: vi.fn(),
  getFireEquipmentDetail: vi.fn(),
  downloadZip: vi.fn(
    async (entries: Array<{ name: string; bytes: ArrayBuffer }>, zipName: string) => {
      // 记录调用由 vi.fn 的 mock.calls 承担；实现体仅消费参数避免未用告警
      void entries
      void zipName
    }
  ),
}))

vi.mock('@/actions/safety', () => ({
  getFireEquipmentStats: mocks.getFireEquipmentStats,
  getFireEquipmentList: mocks.getFireEquipmentList,
  getFireInspectionRecords: mocks.getFireInspectionRecords,
  syncFireEquipment: mocks.syncFireEquipment,
  getFireEquipmentDetail: mocks.getFireEquipmentDetail,
  initFireEquipmentWritebackTable: vi.fn(async () => ({ code: 200 })),
}))

vi.mock('@/lib/download', () => ({
  downloadZip: mocks.downloadZip,
}))

vi.mock('qrcode.react', async () => {
  const { createElement } = await import('react')
  return {
    QRCodeCanvas: ({ value }: { value: string }) =>
      createElement('canvas', { 'data-qr-value': value }),
    QRCodeSVG: ({ value }: { value: string }) =>
      createElement('svg', { 'data-qr-value': value }),
  }
})

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: true,
    canQuery: true,
    canOperate: mocks.canOperate,
    canSync: false,
  }),
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ message, description }: { message: ReactNode; description?: ReactNode }) =>
      createElement('div', { 'data-notice': String(message) }, description),
  }
})

vi.mock('./FireEquipmentQrSheet', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ open, items }: { open: boolean; items: unknown[] }) =>
      createElement(
        'div',
        { 'data-qr-sheet-open': String(open), 'data-qr-count': String(items.length) }
      ),
    fireEquipmentScanUrl: (equipmentId: string) =>
      `http://test/safety/fire-inspection/scan/${equipmentId}`,
  }
})

vi.mock('./FireEquipmentDetailDrawer', () => ({
  default: () => createElement('div', { 'data-detail-drawer': 'true' }),
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
  const Button = ({ children, onClick, disabled, loading }: AnyProps) =>
    createElement(
      'button',
      {
        type: 'button',
        'data-loading': String(Boolean(loading)),
        disabled: Boolean(disabled || loading),
        onClick: onClick as never,
      },
      children as ReactNode
    )
  const Table = ({ columns, dataSource }: { columns?: Column[]; dataSource?: Array<Record<string, unknown>> }) =>
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
            onClick: () => (onChange as (v: string) => void)?.(option.value),
          },
          option.label
        )
      )
    )
  const Input = Object.assign(
    ({ value, onChange, placeholder }: AnyProps) =>
      createElement('input', {
        value: (value as string) ?? '',
        placeholder: placeholder as string,
        ref: (node: HTMLInputElement | null) => {
          if (!node) return
          node.oninput = () => (onChange as (event: { target: { value: string } }) => void)?.({ target: { value: node.value } })
        },
      }),
    {
      Search: ({ placeholder, onSearch }: AnyProps) =>
        createElement(
          'button',
          {
            type: 'button',
            'data-search': String(placeholder ?? ''),
            onClick: () => (onSearch as () => void)?.(),
          },
          'search'
        ),
    }
  )
  const Statistic = ({ title, value }: AnyProps) =>
    createElement('span', { 'data-stat': String(title) }, String(value))
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)

  return {
    Button,
    Card: Box,
    Col: Box,
    Input,
    Row: Box,
    Segmented,
    Space: Box,
    Statistic,
    Table,
    Tabs,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Tooltip: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text }
    ),
    message: mocks.message,
  }
})

import FireEquipmentPanel from './FireEquipmentPanel'

const PAGE_KEY = 'safety:emergency-accident:fire-equipment-inspection'

const STATS = {
  total: 2,
  extinguisher_count: 1,
  hydrant_count: 1,
  inspected_this_month: 1,
  uninspected_this_month: 1,
  failed_this_month: 0,
  expired_count: 1,
  expiring_in_30_count: 2,
  is_configured: true,
  writeback_enabled: false,
  last_synced_at: '2026-10-20T01:00:00Z',
  last_sync_status: 'success',
  last_sync_error: null,
}

const EQUIPMENT_PAGE = {
  columns: [
    { name: '型号', kind: 'text' },
    { name: '压力状态', kind: 'select' },
  ],
  items: [
    {
      id: 'eq-1',
      equipment_type: 'extinguisher',
      equipment_type_label: '灭火器',
      equipment_no: 'MQC-001',
      department: '101一车间',
      location: '东侧通道口',
      tab_name: '主表',
      table_id: 'tbl1',
      record_id: 'rec1',
      fields: { '型号': 'MFZ/ABC4' },
      last_inspected_at: '2026-10-19T02:00:00Z',
      last_inspection_result: 'pass',
      month_status: 'inspected',
      last_synced_at: null,
    },
    {
      id: 'eq-2',
      equipment_type: 'hydrant',
      equipment_type_label: '消防栓',
      equipment_no: '',
      department: '102二车间',
      location: '一楼楼梯口',
      tab_name: '消防栓',
      table_id: 'tbl2',
      record_id: 'rec2',
      fields: {},
      last_inspected_at: null,
      last_inspection_result: null,
      month_status: 'uninspected',
      expiry_date: '2026-11-01',
      expiry_days_left: 12,
      expiry_status: 'expiring',
      last_synced_at: null,
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
}

const RECORDS_PAGE = {
  items: [
    {
      id: 'insp-1',
      equipment_id: 'eq-1',
      equipment_type: 'extinguisher',
      equipment_type_label: '灭火器',
      equipment_no: 'MQC-001',
      department: '101一车间',
      location: '东侧通道口',
      items: [{ key: 'body', label: '钢体外观', result: 'ok' }],
      result: 'pass',
      failed_items: [],
      abnormal_action: null,
      inspector_name: '张三',
      inspected_at: '2026-10-19T02:00:00Z',
      source: 'scan',
      created_at: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
}

function renderPanel(
  overrides: Partial<Parameters<typeof FireEquipmentPanel>[0]> = {}
) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      createElement(FireEquipmentPanel, {
        pageKey: PAGE_KEY,
        initialStats: STATS as never,
        initialEquipment: EQUIPMENT_PAGE as never,
        initialRecords: RECORDS_PAGE as never,
        initialError: null,
        ...overrides,
      })
    )
  })
  return { container, root }
}

describe('FireEquipmentPanel', () => {
  let root: Root | null = null
  let container: HTMLElement | null = null

  beforeEach(() => {
    Object.values(mocks.message).forEach((fn) => fn.mockClear())
    Object.values(mocks).forEach((value) => {
      if (typeof value === 'function' && 'mockReset' in value) value.mockReset()
    })
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = null
    container = null
  })

  it('renders stats and equipment rows', () => {
    const view = renderPanel()
    root = view.root
    container = view.container
    expect(container.querySelector('[data-stat="器材总数"]')?.textContent).toBe('2')
    expect(container.querySelector('[data-row="eq-1"]')?.textContent).toContain('MQC-001')
    // 未填编号显示兜底文案
    expect(container.querySelector('[data-row="eq-2"]')?.textContent).toContain('未填编号')
    expect(container.textContent).toContain('最近同步')
    // 动态列对齐多维表格：字段值来自 row.fields
    expect(container.querySelector('[data-row="eq-1"]')?.textContent).toContain('MFZ/ABC4')
    // 有效日期列：临近到期显示橙色标示
    expect(container.querySelector('[data-row="eq-2"]')?.textContent).toContain('12天后到期')
    expect(container.querySelector('[data-stat="已过期"]')?.textContent).toBe('1')
    // 未开启回写时展示一键创建入口；点检记录显示待回写
    expect(container.textContent).toContain('一键创建点检记录回写表')
    expect(container.querySelector('[data-tab="records"]')?.textContent).toContain('待回写')
  })

  it('hides writeback entry when already enabled', () => {
    const view = renderPanel({
      initialStats: { ...STATS, writeback_enabled: true } as never,
    })
    root = view.root
    container = view.container
    expect(container.textContent).toContain('点检记录自动回写飞书')
    expect(container.textContent).not.toContain('一键创建点检记录回写表')
  })

  it('shows binding guide when feishu table is not configured', () => {
    const view = renderPanel({
      initialStats: { ...STATS, is_configured: false } as never,
    })
    root = view.root
    container = view.container
    expect(
      container.querySelector('[data-notice="尚未绑定飞书多维表格"]')
    ).not.toBeNull()
  })

  it('syncs ledger and refreshes list on click', async () => {
    mocks.syncFireEquipment.mockResolvedValue({
      code: 200,
      data: { ...STATS, total: 9 },
    })
    mocks.getFireEquipmentList.mockResolvedValue({
      code: 200,
      data: { ...EQUIPMENT_PAGE, total: 9 },
    })
    mocks.getFireInspectionRecords.mockResolvedValue({
      code: 200,
      data: RECORDS_PAGE,
    })
    const view = renderPanel()
    root = view.root
    container = view.container

    const syncButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('立即同步飞书台账')
    )
    expect(syncButton).toBeDefined()
    await act(async () => {
      syncButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(mocks.syncFireEquipment).toHaveBeenCalledWith({ pageKey: PAGE_KEY })
    expect(mocks.message.success).toHaveBeenCalled()
    expect(
      container.querySelector('[data-stat="器材总数"]')?.textContent
    ).toBe('9')
  })

  it('renders inspection records with expand source column', () => {
    const view = renderPanel()
    root = view.root
    container = view.container
    const recordsTab = container.querySelector('[data-tab="records"]')
    expect(recordsTab?.textContent).toContain('MQC-001')
    expect(recordsTab?.textContent).toContain('张三')
  })

  it('downloads filtered QR codes as a zip', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(
      'data:image/png;base64,QUJD'
    )
    mocks.getFireEquipmentList.mockResolvedValue({
      code: 200,
      data: EQUIPMENT_PAGE,
    })
    const view = renderPanel()
    root = view.root
    container = view.container

    const downloadButton = [...container.querySelectorAll('button')].find(
      (button) => button.textContent?.includes('批量下载二维码')
    )
    expect(downloadButton).toBeDefined()
    await act(async () => {
      downloadButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    // 下载 handler 含宏任务等待（挂载二维码画布），轮询至其完成
    await vi.waitFor(() => {
      expect(mocks.downloadZip).toHaveBeenCalledTimes(1)
    })

    // 与批量打印同口径：按当前筛选拉全量（上限 200）
    expect(mocks.getFireEquipmentList).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, pageSize: 200 })
    )
    const [entries, zipName] = mocks.downloadZip.mock.calls[0]
    expect(entries).toHaveLength(2)
    expect(entries[0].name).toContain('MQC-001')
    expect(String(zipName)).toContain('消防器材二维码')
    expect(mocks.message.success).toHaveBeenCalled()
  })
})
