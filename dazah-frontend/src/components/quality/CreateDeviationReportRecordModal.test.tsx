/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchQualityPersonDirectory: vi.fn(),
  createDeviationReportRecord: vi.fn(),
}))
vi.mock('@/lib/api/client/quality', () => ({
  fetchQualityPersonDirectory: mocks.fetchQualityPersonDirectory,
}))
vi.mock('@/actions/quality-deviation', () => ({
  createDeviationReportRecord: mocks.createDeviationReportRecord,
}))
import { CreateDeviationReportRecordModal } from './CreateDeviationReportRecordModal'

let root: Root
let container: HTMLDivElement
let client: QueryClient

beforeEach(() => {
  mocks.fetchQualityPersonDirectory.mockReset()
  mocks.createDeviationReportRecord.mockReset().mockResolvedValue({ id: 'created' })
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

async function renderModal() {
  await act(async () => root.render(
    <App>
      <QueryClientProvider client={client}>
        <CreateDeviationReportRecordModal open onClose={() => undefined} />
      </QueryClientProvider>
    </App>,
  ))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)) })
}

it('renders reporter options with avatars for contacts that provide one', async () => {
  mocks.fetchQualityPersonDirectory.mockResolvedValue([
    { open_id: 'ou-avatar', name: '张头像', department: 'QA', job_title: null, enterprise_email: null, avatar_url: 'https://example.test/a.png' },
    { open_id: 'ou-plain', name: '李无图', department: 'QC', job_title: null, enterprise_email: null, avatar_url: null },
  ])
  await renderModal()

  const selector = document.querySelector('#reporter_open_id')!
  await act(async () => selector.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })

  const options = Array.from(document.querySelectorAll('.ant-select-item-option'))
  const avatarOption = options.find((item) => item.textContent?.includes('张头像'))
  const plainOption = options.find((item) => item.textContent?.includes('李无图'))
  expect(avatarOption).toBeDefined()
  expect(plainOption).toBeDefined()
  expect(avatarOption?.querySelector('img')).not.toBeNull()
  expect(plainOption?.querySelector('img')).toBeNull()
})
