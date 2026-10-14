/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import dayjs, { type Dayjs } from 'dayjs'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { User } from '@/types/user'
import type { Feedback } from '@/lib/api/feedback'

vi.mock('next/navigation', () => ({ usePathname: () => '/quality/deviations/ledger' }))
vi.mock('@/actions/feedback', () => ({ submitFeedback: vi.fn(), processFeedback: vi.fn() }))
vi.mock('@/lib/api/feedback', async (original) => ({
  ...await original<typeof import('@/lib/api/feedback')>(), fetchFeedback: vi.fn(),
}))
// Keep the actual Form, Upload, drawers, queries and business handlers. Calendar
// popup geometry is already exercised by Playwright; provide a deterministic input.
vi.mock('antd', async (original) => ({
  ...await original<typeof import('antd')>(),
  DatePicker: ({ value, onChange, id, disabled }: {
    value?: Dayjs; onChange?: (value: Dayjs) => void; id?: string; disabled?: boolean
  }) => <input id={id} aria-label="发生时间" disabled={disabled}
    value={value?.format('YYYY-MM-DD HH:mm') || ''}
    onChange={(event) => onChange?.(dayjs(event.target.value))} />,
}))

import { submitFeedback, processFeedback } from '@/actions/feedback'
import { fetchFeedback } from '@/lib/api/feedback'
import { FeedbackEntry } from './FeedbackEntry'

const user: User = { id: 'feedback-user', name: '测试提交者', role: 'user', status: 'active', auth_source: 'local', grant_version: 1, page_permissions: [], page_permission_rollouts: {} }
const feedback: Feedback = {
  id: '11111111-1111-4111-8111-111111111111', reporter_name: '测试提交者',
  description: '保存偏差记录时出现异常，预期保存成功但页面显示错误。',
  occurred_at: '2026-10-01T01:30:00Z', page_path: '/quality/deviations/ledger',
  status: 'pending', reply: '正在核查', version: 3,
  created_at: '2026-10-01T02:00:00Z', updated_at: '2026-10-01T02:00:00Z',
  screenshots: [{ id: '22222222-2222-4222-8222-222222222222', content_type: 'image/png' }],
}
let root: Root
let client: QueryClient

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(window, 'matchMedia').mockImplementation((media) => ({
    matches: false, media, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: () => true,
  }))
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  vi.mocked(fetchFeedback).mockResolvedValue({ items: [feedback], total: 1, pending_count: 1, page: 1, page_size: 10 })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  document.body.replaceChildren()
  vi.restoreAllMocks()
})

async function render(actor = user, ready = true) {
  await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}>
    <App><QueryClientProvider client={client}><FeedbackEntry user={actor} ready={ready} /></QueryClientProvider></App>
  </ConfigProvider>))
}

async function waitFor(assertion: () => void) {
  await vi.waitFor(async () => {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
    assertion()
  }, { timeout: 3000, interval: 20 })
}

async function click(text: string, selector = 'button') {
  const button = [...document.querySelectorAll<HTMLElement>(selector)]
    .find((element) => (selector === 'li button'
      ? element.textContent?.includes(text)
      : element.textContent?.replace(/\s/g, '') === text.replace(/\s/g, '')) || element.getAttribute('aria-label') === text)
  expect(button, text).toBeDefined()
  await act(async () => button!.click())
}

async function fill(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  await act(async () => {
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function upload(file: File) {
  const input = document.querySelector<HTMLInputElement>('input[type=file]')!
  expect(input).not.toBeNull()
  await act(async () => {
    Object.defineProperty(input, 'files', { configurable: true, value: [file] })
    input.dispatchEvent(new Event('change', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

async function chooseResolution() {
  await act(async () => document.querySelector('.ant-modal [role=combobox]')!
    .dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const option = [...document.querySelectorAll<HTMLElement>('.ant-select-item-option')]
    .find((element) => element.textContent === '已解决')
  expect(option).toBeDefined()
  await act(async () => option!.click())
}

it.each([user, { ...user, role: 'admin' as const, roles: ['ordinary_admin'] }])('keeps personal feedback private for $role and retries failed reads', async (actor) => {
  await render(actor, false)
  expect(document.querySelector<HTMLButtonElement>('[aria-label="问题反馈"]')!.disabled).toBe(true)
  expect(fetchFeedback).not.toHaveBeenCalled()
  await render(actor)
  await click('问题反馈')
  expect(document.body.textContent).not.toContain('收件箱')
  expect(fetchFeedback).not.toHaveBeenCalled()
  vi.mocked(fetchFeedback).mockRejectedValueOnce(new Error('反馈列表暂不可用'))
  await click('我的反馈', '[role=tab]')
  await waitFor(() => expect(document.body.textContent).toContain('反馈列表暂不可用'))
  await click('重试')
  await waitFor(() => expect(document.body.textContent).toContain(feedback.description))
  expect(vi.mocked(fetchFeedback).mock.calls.every(([admin]) => admin === false)).toBe(true)
  await click(feedback.description, 'li button')
  await waitFor(() => expect(document.body.textContent).toContain('管理员回复：正在核查'))
  expect(document.querySelector<HTMLImageElement>('[alt="问题截图 1"]')!.src).toContain(`/identity/me/feedback/${feedback.id}/screenshots/`)
  expect(document.body.textContent).not.toContain('保存处理结果')
  await act(async () => document.querySelector<HTMLButtonElement>('.ant-modal-close')!.click())
  await click('刷新')
  expect(fetchFeedback).toHaveBeenCalledTimes(3)
})

it('validates the form and screenshots, preserves failures and reuses the submission id until success', async () => {
  await render()
  await click('问题反馈')
  await click('提交反馈')
  await waitFor(() => expect(document.body.textContent).toContain('请选择问题发生时间'))
  const description = document.querySelector<HTMLTextAreaElement>('textarea')!
  const date = document.querySelector<HTMLInputElement>('[aria-label="发生时间"]')!
  await fill(description, `  ${feedback.description}  `)
  await fill(date, '2099-10-01 09:30')
  await click('提交反馈')
  await waitFor(() => expect(document.body.textContent).toContain('发生时间不能晚于当前时间'))
  await fill(date, '2026-10-01 09:30')
  await click('提交反馈')
  await waitFor(() => expect(document.body.textContent).toContain('请上传至少一张问题截图'))
  expect(submitFeedback).not.toHaveBeenCalled()
  await upload(new File(['invalid'], 'invalid.txt', { type: 'text/plain' }))
  await waitFor(() => expect(document.body.textContent).toContain('截图格式不支持或超过 2MB'))
  await upload(new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' }))
  expect(document.querySelectorAll('.ant-upload-list-item')).toHaveLength(0)
  await upload(new File(['image'], 'problem.png', { type: 'image/png' }))
  await waitFor(() => expect(document.body.textContent).toContain('problem.png'))
  vi.mocked(submitFeedback).mockResolvedValueOnce({ success: false, error: '反馈服务暂不可用' })
  await click('提交反馈')
  await waitFor(() => expect(document.body.textContent).toContain('反馈服务暂不可用'))
  expect(description.value.trim()).toBe(feedback.description)
  const first = vi.mocked(submitFeedback).mock.calls[0][0]
  expect(first.get('description')).toBe(feedback.description)
  expect(first.get('page_path')).toBe('/quality/deviations/ledger')
  expect(new Date(String(first.get('occurred_at'))).getTime()).toBe(dayjs('2026-10-01 09:30').valueOf())
  expect(first.getAll('screenshots')).toHaveLength(1)
  vi.mocked(submitFeedback).mockRejectedValueOnce(new Error('offline'))
  await click('提交反馈')
  await waitFor(() => expect(document.body.textContent).toContain('提交未完成，填写内容已保留'))
  expect(vi.mocked(submitFeedback).mock.calls[1][0].get('feedback_id')).toBe(first.get('feedback_id'))
  vi.mocked(submitFeedback).mockResolvedValueOnce({ success: true, data: feedback })
  await click('提交反馈')
  await waitFor(() => expect(document.querySelector('[role=tab][aria-selected=true]')!.textContent).toBe('我的反馈'))
  expect(vi.mocked(submitFeedback).mock.calls[2][0].get('feedback_id')).toBe(first.get('feedback_id'))
  expect(document.querySelector<HTMLTextAreaElement>('textarea')!.value).toBe('')
  expect(fetchFeedback).toHaveBeenCalledWith(false, 1, undefined, expect.any(AbortSignal))
})

it('requires a resolution reply and keeps admin edits on conflicts and transport failures', async () => {
  await render({ ...user, role: 'admin', roles: ['super_admin'] })
  await waitFor(() => expect(fetchFeedback).toHaveBeenCalledWith(true, 1, 'pending', expect.any(AbortSignal)))
  await click('问题反馈')
  await waitFor(() => expect(document.body.textContent).toContain(feedback.description))
  expect(document.body.textContent).not.toContain('提交反馈')
  await click(feedback.description, 'li button')
  await waitFor(() => expect(document.body.textContent).toContain('保存处理结果'))
  expect(document.querySelector<HTMLImageElement>('[alt="问题截图 1"]')!.src).toContain('/identity/admin/feedback/')
  const reply = document.querySelector<HTMLTextAreaElement>('.ant-modal textarea')!
  await fill(reply, '')
  await chooseResolution()
  await click('保存处理结果')
  await waitFor(() => expect(document.body.textContent).toContain('处理完成时请填写处理结果'))
  expect(processFeedback).not.toHaveBeenCalled()
  await fill(reply, '已修复，请重新尝试。')
  vi.mocked(processFeedback).mockResolvedValueOnce({ success: false, error: '反馈已被其他管理员更新' })
  await click('保存处理结果')
  await waitFor(() => expect(document.body.textContent).toContain('反馈已被其他管理员更新'))
  expect(reply.value).toBe('已修复，请重新尝试。')
  expect(processFeedback).toHaveBeenCalledWith(feedback.id, { status: 'resolved', reply: '已修复，请重新尝试。', version: 3 })
  vi.mocked(processFeedback).mockRejectedValueOnce(new Error('offline'))
  await click('保存处理结果')
  await waitFor(() => expect(document.body.textContent).toContain('处理结果未保存，请稍后重试'))
  vi.mocked(processFeedback).mockResolvedValueOnce({ success: true, data: { ...feedback, status: 'resolved', reply: reply.value, version: 4 } })
  await click('保存处理结果')
  await waitFor(() => expect(document.body.textContent).toContain('提交者：测试提交者 · 已解决'))
  expect(vi.mocked(fetchFeedback).mock.calls.every(([admin]) => admin === true)).toBe(true)
  expect(processFeedback).toHaveBeenCalledTimes(3)
})
