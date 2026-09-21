/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchPushRecords: vi.fn(),
  fetchReportRecords: vi.fn(),
  fetchAppSettings: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchDeviationInvestigationPushRecords: mocks.fetchPushRecords,
  fetchDeviationReportRecords: mocks.fetchReportRecords,
  fetchQualityFeishuAppSettings: mocks.fetchAppSettings,
  fetchQualityPersonDirectory: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/actions/quality-deviation', () => ({
  deleteDeviationInvestigationPushRecord: vi.fn(),
  updateDeviationInvestigationPushRecord: vi.fn(),
}))
vi.mock('@/actions/quality', () => ({ pullQualityRecordsFromFeishu: vi.fn() }))
vi.mock('next/link', () => ({
  default: ({ children }: { children?: React.ReactNode }) =>
    React.createElement('a', null, children),
}))
import { DeviationInvestigationPushPage } from './DeviationInvestigationPushPage'

let root: Root
let container: HTMLDivElement
let client: QueryClient

const pushRecord = {
  id: 'push-1',
  record_id: 'rec-1',
  deviation_id: null,
  deviation_code: 'PC-PUSH-1',
  push_round: '第1次推送',
  investigation_report_url: 'https://example.test/report',
  submitted_at: '2026-09-01T08:00:00Z',
  submitter: '王推送',
  submitters: null,
  department_head: null,
  department_heads: null,
  department_head_result: null,
  department_head_reviewed_at: null,
  qa_name: null,
  qas: null,
  qa_result: null,
  qa_reviewed_at: null,
  qa_head_name: null,
  qa_heads: null,
  qa_head_result: null,
  qa_head_reviewed_at: null,
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-01T08:00:00Z',
}

beforeEach(() => {
  mocks.fetchPushRecords.mockReset().mockResolvedValue({ items: [pushRecord], total: 1 })
  mocks.fetchReportRecords.mockReset().mockResolvedValue({
    items: [{ id: 'r1', deviation_code: 'PC-PUSH-1', report_status: 'investigating' }],
    total: 1,
  })
  mocks.fetchAppSettings.mockReset().mockResolvedValue({
    configured: false,
    deviation_investigation_push_form_url: '',
  })
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

async function renderPage() {
  await act(async () => root.render(
    <App>
      <QueryClientProvider client={client}>
        <DeviationInvestigationPushPage
          submitterContacts={[
            { open_id: 'ou-push', name: '王推送', department: 'QC', job_title: null, enterprise_email: null, avatar_url: 'https://example.test/p.png' },
          ]}
        />
      </QueryClientProvider>
    </App>,
  ))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
}

it('renders submitter options with avatars when editing an existing push record', async () => {
  await renderPage()

  expect(container.textContent).toContain('PC-PUSH-1')
  const edit = Array.from(container.querySelectorAll('button')).find(
    (button) => button.textContent === '修改',
  )
  expect(edit).toBeDefined()
  await act(async () => edit?.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })

  const submitterSelect = document.querySelector('#submitter_open_id')!
  expect(submitterSelect).not.toBeNull()
  await act(async () => submitterSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })

  const submitterOption = Array.from(document.querySelectorAll('.ant-select-item-option')).find(
    (item) => item.textContent?.includes('王推送'),
  )
  expect(submitterOption).toBeDefined()
  expect(submitterOption?.querySelector('img')).not.toBeNull()
})
