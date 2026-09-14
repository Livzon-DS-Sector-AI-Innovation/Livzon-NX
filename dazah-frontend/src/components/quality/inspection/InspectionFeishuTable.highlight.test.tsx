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
  fetchInspectionMaterials: vi.fn(),
  fetchInspectionFeishuRecordDetail: vi.fn(),
}))

const inspectionActions = vi.hoisted(() => ({
  pullInspectionFeishuRecords: vi.fn(),
  deleteInspectionFeishuRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-inspection', () => inspectionActions)

import { InspectionFeishuTable } from './InspectionFeishuTable'

const LIST_WITHOUT_NEW = {
  data: [{ record_id: 'rec-old', 批号: 'YS001-2608001', 外观: '白色粉末' }],
  meta: {
    total: 1,
    page: 1,
    page_size: 20,
    configured: true,
    fields: ['批号', '外观'],
  },
}

const LIST_WITH_NEW = {
  data: [
    { record_id: 'rec-old', 批号: 'YS001-2608001', 外观: '白色粉末' },
    { record_id: 'rec-new', 批号: 'YS001-2609001', 外观: '白色结晶粉末' },
  ],
  meta: {
    total: 2,
    page: 1,
    page_size: 20,
    configured: true,
    fields: ['批号', '外观'],
  },
}

const FETCHED_RECORD = {
  record_id: 'rec-new',
  created_at: '2026-09-14T00:00:00Z',
  updated_at: '2026-09-14T00:00:00Z',
  批号: 'YS001-2609001',
  外观: '白色结晶粉末',
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [{ field_name: '批号', ui_type: 'Text', editable: true }],
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

async function renderTable(listResponse: Record<string, unknown>, highlightProps: Record<string, unknown> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(listResponse), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InspectionFeishuTable
            title="固体物料检验"
            listApi="/api/v1/quality/inspection-solid/ys-000/records"
            entityCode="qc_solid_ys001"
            editable
            createWithMaterialPicker
            {...highlightProps}
          />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
}

async function waitFor(condition: () => unknown, timeoutMs = 1500) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (condition()) return
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error('waitFor timeout')
}

describe('InspectionFeishuTable 跳转「列表并弹详情」', () => {
  it('列表镜像未包含新记录时，按 record_id 直读飞书详情并打开抽屉', async () => {
    apiClient.fetchInspectionFeishuRecordDetail.mockResolvedValue(FETCHED_RECORD)
    await renderTable(LIST_WITHOUT_NEW, {
      highlightRecordId: 'rec-new',
      highlightEntityCode: 'qc_solid_ys001',
    })

    await waitFor(() => expect(document.body.textContent).toContain('记录详情'))
    expect(document.body.textContent).toContain('YS001-2609001')
    expect(document.body.textContent).toContain('白色结晶粉末')
    expect(apiClient.fetchInspectionFeishuRecordDetail).toHaveBeenCalledWith(
      'qc_solid_ys001',
      'rec-new',
    )
  })

  it('列表已包含新记录时直接从列表数据打开详情抽屉', async () => {
    await renderTable(LIST_WITH_NEW, {
      highlightRecordId: 'rec-new',
      highlightEntityCode: 'qc_solid_ys001',
    })

    await waitFor(() => expect(document.body.textContent).toContain('记录详情'))
    expect(document.body.textContent).toContain('YS001-2609001')
    // 命中列表数据，不应再发详情请求
    expect(apiClient.fetchInspectionFeishuRecordDetail).not.toHaveBeenCalled()
  })

  it('highlightEntityCode 与当前列表实体不一致时不打开详情', async () => {
    await renderTable(LIST_WITH_NEW, {
      highlightRecordId: 'rec-new',
      highlightEntityCode: 'qc_solid_ys002',
    })

    await waitFor(() => expect(document.body.textContent).toContain('YS001-2608001'))
    expect(document.body.textContent).not.toContain('记录详情')
    expect(apiClient.fetchInspectionFeishuRecordDetail).not.toHaveBeenCalled()
  })
})
