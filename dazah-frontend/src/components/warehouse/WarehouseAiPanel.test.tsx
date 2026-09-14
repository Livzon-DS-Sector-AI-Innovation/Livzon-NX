/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clientMocks = vi.hoisted(() => ({
  fetchWarehouseTrendSummary: vi.fn(),
  fetchWarehouseTrendAnomalies: vi.fn(),
  fetchWarehouseTrendProductLines: vi.fn(),
  fetchWarehouseHardwareCostAnomalies: vi.fn(),
  fetchWarehouseHardwareCostSummary: vi.fn(),
}))
const actionMocks = vi.hoisted(() => ({
  chatWarehouseAiAction: vi.fn(),
}))

vi.mock('@/lib/api/client/warehouse', () => clientMocks)
vi.mock('@/actions/warehouse', () => actionMocks)

import { WarehouseAiPanel } from './WarehouseAiPanel'

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  clientMocks.fetchWarehouseTrendSummary.mockResolvedValue(null)
  clientMocks.fetchWarehouseTrendAnomalies.mockResolvedValue([])
  clientMocks.fetchWarehouseTrendProductLines.mockResolvedValue([])
  clientMocks.fetchWarehouseHardwareCostAnomalies.mockResolvedValue([])
  clientMocks.fetchWarehouseHardwareCostSummary.mockResolvedValue(null)
  actionMocks.chatWarehouseAiAction.mockResolvedValue(null)
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
})

async function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <WarehouseAiPanel />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
}

describe('WarehouseAiPanel', () => {
  it('renders summary cards and empty states when no data is configured', async () => {
    await renderPanel()
    const text = document.body.textContent || ''
    expect(text).toContain('仓储AI分析')
    expect(text).toContain('暂无产品线趋势数据')
    expect(text).toContain('暂无趋势异常物料')
    expect(text).toContain('智能问答')
    expect(clientMocks.fetchWarehouseTrendSummary).toHaveBeenCalled()
  })
})
