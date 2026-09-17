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
  data: [{ record_id: 'rec-1', 设备名称: '空压机' }],
  meta: {
    total: 1,
    page: 1,
    page_size: 20,
    configured: true,
    fields: ['设备名称'],
  },
}

const FORM_URL =
  'https://j0eukrlohu.feishu.cn/share/base/form/shrcnexQSNoIwPZ8LPOL6nuKOF0'

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  window.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  window.URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

async function renderTable(formUrl: string | null) {
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [{ field_name: '设备名称', ui_type: 'Text', editable: true }],
    can_push: true,
    form_url: formUrl,
  })
  const openMock = vi.fn()
  vi.stubGlobal('open', openMock)
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(LIST), {
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
            title="设备维修记录"
            listApi="/api/v1/quality/instruments/repair"
            entityCode="qc_instr_repair"
            editable
            createFormOnly
          />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
  return { openMock }
}

function findCreateButton() {
  return Array.from(document.querySelectorAll('button')).find(
    (node) => node.textContent === '新增'
  )
}

describe('InspectionFeishuTable 仅表单新增（createFormOnly）', () => {
  it('配置了表单链接：新增只打开飞书表单，不打开本地弹窗', async () => {
    const { openMock } = await renderTable(FORM_URL)
    const button = findCreateButton()
    expect(button).toBeTruthy()
    await act(async () => {
      button!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(openMock).toHaveBeenCalledTimes(1)
    expect(String(openMock.mock.calls[0]?.[0])).toBe(FORM_URL)
    // 本地新增弹窗不应出现
    expect(document.body.textContent).not.toContain('取消')
  })

  it('未配置表单链接：不显示新增按钮（不回退本地弹窗）', async () => {
    await renderTable(null)
    expect(findCreateButton()).toBeUndefined()
  })
})
