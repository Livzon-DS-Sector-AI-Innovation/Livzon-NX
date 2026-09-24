/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetchStats: vi.fn() }))
vi.mock('@/lib/api/client/quality', () => ({ fetchCapaStatistics: mocks.fetchStats }))
vi.mock('next/link', () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }))
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="chart" /> }))

import { CapaDashboardPage } from './CapaDashboardPage'

let root: Root
let container: HTMLDivElement
let client: QueryClient

beforeEach(() => {
  mocks.fetchStats.mockReset()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  vi.restoreAllMocks()
})

async function renderPage() {
  await act(async () => root.render(
    <App>
      <QueryClientProvider client={client}>
        <CapaDashboardPage />
      </QueryClientProvider>
    </App>,
  ))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}

const STATS = {
  total: 6,
  closedCount: 4,
  inProgressCount: 2,
  resultDistribution: [
    { name: '有效', count: 3 },
    { name: '进行中', count: 2 },
    { name: '未填', count: 1 },
  ],
  departmentDistribution: [
    { name: 'QC', count: 5 },
    { name: '未填', count: 1 },
  ],
  monthlyTrend: [
    { month: '2026-04', count: 0 },
    { month: '2026-05', count: 0 },
    { month: '2026-06', count: 0 },
    { month: '2026-07', count: 0 },
    { month: '2026-08', count: 0 },
    { month: '2026-09', count: 6 },
  ],
}

it('shows ledger-oriented cards and charts from local statistics', async () => {
  mocks.fetchStats.mockResolvedValue(STATS)
  await renderPage()
  expect(container.textContent).toContain('CAPA总数')
  expect(container.textContent).toContain('进行中')
  expect(container.textContent).toContain('已关闭（关闭率 67%）')
  for (const title of ['CAPA效果评估分布', '事件部门分布', '近 6 个月启动趋势']) {
    expect(container.textContent).toContain(title)
  }
  // 旧的「状态/来源分布」不再出现
  expect(container.textContent).not.toContain('状态分布')
  expect(container.textContent).not.toContain('来源分布')
  expect(mocks.fetchStats).toHaveBeenCalledTimes(1)
})

it('offers retry when statistics fail to load', async () => {
  mocks.fetchStats.mockRejectedValueOnce(new Error('boom'))
  await renderPage()
  expect(container.textContent).toContain('统计数据加载失败')
  mocks.fetchStats.mockResolvedValue(STATS)
  const retry = Array.from(container.querySelectorAll('button')).find(b => b.textContent?.replace(/\s/g, '') === '重试')
  expect(retry).toBeDefined()
  await act(async () => retry!.click())
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
  expect(mocks.fetchStats).toHaveBeenCalledTimes(2)
  expect(container.textContent).toContain('已关闭（关闭率 67%）')
})