/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

let mockSearchParams = new URLSearchParams()

vi.mock('next/navigation', () => ({
  useSearchParams: () => mockSearchParams,
}))

const apiClient = vi.hoisted(() => ({
  fetchAnomalyReportYears: vi.fn(),
  fetchAnomalyReportFields: vi.fn(),
  fetchAnomalyReportRecords: vi.fn(),
  fetchAnomalyReportShareLinks: vi.fn(),
  fetchDepartmentContacts: vi.fn(),
}))

const anomalyActions = vi.hoisted(() => ({
  createAnomalyReportRecord: vi.fn(),
  updateAnomalyReportRecord: vi.fn(),
  deleteAnomalyReportRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/finished-product-anomaly', () => anomalyActions)

import { FinishedProductAnomalyTablePage } from './FinishedProductAnomalyTablePage'

const FIELD_METAS_2026 = [
  { field_name: '自动编号', ui_type: 'AutoNumber', editable: false, options: null },
  { field_name: '数据来源', ui_type: 'SingleSelect', editable: true, options: [{ name: '客户投诉' }] },
  { field_name: '涉及产品', ui_type: 'SingleSelect', editable: true, options: [{ name: '洛伐他汀' }] },
  { field_name: '不合格项目描述', ui_type: 'Text', editable: true, options: null },
  { field_name: '相关照片', ui_type: 'Attachment', editable: false, options: null },
  { field_name: '提交时间', ui_type: 'CreatedTime', editable: false, options: null },
  { field_name: '提交人', ui_type: 'CreatedUser', editable: false, options: null },
  { field_name: '调查结果说明', ui_type: 'Attachment', editable: false, options: null },
  { field_name: '是否结案', ui_type: 'SingleSelect', editable: true, options: [{ name: '是' }, { name: '否' }] },
  { field_name: '跟踪情况', ui_type: 'Text', editable: true, options: null },
]

const FIELD_METAS_2025 = [
  { field_name: '发现时间', ui_type: 'DateTime', editable: true, options: null },
  { field_name: '数据来源', ui_type: 'SingleSelect', editable: true, options: [{ name: 'QC检测' }] },
  { field_name: '不合格项目', ui_type: 'Text', editable: true, options: null },
  { field_name: '洛伐他汀', ui_type: 'Attachment', editable: false, options: null },
  { field_name: '调查结果说明', ui_type: 'Attachment', editable: false, options: null },
  { field_name: '是否结案', ui_type: 'SingleSelect', editable: true, options: [{ name: '是' }, { name: '否' }] },
]

const RECORDS_2026 = [
  {
    record_id: 'rec-1',
    自动编号: '1',
    数据来源: '客户投诉',
    涉及产品: '洛伐他汀',
    不合格项目描述: '含量测定超出标准限度',
    相关照片: [{ name: 'photo.jpeg', file_token: 'ft-1', url: '', size: 10 }],
    提交时间: '1785513600000',
    调查结果说明: [{ name: 'report.pdf', file_token: 'ft-2', url: '', size: 30 }],
    是否结案: '否',
    跟踪情况: '调查中',
  },
]

const RECORDS_2025 = [
  {
    record_id: 'rec-25',
    发现时间: '1733068800000',
    数据来源: 'QC检测',
    不合格项目: '甲醇溶解性中有不溶白色颗粒',
    洛伐他汀: [{ name: 'lft.jpeg', file_token: 'ft-25', url: '', size: 12 }],
    调查结果说明: [{ name: 'result.pdf', file_token: 'ft-25b', url: '', size: 30 }],
    是否结案: '是',
  },
]

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

describe('FinishedProductAnomalyTablePage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    mockSearchParams = new URLSearchParams()
    apiClient.fetchAnomalyReportYears.mockResolvedValue([
      { year: 2025, entity_code: 'finished_product_anomaly_2025', table_configured: true, feishu_url: 'https://www.feishu.cn/base/tok_2025?table=tbl_2025' },
      { year: 2026, entity_code: 'finished_product_anomaly_2026', table_configured: true, feishu_url: 'https://www.feishu.cn/base/tok_2026?table=tbl_2026' },
    ])
    apiClient.fetchAnomalyReportFields.mockImplementation(async (year: number) => ({
      fields: year === 2025 ? FIELD_METAS_2025 : FIELD_METAS_2026,
      can_push: true,
    }))
    apiClient.fetchAnomalyReportRecords.mockImplementation(async (year: number) => ({
      items: year === 2025 ? RECORDS_2025 : RECORDS_2026,
      total: 1,
      page: 1,
      page_size: 20,
      table_configured: true,
    }))
    apiClient.fetchDepartmentContacts.mockResolvedValue([])
    apiClient.fetchAnomalyReportShareLinks.mockResolvedValue({
      'rec-1': 'https://j0eukrlohu.feishu.cn/record/tok-rec-1',
      'rec-25': 'https://j0eukrlohu.feishu.cn/record/tok-rec-25',
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message, .ant-drawer').forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderPage() {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <FinishedProductAnomalyTablePage />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    // 两阶段加载：years 解析出默认年份后才发 fields/list 请求，轮询等分页总数渲染
    await waitFor(() => (container.textContent || '').includes('共 1 条'))
  }

  async function waitFor(
    condition: () => unknown,
    timeoutMs = 1500,
  ): Promise<void> {
    for (let i = 0; i < Math.ceil(timeoutMs / 30); i++) {
      if (condition()) return
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 30))
      })
    }
  }

  it('defaults to the latest configured year with 2026 column overrides', async () => {
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('成品异常报告台账（2026年）')
    expect(text).toContain('含量测定超出标准限度')
    const headers = Array.from(container.querySelectorAll('.ant-table-thead th')).map(
      (node) => node.textContent || '',
    )
    // 列表只保留 数据来源 → 调查结果说明，其余进详情
    expect(headers).not.toContain('自动编号')
    expect(headers).not.toContain('是否结案')
    expect(headers).not.toContain('跟踪情况')
    expect(headers).toContain('数据来源')
    expect(headers).toContain('涉及产品')
    expect(headers).toContain('不合格项目描述')
    expect(headers).toContain('相关照片')
    expect(headers).toContain('提交时间')
    expect(headers).toContain('调查结果说明')
    // 毫秒时间戳字符串按日期呈现（CreatedTime 分支）
    expect(text).not.toContain('1785513600000')
    // 列宽档位：窄列 90px / 中列 108px（1.2 倍）/ 加宽列 26%
    const colWidths = Array.from(container.querySelectorAll('.ant-table col')).map(
      (col) => col.getAttribute('style') || '',
    )
    expect(colWidths.some((style) => style.includes('90px'))).toBe(true)
    expect(colWidths.some((style) => style.includes('108px'))).toBe(true)
    expect(colWidths.some((style) => style.includes('26%'))).toBe(true)
    expect(apiClient.fetchAnomalyReportRecords).toHaveBeenCalledWith(2026, {
      keyword: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('applies 2025 overrides: excluded fields only in the drawer, no auto column', async () => {
    mockSearchParams = new URLSearchParams('year=2025')
    await renderPage()
    const headers = Array.from(container.querySelectorAll('.ant-table-thead th')).map(
      (node) => node.textContent || '',
    )
    expect(headers).toContain('发现时间')
    expect(headers).toContain('不合格项目')
    // 调查结果说明/是否结案只进详情
    expect(headers).not.toContain('调查结果说明')
    expect(headers).not.toContain('是否结案')
    // 首列点击打开详情抽屉，抽屉中可见被排除字段
    const titleLink = container.querySelector('.ant-table-tbody td:first-child a')
    expect(titleLink).toBeTruthy()
    await act(async () => {
      ;(titleLink as HTMLElement | null)?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const drawerText = document.body.textContent || ''
    expect(drawerText).toContain('成品异常报告详情')
    expect(drawerText).toContain('调查结果说明')
    expect(drawerText).toContain('是否结案')
    expect(drawerText).toContain('result.pdf')
  })

  it('opens the attachment preview modal when clicking a file link', async () => {
    await renderPage()
    const fileButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => (btn.textContent || '') === 'report.pdf',
    )
    expect(fileButton).toBeTruthy()
    await act(async () => {
      fileButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    // antd Modal portal 到 body，弹窗内 iframe 指向预览端点并携带年份
    const iframe = document.body.querySelector('.ant-modal iframe')
    expect(iframe).toBeTruthy()
    expect(iframe?.getAttribute('src')).toContain(
      '/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft-2/preview?year=2026',
    )
  })

  it('only offers configured years in the selector and switches via selection', async () => {
    await renderPage()
    const wrapper = container.querySelector('.ant-select') as HTMLElement | null
    expect(wrapper).toBeTruthy()
    await act(async () => {
      wrapper?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      wrapper?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const options = Array.from(document.body.querySelectorAll('.ant-select-item-option'))
    expect(options.some((item) => (item.textContent || '').includes('2025年'))).toBe(true)
    const option2027 = options.find((item) => (item.textContent || '').includes('2027年'))
    expect(option2027).toBeUndefined()
    const option2025 = options.find((item) => (item.textContent || '').includes('2025年')) as HTMLElement
    await act(async () => {
      option2025?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(apiClient.fetchAnomalyReportRecords).toHaveBeenLastCalledWith(2025, {
      keyword: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('initializes the year from the ?year= query parameter', async () => {
    mockSearchParams = new URLSearchParams('year=2025')
    await renderPage()
    expect(apiClient.fetchAnomalyReportRecords).toHaveBeenCalledWith(2025, {
      keyword: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('warns and disables create when no year table is configured', async () => {
    apiClient.fetchAnomalyReportYears.mockResolvedValue([
      { year: 2026, entity_code: 'finished_product_anomaly_2026', table_configured: false, feishu_url: null },
    ])
    apiClient.fetchAnomalyReportRecords.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      table_configured: false,
    })
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('成品异常报告飞书表未配置')
    const createButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('新增'),
    ) as HTMLButtonElement | null
    expect(createButton?.disabled).toBe(true)
  })

  it('opens the Feishu table link from the toolbar button', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    await renderPage()
    const button = Array.from(container.querySelectorAll('button')).find(
      (btn) => (btn.textContent || '').includes('打开飞书表格'),
    )
    expect(button).toBeTruthy()
    await act(async () => {
      button?.click()
    })
    expect(openMock).toHaveBeenCalledWith(
      'https://www.feishu.cn/base/tok_2026?table=tbl_2026',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('opens the per-row Feishu share link from the row action', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    await renderPage()
    const rowButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.getAttribute('title') === '打开飞书对应行',
    )
    expect(rowButton).toBeTruthy()
    await act(async () => {
      rowButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(apiClient.fetchAnomalyReportShareLinks).toHaveBeenCalledWith(2026, ['rec-1'])
    expect(openMock).toHaveBeenCalledWith(
      'https://j0eukrlohu.feishu.cn/record/tok-rec-1',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('confirms, deletes and invalidates the list', async () => {
    anomalyActions.deleteAnomalyReportRecord.mockResolvedValue({ record_id: 'rec-1' })
    await renderPage()
    const deleteButton = container.querySelector('.anticon-delete')?.closest('button')
    expect(deleteButton).toBeTruthy()
    await act(async () => {
      deleteButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const confirmOk = document.body.querySelector('.ant-modal-confirm .ant-btn-primary')
    expect(confirmOk).toBeTruthy()
    const requestCount = apiClient.fetchAnomalyReportRecords.mock.calls.length
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 250))
    })
    expect(anomalyActions.deleteAnomalyReportRecord).toHaveBeenCalledWith(2026, 'rec-1')
    expect(document.body.textContent).toContain('删除成功')
    expect(apiClient.fetchAnomalyReportRecords.mock.calls.length).toBeGreaterThan(requestCount)
  })

  it('creates a record through the editor modal', async () => {
    anomalyActions.createAnomalyReportRecord.mockResolvedValue({ record_id: 'rec-new' })
    await renderPage()
    const createButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('新增'),
    )
    expect(createButton).toBeTruthy()
    await act(async () => {
      createButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('新增成品异常报告（2026年）')
    const descItem = Array.from(document.body.querySelectorAll('.ant-form-item')).find(
      (item) => (item.querySelector('.ant-form-item-label')?.textContent || '').includes('不合格项目描述'),
    )
    const descInput = descItem?.querySelector('input') as HTMLInputElement | null
    expect(descInput).toBeTruthy()
    await act(async () => {
      if (descInput) {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(
          descInput,
          '新增异常描述',
        )
        descInput.dispatchEvent(new Event('input', { bubbles: true }))
      }
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const confirmOk = document.body.querySelector('.ant-modal-footer .ant-btn-primary')
    expect(confirmOk).toBeTruthy()
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(anomalyActions.createAnomalyReportRecord).toHaveBeenCalledWith(
      2026,
      expect.objectContaining({ 不合格项目描述: '新增异常描述' }),
    )
    expect(document.body.textContent).toContain('成品异常报告记录已创建')
  })

  it('filters the list by keyword and refetches', async () => {
    await renderPage()
    const searchInput = Array.from(container.querySelectorAll('input')).find(
      (input) => (input as HTMLInputElement).placeholder === '关键词搜索',
    ) as HTMLInputElement | null
    expect(searchInput).toBeTruthy()
    await act(async () => {
      if (searchInput) {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(
          searchInput,
          '含量',
        )
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
      }
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(apiClient.fetchAnomalyReportRecords).toHaveBeenLastCalledWith(2026, {
      keyword: '含量',
      page: 1,
      page_size: 20,
    })
  })

  it('surfaces the backend message when the list query fails', async () => {
    apiClient.fetchAnomalyReportRecords.mockRejectedValue(new Error('飞书连接超时'))
    await renderPage()
    await waitFor(() => (document.body.textContent || '').includes('飞书连接超时'))
    expect(document.body.textContent).toContain('飞书连接超时')
  })
})
