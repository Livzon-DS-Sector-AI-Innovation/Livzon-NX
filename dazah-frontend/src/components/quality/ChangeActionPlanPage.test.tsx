/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchChangeActionPlans: vi.fn(),
  syncAll: vi.fn(),
}))
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock('@/actions/quality-change', () => ({
  createChangeActionPlan: vi.fn(),
  deleteChangeActionPlan: vi.fn(),
  syncChangeActionPlanToFeishu: vi.fn(),
  syncChangeActionPlansFromFeishu: mocks.syncAll,
  updateChangeActionPlan: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchChangeActionPlans: mocks.fetchChangeActionPlans,
}))
vi.mock('./ChangeActionPlanTable', () => ({
  ChangeActionPlanTable: ({ onSyncAll }: { onSyncAll: () => void }) =>
    React.createElement(
      'button',
      { 'data-testid': 'sync-all', onClick: onSyncAll },
      '同步飞书',
    ),
}))
vi.mock('./ChangeActionPlanEditModal', () => ({
  ChangeActionPlanEditModal: () => null,
}))
import { ChangeActionPlanPage } from './ChangeActionPlanPage'

let root: Root
let container: HTMLDivElement
let client: QueryClient

beforeEach(() => {
  mocks.fetchChangeActionPlans
    .mockReset()
    .mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 })
  mocks.syncAll.mockReset()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  document
    .querySelectorAll('.ant-message, .ant-modal-root')
    .forEach((el) => el.remove())
})

function renderPage(): void {
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <AntdApp>
          <ChangeActionPlanPage />
        </AntdApp>
      </QueryClientProvider>,
    )
  })
}

async function clickSyncAll(): Promise<void> {
  const btn = document.querySelector('[data-testid="sync-all"]') as HTMLElement | null
  if (!btn) throw new Error('sync-all button not rendered')
  await act(async () => {
    btn.click()
  })
  await act(async () => {})
}

function bodyText(): string {
  // happy-dom 解析 antd SVG 会截断 DOM，先剥离 SVG 再取文本
  document.querySelectorAll('svg').forEach((el) => el.remove())
  return document.body.textContent || ''
}

it('同步存在失败记录时用警告提示并展示失败数', async () => {
  mocks.syncAll.mockResolvedValue({ synced: 76, failed: 18 })
  renderPage()
  await act(async () => {})
  await clickSyncAll()
  const text = bodyText()
  expect(text).toContain('成功 76 条，失败 18 条')
  expect(text).toContain('失败记录详见后端日志与飞书数据')
  expect(text).not.toContain('已按最新结果回写系统')
})

it('同步全部成功时用成功提示并保留回写说明', async () => {
  mocks.syncAll.mockResolvedValue({ synced: 94, failed: 0 })
  renderPage()
  await act(async () => {})
  await clickSyncAll()
  const text = bodyText()
  expect(text).toContain('成功 94 条')
  expect(text).toContain('已按最新结果回写系统')
  expect(text).not.toContain('失败')
})
