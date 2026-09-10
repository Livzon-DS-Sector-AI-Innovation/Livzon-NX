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
    },
  ],
  stages: null,
}

describe('WarehouseInspectionProgressPanel', () => {
  let container: HTMLDivElement
  let root: Root
  let client: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    apiClient.fetchWarehouseInspectionProgressOverview.mockResolvedValue(OVERVIEW)
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
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 60))
      })
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
