/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetchDeviationStatistics: vi.fn() }))
vi.mock('@/lib/api/client/quality', () => ({ fetchDeviationStatistics: mocks.fetchDeviationStatistics }))
vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option?: unknown }) =>
    React.createElement('pre', { 'data-testid': 'echart' }, JSON.stringify(option ?? {})),
}))
vi.mock('next/link', () => ({
  default: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('a', null, children),
}))
import { DeviationDashboardPage } from './DeviationDashboardPage'

let root: Root
let container: HTMLDivElement
let client: QueryClient

const stats = {
  total: 6,
  closedCount: 4,
  majorCount: 1,
  levelDistribution: [
    { name: 'minor', count: 3 },
    { name: 'major', count: 1 },
    { name: '未定级', count: 2 },
  ],
  departmentDistribution: [
    { name: 'QC', count: 4 },
    { name: 'QA', count: 2 },
  ],
  rootCauseDistribution: [
    { name: '人员', count: 2 },
    { name: '设施/设备', count: 1 },
  ],
  monthlyTrend: [
    { month: '2026-08', count: 2 },
    { month: '2026-09', count: 4 },
  ],
}

beforeEach(() => {
  mocks.fetchDeviationStatistics.mockReset()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
})

async function renderDashboard() {
  await act(async () => root.render(
    <App>
      <QueryClientProvider client={client}>
        <DeviationDashboardPage />
      </QueryClientProvider>
    </App>,
  ))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
}

function chartText() {
  return Array.from(container.querySelectorAll('[data-testid="echart"]'))
    .map((node) => node.textContent)
    .join('\n')
}

it('renders charts with 人机料法环 cause labels and level translations', async () => {
  mocks.fetchDeviationStatistics.mockResolvedValue(stats)
  await renderDashboard()

  expect(mocks.fetchDeviationStatistics).toHaveBeenCalledOnce()
  expect(container.textContent).toContain('偏差总数')
  expect(container.textContent).toContain('严重偏差')
  expect(container.textContent).not.toContain('暂无数据')

  const rendered = chartText()
  expect(rendered).toContain('人员（人）')
  expect(rendered).toContain('设施/设备（机）')
  expect(rendered).toContain('次要偏差')
  expect(rendered).toContain('严重偏差')
  expect(rendered).toContain('2026-09')
})

it('shows a retry empty state when statistics fail to load', async () => {
  mocks.fetchDeviationStatistics.mockRejectedValueOnce(new Error('统计暂不可用'))
  await renderDashboard()

  expect(container.textContent).toContain('统计数据加载失败')
  const retry = Array.from(container.querySelectorAll('button')).find(
    (button) => button.textContent?.replace(/\s/g, '') === '重试',
  )
  expect(retry).toBeDefined()

  mocks.fetchDeviationStatistics.mockResolvedValue(stats)
  await act(async () => retry?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
  expect(mocks.fetchDeviationStatistics).toHaveBeenCalledTimes(2)
  expect(container.textContent).not.toContain('统计数据加载失败')
})

it('falls back to empty placeholders for absent distributions', async () => {
  mocks.fetchDeviationStatistics.mockResolvedValue({
    ...stats,
    levelDistribution: [],
    departmentDistribution: [],
    rootCauseDistribution: [],
    monthlyTrend: [],
  })
  await renderDashboard()

  expect(container.textContent).toContain('暂无数据')
  expect(container.querySelectorAll('[data-testid="echart"]').length).toBe(0)
})
