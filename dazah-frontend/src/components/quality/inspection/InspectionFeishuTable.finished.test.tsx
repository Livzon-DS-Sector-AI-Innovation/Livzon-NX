/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchInspectionFeishuFields: vi.fn(),
}))

const inspectionActions = vi.hoisted(() => ({
  pullInspectionFeishuRecords: vi.fn(),
  deleteInspectionFeishuRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-inspection', () => inspectionActions)

import { InspectionFeishuTable } from './InspectionFeishuTable'

const LIST_RESPONSE = {
  data: [
    {
      record_id: 'rec-1',
      批号: 'PF-2607001',
      外观: '白色或类白色粉末，可见少量结晶，色泽均匀，无可见异物',
      报告单: [{ name: '报告单.pdf', file_token: 'ft-9', url: '', type: 'pdf' }],
    },
  ],
  meta: {
    total: 1,
    page: 1,
    page_size: 20,
    configured: true,
    fields: ['批号', '外观', '报告单'],
    last_sync_time: '2026-09-11T02:50:00+00:00',
  },
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [{ field_name: '批号', ui_type: 'Text', editable: true }],
    can_push: false,
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(LIST_RESPONSE), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  )
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function renderTable(props: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InspectionFeishuTable
            title="PF"
            listApi="/api/v1/quality/inspection-finished/pf/records"
            entityCode="qc_finished_pf"
            enableTextPreview
            enableAttachmentPreview
            showLastSyncTime
            {...props}
          />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30))
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

describe('InspectionFeishuTable 成品页增强', () => {
  it('纯文本单元格可点击并在弹窗中展示完整内容', async () => {
    await renderTable()
    await waitFor(() => expect(container.textContent).toContain('PF-2607001'))

    const textButton = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent?.includes('白色或类白色粉末'),
    )
    expect(textButton).toBeTruthy()
    act(() => {
      textButton?.click()
    })
    // 弹窗标题为字段名，正文展示完整文本（含被列宽截断的尾部）
    await waitFor(() => expect(document.body.textContent).toContain('外观'))
    expect(document.body.textContent).toContain('无可见异物')
  })

  it('镜像最近同步时间展示在工具栏', async () => {
    await renderTable()
    await waitFor(() => expect(container.textContent).toContain('最近同步'))
    expect(container.textContent).toContain('2026')
  })

  it('未开启 enableTextPreview 时文本保持纯文本', async () => {
    await renderTable({ enableTextPreview: false })
    await waitFor(() => expect(container.textContent).toContain('PF-2607001'))
    const textButton = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent?.includes('白色或类白色粉末'),
    )
    expect(textButton).toBeFalsy()
    expect(container.textContent).toContain('白色或类白色粉末')
  })

  it('文档附件点击弹窗在线预览（office/PDF 走后端 preview 端点）', async () => {
    await renderTable()
    await waitFor(() => expect(container.textContent).toContain('PF-2607001'))
    const attButton = Array.from(container.querySelectorAll('button')).find(
      (b) => b.textContent?.includes('报告单.pdf'),
    )
    expect(attButton).toBeTruthy()
    act(() => {
      attButton?.click()
    })
    // 弹窗标题为附件名，底部提供下载原文件入口
    await waitFor(() => expect(document.body.textContent).toContain('下载原文件'))
    expect(document.body.textContent).toContain('报告单.pdf')
  })
})
