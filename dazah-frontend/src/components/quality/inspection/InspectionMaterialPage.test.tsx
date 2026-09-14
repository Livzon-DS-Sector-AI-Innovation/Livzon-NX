/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const nextNav = vi.hoisted(() => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useSearchParams: vi.fn(() => new URLSearchParams()),
}))

vi.mock('next/navigation', () => nextNav)

const apiClient = vi.hoisted(() => ({
  fetchInspectionMaterials: vi.fn(),
  fetchInspectionFeishuFields: vi.fn(),
  fetchInspectionFeishuRecordDetail: vi.fn(),
}))

const inspectionActions = vi.hoisted(() => ({
  pullInspectionFeishuRecords: vi.fn(),
  deleteInspectionFeishuRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-inspection', () => inspectionActions)

import { InspectionMaterialPage } from './InspectionMaterialPage'

const MATERIALS = [
  { entity_code: 'qc_solid_ys001', label: 'YS001 食用葡萄糖', module: 'solid', group_key: 'ys-000', group_label: 'YS000' },
  { entity_code: 'qc_solid_ys008', label: 'YS008 活性炭', module: 'solid', group_key: 'ys-000', group_label: 'YS000' },
  { entity_code: 'qc_solid_ys015', label: 'YS015 活性炭（303型湿）', module: 'solid', group_key: 'ys-100', group_label: 'YS100' },
  { entity_code: 'qc_liquid_yl001', label: 'YL001 乙醇', module: 'liquid', group_key: 'yl-0xx', group_label: 'YL0xx' },
]

const RECORDS_RESPONSE = {
  data: [{ record_id: 'rec-old', 批号: 'YS001-2608001', 外观: '白色粉末' }],
  meta: { total: 1, page: 1, page_size: 20, configured: true, fields: ['批号', '外观'] },
}

const FETCHED_RECORD = {
  record_id: 'rec-new',
  created_at: '2026-09-14T00:00:00Z',
  updated_at: '2026-09-14T00:00:00Z',
  批号: 'YS015-2609001',
  外观: '黑色粉末',
}

let container: HTMLDivElement
let root: Root
let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  apiClient.fetchInspectionMaterials.mockResolvedValue(MATERIALS)
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [{ field_name: '批号', ui_type: 'Text', editable: true }],
    can_push: true,
  })
  nextNav.useSearchParams.mockReturnValue(new URLSearchParams())
  fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(RECORDS_RESPONSE), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

async function renderPage(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InspectionMaterialPage module="solid" {...props} />
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
    try {
      if (condition()) return
    } catch {
      // 条件为断言时首轮未满足不中断，继续轮询
    }
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error('waitFor timeout')
}

function recordsFetchUrls(): string[] {
  return fetchMock.mock.calls
    .map((c) => String(c[0]))
    .filter((url) => url.includes('/inspection-solid/'))
}

describe('InspectionMaterialPage 固体物料检验单页', () => {
  it('默认选中第一个物料并加载其检验表，筛选只列本模块物料', async () => {
    await renderPage()
    await waitFor(() => expect(container.textContent).toContain('YS001 食用葡萄糖'))
    await waitFor(() => expect(container.textContent).toContain('YS001-2608001'))

    // 只加载固体物料列表（fetchInspectionMaterials 返回全部，页面按模块过滤）
    // 打开物料筛选下拉，不应出现液体物料
    const selector = container.querySelector('.ant-select') as HTMLElement
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 150))
    })
    const optionTexts = Array.from(document.body.querySelectorAll('.ant-select-item-option')).map(
      (o) => o.textContent || '',
    )
    expect(optionTexts).toContain('YS001 食用葡萄糖')
    expect(optionTexts).toContain('YS008 活性炭')
    expect(optionTexts).toContain('YS015 活性炭（303型湿）')
    expect(optionTexts).not.toContain('YL001 乙醇')
  })

  it('物料列表加载失败时提示错误并清空选择', async () => {
    apiClient.fetchInspectionMaterials.mockRejectedValue(new Error('飞书超时'))
    await renderPage()
    expect(document.body.textContent).toContain('物料列表加载失败')
    expect(document.body.textContent).toContain('重试')
  })

  it('切换物料后加载该物料对应分组子表的检验记录', async () => {
    await renderPage()
    await waitFor(() => expect(container.textContent).toContain('YS001-2608001'))

    const selector = container.querySelector('.ant-select') as HTMLElement
    await act(async () => {
      selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 150))
    })
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find(
      (o) => o.textContent?.includes('YS015 活性炭（303型湿）'),
    ) as HTMLElement | null
    expect(option).toBeTruthy()
    await act(async () => {
      option?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })

    // 选中后工具栏标签应切换为 YS015
    await waitFor(() => expect(container.textContent).toContain('YS015 活性炭（303型湿）'))

    const urls = recordsFetchUrls()
    expect(urls.some((url) => url.includes('/inspection-solid/ys-100/records'))).toBe(true)
    expect(urls.some((url) => url.includes('entity_code=qc_solid_ys015'))).toBe(true)
  })

  it('跳转携带 recordId/entityCode 时切到对应物料并按 id 直读详情打开抽屉', async () => {
    nextNav.useSearchParams.mockReturnValue(
      new URLSearchParams({ recordId: 'rec-new', entityCode: 'qc_solid_ys015' }),
    )
    apiClient.fetchInspectionFeishuRecordDetail.mockResolvedValue(FETCHED_RECORD)
    await renderPage()

    await waitFor(() => expect(document.body.textContent).toContain('记录详情'))
    expect(document.body.textContent).toContain('YS015-2609001')
    expect(apiClient.fetchInspectionFeishuRecordDetail).toHaveBeenCalledWith(
      'qc_solid_ys015',
      'rec-new',
    )
    // 页面物料筛选已切到 YS015
    expect(container.textContent).toContain('YS015 活性炭（303型湿）')
  })
})
