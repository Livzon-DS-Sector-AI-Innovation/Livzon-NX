/* @vitest-environment happy-dom */

import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EmployeeStats } from '@/types/hr'

const queryState = vi.hoisted(() => ({
  data: undefined as { code: number; data: EmployeeStats } | undefined,
  isLoading: false,
  isError: false,
  isFetching: false,
  refetch: () => {},
}))
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => queryState,
  QueryClient: class {},
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock('@/lib/api/client/hr', () => ({ fetchEmployeeStats: vi.fn() }))
vi.mock('./EmployeeQrCode', () => ({ default: () => null }))

import EmployeeDashboardClient from './EmployeeDashboardClient'
import EmployeeDashboardView from './EmployeeDashboardView'

const baseStats: EmployeeStats = {
  total: 828,
  status_distribution: { 正式: 802, 试用期: 24, 实习生: 2 },
  department_distribution: [{ department: '质量部', count: 30 }],
  education_distribution: { 本科: 100 },
  contract_expiring_count: 0,
  contract_expiring_list: [],
  contract_expiring_90d_count: 35,
  contract_expiring_90d_list: [],
  probation_due_count: 3,
  probation_due_list: [],
  certificate_due_count: 2,
  certificate_due_list: [],
  hires_this_month: 4,
  departures_this_month: 1,
}

function viewMarkup(stats: EmployeeStats) {
  return renderToStaticMarkup(<EmployeeDashboardView stats={stats} />)
}

function statisticValues(markup: string) {
  // happy-dom 解析 antd 图标 SVG 中的 <defs><style> 会截断 DOM，先剥离再断言
  const container = document.createElement('div')
  container.innerHTML = markup.replace(/<svg[\s\S]*?<\/svg>/g, '')
  return Array.from(container.querySelectorAll('.ant-statistic')).reduce<Record<string, string>>(
    (acc, node) => {
      const title = node.querySelector('.ant-statistic-title')?.textContent?.trim() ?? ''
      const value = node.querySelector('.ant-statistic-content')?.textContent?.trim() ?? ''
      if (title) acc[title] = value
      return acc
    },
    {},
  )
}

describe('employee dashboard view statistics', () => {
  it('renders status, turnover and reminder cards with feishu status values', () => {
    const values = statisticValues(viewMarkup(baseStats))
    expect(values['员工总数']).toBe('828')
    expect(values['正式员工']).toBe('802')
    expect(values['试用期']).toBe('24')
    expect(values['实习生']).toBe('2')
    expect(values['本月入职']).toBe('4')
    expect(values['本月离职']).toBe('1')
    expect(values['合同到期·本季度']).toBe('0')
    expect(values['合同到期·未来90天']).toBe('35')
    expect(values['试用期转正·30天内']).toBe('3')
    expect(values['证书复审·90天内']).toBe('2')
  })

  it('merges locally created “在职” employees into the formal card', () => {
    const values = statisticValues(
      viewMarkup({
        ...baseStats,
        total: 17,
        status_distribution: { 正式: 10, 在职: 5, 试用期: 2 },
      }),
    )
    expect(values['正式员工']).toBe('15')
    expect(values['试用期']).toBe('2')
    expect(values['实习生']).toBe('0')
  })

  it('shows department ratio column, deep links and reminder tab labels', () => {
    const markup = viewMarkup(baseStats)
    expect(markup).toContain('占比')
    expect(markup).toContain('href="/hr/profile?department=')
    expect(markup).toContain('合同到期·本季度 (0)')
    expect(markup).toContain('合同到期·未来90天 (35)')
    expect(markup).toContain('试用期转正·30天内 (3)')
    expect(markup).toContain('证书复审·90天内 (2)')
    expect(markup).toContain('部门分布（点击部门查看员工档案）')
  })
})

describe('employee dashboard client data flow', () => {
  beforeEach(() => {
    queryState.isLoading = false
    queryState.isError = false
    queryState.data = undefined
  })

  it('renders view with stats payload from the query', () => {
    queryState.data = { code: 0, data: baseStats }
    const markup = renderToStaticMarkup(<EmployeeDashboardClient />)
    expect(markup).toContain('员工管理')
    expect(markup).toContain('刷新数据')
    expect(statisticValues(markup)['员工总数']).toBe('828')
  })

  it('renders loading and error states instead of empty cards', () => {
    queryState.isLoading = true
    expect(renderToStaticMarkup(<EmployeeDashboardClient />)).toContain('员工统计加载中')

    queryState.isLoading = false
    queryState.isError = true
    expect(renderToStaticMarkup(<EmployeeDashboardClient />)).toContain('员工统计数据加载失败')
  })
})
