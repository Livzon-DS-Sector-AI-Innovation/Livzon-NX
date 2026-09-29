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

async function openSelectAndPickOption(selector: string, optionText: string) {
  const selectorNode = document.querySelector(selector)!
  await act(async () => selectorNode.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })
  // 多选下拉点击选项后不收起，必须按文本定位目标选项
  const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find(
    (item) => item.textContent === optionText,
  )
  expect(option).toBeTruthy()
  await act(async () => option!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

function setNativeValue(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = element instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')!.set!
  setter.call(element, value)
  element.dispatchEvent(new Event('input', { bubbles: true }))
}

it('submits products, batch numbers and event type aligned with the feishu table', async () => {
  mocks.fetchQualityPersonDirectory.mockResolvedValue([
    { open_id: 'ou-1', name: '报告人', department: 'QC', job_title: null, enterprise_email: null, avatar_url: null },
  ])
  await renderModal()

  const description = document.querySelector<HTMLTextAreaElement>('#description')!
  await act(async () => setNativeValue(description, '偏差内容'))

  await openSelectAndPickOption('#products', '霉酚酸')

  const batchInput = document.querySelector<HTMLInputElement>('#batch_numbers')!
  await act(async () => setNativeValue(batchInput, 'LN-2602006'))

  await openSelectAndPickOption('#reporter_open_id', '报告人')

  const submit = Array.from(document.querySelectorAll('button')).find(
    (item) => item.textContent?.replace(/\s/g, '') === '提交',
  )!
  await act(async () => submit.click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) })

  expect(mocks.createDeviationReportRecord).toHaveBeenCalledWith({
    description: '偏差内容',
    event_type: '偏差',
    products: ['霉酚酸'],
    batch_numbers: 'LN-2602006',
    reporter_open_id: 'ou-1',
  })
})
