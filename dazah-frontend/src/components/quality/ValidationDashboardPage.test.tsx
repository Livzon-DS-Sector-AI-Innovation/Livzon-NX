/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ValidationDashboardStats } from '@/types/quality'

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}))

const apiClient = vi.hoisted(() => ({
  fetchFeishuValidationDashboardStats: vi.fn(),
  fetchFeishuValidationUpcoming: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)

import { ValidationDashboardClient } from './ValidationDashboardPage'

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

const baseStats: ValidationDashboardStats = {
  total: 10,
  typeDistribution: [
    { validation_type: 'process_validation', count: 4 },
    { validation_type: 'equipment_qualification', count: 6 },
  ],
  statusDistribution: [
    { status: '进行中', count: 6 },
    { status: '完成', count: 4 },
  ],
  executionDistribution: [
    { validation_type: 'process_validation', count: 4 },
    { validation_type: 'equipment_qualification', count: 6 },
  ],
  revalidationUpcoming: 3,
  year_summaries: [
    { year: 2024, total: 6, completed: 4 },
    { year: 2025, total: 4, completed: 0 },
    { year: 2026, total: 0, completed: 0 },
    { year: 2027, total: 0, completed: 0 },
    { year: 2028, total: 0, completed: 0 },
  ],
}

const upcomingItems = [
  {
    record_id: 'r1',
    title: '纯化水系统再验证',
    validation_type: 'process_validation',
    status: '进行中',
    planned_end_date: '2026.02',
    department: '质量部',
    equipment_code: null,
    plan_name: '2026 验证方案',
    plan_code: null,
  },
  {
    record_id: 'r2',
    title: '设备B确认',
    validation_type: 'equipment_qualification',
    status: '待完成',
    planned_end_date: '2026.03.15',
    department: '工程部',
    equipment_code: 'EQ-1',
    plan_name: null,
    plan_code: null,
  },
]

describe('ValidationDashboardClient', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    apiClient.fetchFeishuValidationDashboardStats.mockResolvedValue(baseStats)
    apiClient.fetchFeishuValidationUpcoming.mockResolvedValue({
      items: upcomingItems,
      total: 2,
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body
      .querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message')
      .forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderPage(initialStats: ValidationDashboardStats | null = null) {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <ValidationDashboardClient initialStats={initialStats} />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
  }

  it('renders the dashboard stats from initial data', async () => {
    await renderPage(baseStats)
    const text = container.textContent || ''
    expect(text).toContain('验证与确认仪表盘')
    expect(text).toContain('验证总数')
    expect(text).toContain('近期待再验证')
    expect(text).toContain('3')
    expect(text).toContain('工艺验证')
    expect(text).toContain('设备确认')
    // 起始年份控件存在（默认为今年）
    expect(text).toContain('起始年份')
    expect(text).not.toContain('年度验证趋势')
    const yearInput = container.querySelector(
      '.ant-input-number input',
    ) as HTMLInputElement | null
    expect(yearInput?.value).toBe(String(new Date().getFullYear()))
  })

  it('re-fetches stats when the upcoming window changes', async () => {
    await renderPage()
    apiClient.fetchFeishuValidationDashboardStats.mockClear()

    const wrapper = container.querySelector('.ant-select') as HTMLElement | null
    expect(wrapper).toBeTruthy()
    await act(async () => {
      wrapper?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      wrapper?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })

    const option = Array.from(
      document.body.querySelectorAll('.ant-select-item-option'),
    ).find((node) => (node.textContent || '').includes('90天'))
    expect(option).toBeTruthy()
    await act(async () => {
      option?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 100))
    })

    expect(apiClient.fetchFeishuValidationDashboardStats).toHaveBeenCalledWith(
      90,
      new Date().getFullYear(),
    )
  })

  it('opens the upcoming detail modal when clicking the card', async () => {
    await renderPage()
    const cards = Array.from(container.querySelectorAll('.ant-card'))
    const upcomingCard = cards.find((card) =>
      (card.textContent || '').includes('近期待再验证'),
    )
    expect(upcomingCard).toBeTruthy()
    upcomingCard?.dispatchEvent(new MouseEvent('click', { bubbles: true }))

    const currentYear = new Date().getFullYear()
    // 弹窗打开后才触发取数（enabled: upcomingOpen），轮询等待数据渲染，
    // 避免固定 sleep 在慢环境（覆盖率插桩）下竞态
    let modalText = ''
    for (let i = 0; i < 30; i += 1) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100))
      })
      modalText = document.body.textContent || ''
      if (modalText.includes('纯化水系统再验证')) break
    }
    expect(apiClient.fetchFeishuValidationUpcoming).toHaveBeenCalledWith(
      30,
      currentYear,
      { page: 1, page_size: 10 },
    )
    expect(modalText).toContain(
      `近期待再验证（未来 30 天内，${currentYear} 年起）`,
    )
    expect(modalText).toContain('纯化水系统再验证')
    expect(modalText).toContain('设备B确认')
    // 到期时间文本格式展示为连字符
    expect(modalText).toContain('2026-02')
    expect(modalText).toContain('2026-03-15')
  })

  it('shows a hint when the master plan is not bound', async () => {
    apiClient.fetchFeishuValidationDashboardStats.mockResolvedValue({
      total: 0,
      typeDistribution: [],
      statusDistribution: [],
      executionDistribution: [],
      revalidationUpcoming: 0,
      year_summaries: [],
    })
    await renderPage()
    expect(container.textContent).toContain(
      '暂无数据，请确认已在同步设置中绑定验证主计划年度飞书表',
    )
  })

  it('shows an error alert when stats loading fails', async () => {
    apiClient.fetchFeishuValidationDashboardStats.mockRejectedValue(
      new Error('boom'),
    )
    await renderPage()
    expect(container.textContent).toContain('统计数据加载失败')
  })
})
