/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const apiClient = vi.hoisted(() => ({
  fetchInspectionFeishuFields: vi.fn(),
  fetchInspectionFeishuRecordDetail: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)

import { InspectionFeishuTable } from './InspectionFeishuTable'

const LIST = {
  data: [{ record_id: 'rec-1', 设备名称: '高效液相色谱仪' }],
  meta: {
    total: 1,
    page: 1,
    page_size: 20,
    configured: true,
    fields: ['设备名称'],
  },
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [{ field_name: '设备名称', ui_type: 'Text', editable: true }],
    can_push: true,
  })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

async function renderTable(props: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(LIST), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InspectionFeishuTable
            title="设备维护保养记录"
            listApi="/api/v1/quality/instruments/maintenance"
            entityCode="qc_instr_maintenance"
            {...props}
          />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
  return fetchMock
}

function firstListUrl(fetchMock: ReturnType<typeof vi.fn>) {
  const url = String(fetchMock.mock.calls[0]?.[0] ?? '')
  const query = url.split('?')[1] ?? ''
  return new URLSearchParams(query)
}

describe('InspectionFeishuTable 月份过滤', () => {
  it('monthFilter 传入时列表请求带 month=YYYY-MM', async () => {
    const fetchMock = await renderTable({ monthFilter: '2026-09' })
    const params = firstListUrl(fetchMock)
    expect(params.get('month')).toBe('2026-09')
  })

  it('monthFilter 为空串（月份被清空）时请求不带 month，即全部内容', async () => {
    const fetchMock = await renderTable({ monthFilter: '' })
    const params = firstListUrl(fetchMock)
    expect(params.get('month')).toBeNull()
  })
})
