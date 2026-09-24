/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}))

const apiClient = vi.hoisted(() => ({
  fetchWarehouseInspectionProgressOverview: vi.fn(),
  fetchWarehouseRecordDetail: vi.fn(),
}))

vi.mock('@/lib/api/client/warehouse', () => apiClient)

import { WarehouseInspectionProgressPanel } from './WarehouseInspectionProgressPanel'

const OVERVIEW = {
  scope: 'raw',
  scope_label: '原辅料及包材',
  start_date: '2026-09-09',
  generated_at: '2026-09-20T04:00:00+00:00',
  current: { pending_count: 2, pending_avg_hours: 60.0, pending_max_hours: 96.0 },
  window: {
    days: 30,
    start: '2026-08-21',
    end: '2026-09-20',
    completed_count: 3,
    qualified_count: 2,
    unqualified_count: 1,
    avg_hours: 64.5,
    median_hours: 57.0,
    p90_hours: 72.0,
    max_hours: 72.0,
  },
  breakdown: [
    {
      label: '原辅料类',
      completed_count: 2,
      qualified_count: 2,
      unqualified_count: 0,
      avg_hours: 57.0,
      pending_count: 1,
    },
  ],
  daily: [
    { date: '2026-09-12', qualified: 1, unqualified: 0, avg_hours: 57.0 },
    { date: '2026-09-14', qualified: 0, unqualified: 1, avg_hours: 72.0 },
  ],
  oldest_pending: [
    {
      name: '乳糖',
      batch: 'YL-300',
      category: '原辅料类',
      product: null,
      inbound_date: '2026-09-18',
      waited_hours: 60.0,
      record_id: 'rec-pending',
      page_key: 'inbound-ledger',
    },
  ],
  pending_items: [
    {
      name: '乳糖',
      batch: 'YL-300',
      category: '原辅料类',
      product: null,
      inbound_date: '2026-09-18',
      waited_hours: 60.0,
      record_id: 'rec-pending',
      page_key: 'inbound-ledger',
    },
    {
      name: '甘露醇',
      batch: 'YL-400',
      category: '原辅料类',
      product: null,
      inbound_date: '2026-09-19',
      waited_hours: 36.0,
      record_id: 'rec-pending-2',
      page_key: 'inbound-ledger',
    },
  ],
  stages: null,
}

const RECORD_DETAIL = {
  record_id: 'rec-pending-2',
  fields: [
    { field_name: '物料名称', value: '甘露醇' },
    { field_name: '厂内批号', value: 'YL-400' },
    { field_name: '入库日期', value: '2026-09-19' },
    { field_name: '检测结果', value: null },
  ],
  inspection_cycle: {
    page_key: 'inbound-ledger',
    record_id: 'rec-pending-2',
    status: 'pending',
    status_label: '待验中',
    result: null,
    inbound_date: '2026-09-19',
    pending_since: null,
    result_at: null,
    stages: [],
    total_hours: 36.0,
    note: null,
  },
}

// happy-dom 解析 antd 内联 SVG 会截断后续 DOM，静态断言前先移除
function visibleText(root: ParentNode): string {
  root.querySelectorAll('svg').forEach((el) => el.remove())
  return root.textContent ?? ''
}

function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
}

async function settle(ms = 60) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

describe('WarehouseInspectionProgressPanel', () => {
  let container: HTMLDivElement
  let root: Root
  let client: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.fetchWarehouseInspectionProgressOverview.mockResolvedValue(OVERVIEW)
    apiClient.fetchWarehouseRecordDetail.mockResolvedValue(RECORD_DETAIL)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  })

  afterEach(() => {
    act(() => root.unmount())
    client.clear()
    container.remove()
    vi.restoreAllMocks()
  })

  async function mount(scope: 'raw' | 'product' = 'raw', waitRendered = true) {
    act(() => {
      root.render(
        <App>
          <QueryClientProvider client={client}>
            <WarehouseInspectionProgressPanel scope={scope} />
          </QueryClientProvider>
        </App>
      )
    })
    if (waitRendered) {
      await settle()
    }
  }

  it('renders inspection progress KPIs, chart and oldest pending list', async () => {
    await mount('raw')
    expect(apiClient.fetchWarehouseInspectionProgressOverview).toHaveBeenCalledWith('raw', 30)
    const text = container.textContent ?? ''
    expect(text).toContain('近期检验进度')
    expect(text).toContain('当前待验批次')
    expect(text).toContain('平均检验周期')
    expect(text).toContain('统计自 2026-09-09')
    expect(text).toContain('乳糖')
    expect(container.querySelector('[data-testid="echarts-mock"]')).not.toBeNull()
  })

  it('shows batch number column in the oldest pending table', async () => {
    await mount('raw')
    const text = visibleText(container)
    expect(text).toContain('批号')
    expect(text).toContain('YL-300')
  })

  it('opens the full pending list drawer when clicking the pending card', async () => {
    await mount('raw')
    const card = container.querySelector('.cursor-pointer')
    expect(card).not.toBeNull()
    expect(card?.textContent).toContain('当前待验批次')
    click(card as Element)
    await settle()

    // 卡片点击触发一次主动拉新
    expect(apiClient.fetchWarehouseInspectionProgressOverview.mock.calls.length).toBeGreaterThanOrEqual(2)
    const text = visibleText(document.body)
    expect(text).toContain('当前待验批次（共 2 条）')
    // 抽屉展示全量列表（含 Top5 之外的批次）
    expect(text).toContain('甘露醇')
    expect(text).toContain('YL-400')
    expect(text).toContain('前往台账查看')
  })

  it('opens the record detail modal when clicking a pending row', async () => {
    await mount('raw')
    // 打开全量列表抽屉后点击仅存在于抽屉中的批次行
    const card = container.querySelector('.cursor-pointer') as Element
    click(card)
    await settle()

    const row = Array.from(document.body.querySelectorAll('tr')).find((tr) =>
      (tr.textContent ?? '').includes('YL-400')
    )
    expect(row).toBeDefined()
    click(row as Element)
    await settle()

    expect(apiClient.fetchWarehouseRecordDetail).toHaveBeenCalledWith(
      'inbound-ledger',
      'rec-pending-2'
    )
    const text = visibleText(document.body)
    expect(text).toContain('批次记录详情')
    expect(text).toContain('物料名称')
    expect(text).toContain('甘露醇')
    expect(text).toContain('检验进度周期')
    expect(text).toContain('待验中')
    expect(text).toContain('总时长')
  })

  it('renders product scope stage stats when present', async () => {
    apiClient.fetchWarehouseInspectionProgressOverview.mockResolvedValue({
      ...OVERVIEW,
      scope: 'product',
      scope_label: '成品',
      stages: {
        inbound_to_pending_avg_hours: 8.67,
        pending_to_result_avg_hours: 48.0,
      },
    })
    await mount('product')
    expect(apiClient.fetchWarehouseInspectionProgressOverview).toHaveBeenCalledWith('product', 30)
    const text = container.textContent ?? ''
    expect(text).toContain('成品')
    expect(text).toContain('分段平均时长')
    expect(text).toContain('待验→结果')
  })

  it('renders nothing when the overview request fails', async () => {
    apiClient.fetchWarehouseInspectionProgressOverview.mockRejectedValue(
      new Error('服务不可用')
    )
    await mount('raw', false)
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(container.textContent).toBe('')
  })
})
