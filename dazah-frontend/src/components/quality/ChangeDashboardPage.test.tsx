/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchChangeDashboardStats: vi.fn(),
  fetchChangeActionPlanDueStatus: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchChangeDashboardStats: mocks.fetchChangeDashboardStats,
  fetchChangeActionPlanDueStatus: mocks.fetchChangeActionPlanDueStatus,
}))
vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option?: unknown }) =>
    React.createElement('pre', { 'data-testid': 'echart' }, JSON.stringify(option ?? {})),
}))
vi.mock('next/link', () => ({
  default: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('a', null, children),
}))
import { ChangeDashboardPage } from './ChangeDashboardPage'

const stats = {
  total: 151,
  closedCount: 0,
  delayCount: 0,
  statusDistribution: [{ status: 'draft', count: 151 }],
  levelDistribution: [{ level: '一级', count: 151 }],
  typeDistribution: [],
  departmentDistribution: [{ name: 'QC', count: 151 }],
  actionPlanTotal: 94,
  actionPlanOverdue: 55,
  actionPlanConfirmed: 0,
}

const dueStatus = (leadDays: number) => ({
  today: '2026-09-24',
  lead_days: leadDays,
  overdue: [
    {
      id: 'plan-overdue-1',
      change_code: 'BG-2601006',
      project_name: '逾期项目一',
      related_work: null,
      owner_name: '李文昊',
      owner_user_id: null,
      owner_avatar_url: null,
      director_name: null,
      deadline_date: '2026-09-20',
      delayed_deadline_date: null,
      status: '推进中',
      days_offset: -4,
    },
  ],
  due_soon: [
    {
      id: 'plan-soon-1',
      change_code: 'BG-2601019',
      project_name: '临期项目一',
      related_work: null,
      owner_name: '刘伟',
      owner_user_id: null,
      owner_avatar_url: null,
      director_name: null,
      deadline_date: '2026-09-28',
      delayed_deadline_date: null,
      status: '推进中',
      days_offset: 4,
    },
  ],
  total_count: 94,
  confirmed_count: 0,
})

let root: Root
let container: HTMLDivElement
let client: QueryClient

beforeEach(() => {
  mocks.fetchChangeDashboardStats.mockReset().mockResolvedValue(stats)
  mocks.fetchChangeActionPlanDueStatus.mockReset().mockImplementation(async (d: number) => dueStatus(d))
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  document.querySelectorAll('.ant-modal-root, .ant-select-dropdown').forEach((el) => el.remove())
})

function renderPage(): void {
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <ChangeDashboardPage />
      </QueryClientProvider>,
    )
  })
}

async function renderPageAsync(): Promise<void> {
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <ChangeDashboardPage />
      </QueryClientProvider>,
    )
  })
}

function findCardByTitle(text: string): HTMLElement | null {
  return Array.from(document.querySelectorAll('.ant-card')).find(
    (card) => card.textContent?.includes(text) ?? false,
  ) as HTMLElement | null
}

it('渲染五张指标卡：临期计划卡按选中窗口展示数量并默认 15 天', async () => {
  await renderPageAsync()
  for (const title of ['变更总数', '变更计划总数', '逾期计划', '临期计划', '已确认提醒']) {
    expect(findCardByTitle(title)).toBeTruthy()
  }
  expect(mocks.fetchChangeActionPlanDueStatus).toHaveBeenCalledWith(15)
  const soonCard = findCardByTitle('临期计划')
  expect(soonCard?.textContent).toContain('15 天内')
})

it('五张指标卡排布在同一 5 列网格容器内', async () => {
  await renderPageAsync()
  const grid = Array.from(container.querySelectorAll('div')).find(
    (el) =>
      (el as HTMLElement).style.display === 'grid' &&
      (el as HTMLElement).style.gridTemplateColumns.includes('repeat(5'),
  ) as HTMLElement | undefined
  expect(grid).toBeTruthy()
  expect(grid?.querySelectorAll(':scope > .ant-card').length).toBe(5)
})

it('点击逾期/临期卡片弹出对应明细，临期切换窗口后按新窗口重新拉取', async () => {
  await renderPageAsync()

  await act(async () => {
    findCardByTitle('逾期计划')?.click()
  })
  let modal = document.querySelector('.ant-modal')
  expect(modal?.textContent).toContain('逾期计划明细')
  expect(modal?.textContent).toContain('逾期项目一')
  expect(modal?.textContent).toContain('逾期 4 天')
  await act(async () => {
    ;(document.querySelector('.ant-modal .ant-modal-close') as HTMLElement)?.click()
  })

  await act(async () => {
    findCardByTitle('临期计划')?.click()
  })
  modal = document.querySelector('.ant-modal')
  expect(modal?.textContent).toContain('临期计划明细')
  expect(modal?.textContent).toContain('未来 15 天内到期')
  expect(modal?.textContent).toContain('临期项目一')
  expect(modal?.textContent).toContain('剩余 4 天')
})
