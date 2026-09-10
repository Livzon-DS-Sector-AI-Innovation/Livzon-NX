/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}))

const pushMock = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}))

const apiClient = vi.hoisted(() => ({
  fetchAnomalyDashboard: vi.fn(),
  fetchAnomalyAnalysisStatus: vi.fn(),
  fetchAnomalyReportYears: vi.fn(),
  fetchAnomalyReportFields: vi.fn(),
  fetchAnomalyReportRecords: vi.fn(),
}))

const anomalyActions = vi.hoisted(() => ({
  runAnomalyAnalysisAction: vi.fn(),
  createAnomalyReportRecord: vi.fn(),
  updateAnomalyReportRecord: vi.fn(),
  deleteAnomalyReportRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/finished-product-anomaly', () => anomalyActions)

import { FinishedProductAnomalyDashboard } from './FinishedProductAnomalyDashboard'

const YEARS = [
  { year: 2025, entity_code: 'finished_product_anomaly_2025', table_configured: true, feishu_url: 'https://www.feishu.cn/base/tok_2025?table=tbl_2025' },
  { year: 2026, entity_code: 'finished_product_anomaly_2026', table_configured: true, feishu_url: 'https://www.feishu.cn/base/tok_2026?table=tbl_2026' },
]

const DASHBOARD_DATA = {
  years: [2025, 2026],
  total: 486,
  analyzed: 400,
  unclassified: 86,
  ai_configured: true,
  last_analyzed_at: '2026-09-08T08:00:00+00:00',
  products: [
    {
      product: '霉酚酸',
      count: 120,
      types: [
        { type: '杂质异常', count: 100 },
        { type: '异物混入', count: 20 },
      ],
    },
    {
      product: 'L-苯丙氨酸',
      count: 90,
      types: [
        { type: '异物混入', count: 50 },
        { type: '性状与外观异常', count: 40 },
      ],
    },
  ],
  type_totals: [
    { type: '异物混入', count: 70 },
    { type: '杂质异常', count: 100 },
    { type: '性状与外观异常', count: 40 },
  ],
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

describe('FinishedProductAnomalyDashboard', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    apiClient.fetchAnomalyReportYears.mockResolvedValue(YEARS)
    apiClient.fetchAnomalyDashboard.mockResolvedValue(DASHBOARD_DATA)
    apiClient.fetchAnomalyAnalysisStatus.mockResolvedValue({
      job_id: 'job:x',
      state: 'completed',
      progress: '完成',
      result: { analyzed: 86 },
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.querySelectorAll('.ant-message').forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderPage() {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <FinishedProductAnomalyDashboard />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
  }

  it('renders aggregate statistics, charts and year selector for configured years', async () => {
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('成品异常报告总览')
    expect(text).toContain('异常记录总数')
    expect(text).toContain('486')
    expect(text).toContain('各产品异常数量（按异常类型堆叠）')
    expect(text).toContain('异常类型分布')
    expect(document.querySelector('[data-testid="echarts-mock"]')).toBeTruthy()
    // 未配置年份不出现在筛选中
    await act(async () => {
      const wrapper = container.querySelector('.ant-select') as HTMLElement | null
      wrapper?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      wrapper?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const options = Array.from(document.body.querySelectorAll('.ant-select-item-option')).map(
      (node) => node.textContent || '',
    )
    expect(options).toContain('全部年份')
    expect(options).toContain('2025年')
    expect(options.some((item) => item.includes('2027'))).toBe(false)
  })

  it('shows the pending count on the AI analysis button and starts the job', async () => {
    anomalyActions.runAnomalyAnalysisAction.mockResolvedValue({
      job_id: 'job:x',
      years: [2025, 2026],
    })
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('AI 分类（86 条待分析）')
    const runButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('AI 分类'),
    )
    await act(async () => {
      runButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 120))
    })
    expect(anomalyActions.runAnomalyAnalysisAction).toHaveBeenCalledWith(undefined)
    // 任务启动后轮询进度并在完成时刷新聚合
    expect(apiClient.fetchAnomalyAnalysisStatus).toHaveBeenCalledWith('job:x')
    // AI 助手按钮存在（打开聊天抽屉）
    expect(
      Array.from(container.querySelectorAll('button')).some((btn) =>
        (btn.textContent || '').includes('AI 助手'),
      ),
    ).toBe(true)
  })

  it('warns when AI service is not configured', async () => {
    apiClient.fetchAnomalyDashboard.mockResolvedValue({
      ...DASHBOARD_DATA,
      ai_configured: false,
    })
    await renderPage()
    expect(container.textContent).toContain('AI 服务尚未配置')
  })

  it('refetches the aggregation when the year filter changes', async () => {
    await renderPage()
    const before = apiClient.fetchAnomalyDashboard.mock.calls.length
    const wrapper = container.querySelector('.ant-select') as HTMLElement | null
    await act(async () => {
      wrapper?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      wrapper?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const option2025 = Array.from(
      document.body.querySelectorAll('.ant-select-item-option'),
    ).find((item) => (item.textContent || '').includes('2025年')) as HTMLElement
    await act(async () => {
      option2025?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(apiClient.fetchAnomalyDashboard).toHaveBeenLastCalledWith(2025)
    expect(apiClient.fetchAnomalyDashboard.mock.calls.length).toBeGreaterThan(before)
  })

  it('navigates to the year ledger from the entry card', async () => {
    const originalHref = window.location.href
    await renderPage()
    const ledgerButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('2025年台账'),
    )
    expect(ledgerButton).toBeTruthy()
    await act(async () => {
      ledgerButton?.click()
    })
    expect(window.location.href.endsWith('/quality/anomaly-report/ledger?year=2025')).toBe(true)
    window.location.href = originalHref
  })
})
