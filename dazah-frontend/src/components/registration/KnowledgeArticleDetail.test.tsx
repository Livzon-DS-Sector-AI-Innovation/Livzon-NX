/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { KnowledgeArticleDetail as Article } from '@/types/registration'
import KnowledgeArticleDetail from './KnowledgeArticleDetail'

const actions = vi.hoisted(() => ({
  createKnowledgeComment: vi.fn(), deleteKnowledgeComment: vi.fn(), generateAttachmentSummary: vi.fn(),
  uploadKnowledgeAttachment: vi.fn(), deleteKnowledgeAttachment: vi.fn(),
}))
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }))
vi.mock('@/actions/registration', () => actions)
vi.mock('next/navigation', () => ({ useRouter: () => router }))

const date = '2026-08-01'
const article: Article = {
  id: 'article-1', title: '审核知识条目', content: '示例正文', category_id: 'category-1', category_name: '归档',
  author: null, country: null, product: null, tags: null, source_url: null, is_published: true,
  published_at: date, created_at: date, updated_at: date, view_count: 0,
  attachments: [{
    id: 'file-1', article_id: 'article-1', content_type: 'application/pdf', file_name: '示例.pdf',
    file_size: 99, created_at: date, ai_summary: null,
  }],
  comments: [{
    id: 'comment-1', article_id: 'article-1', author: '审核员', content: '请保留记录',
    created_at: date, updated_at: date,
  }],
}
const technicalError = 'TypeError: internal registration adapter'
const safeError = '操作未完成，请稍后重试'
let root: Root
let host: HTMLDivElement

beforeEach(async () => {
  vi.resetAllMocks()
  for (const action of Object.values(actions)) action.mockRejectedValue(new Error(technicalError))
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  await act(async () => root.render(
    <ConfigProvider theme={{ token: { motion: false } }}>
      <App><KnowledgeArticleDetail article={article} /></App>
    </ConfigProvider>,
  ))
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

async function click(element?: HTMLButtonElement | null) {
  expect(element?.disabled).toBe(false)
  await act(async () => element?.click())
}

function button(label: string) {
  return Array.from(host.querySelectorAll('button'))
    .find(el => el.textContent?.replace(/\s/g, '') === label)
}

async function confirmDelete(index: number) {
  const triggers = Array.from(host.querySelectorAll('[aria-label="delete"]'))
  await click(triggers[index]?.closest('button'))
  await click(document.querySelector<HTMLButtonElement>('.ant-popconfirm:not(.ant-popconfirm-hidden) button.ant-btn-primary'))
}

it('preserves a comment and its draft after submit or confirmed deletion fails', async () => {
  const draft = host.querySelector<HTMLTextAreaElement>('textarea')
  expect(draft).not.toBeNull()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(draft, '补充说明')
    draft?.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await click(button('提交评论'))
  expect(actions.createKnowledgeComment).toHaveBeenCalledWith(article.id, { content: '补充说明' })
  expect(draft?.value).toBe('补充说明')
  expect(document.body.textContent).toContain(safeError)
  await confirmDelete(1)
  expect(actions.deleteKnowledgeComment).toHaveBeenCalledWith('comment-1', article.id)
  expect(host.textContent).toContain('请保留记录')
  expect(document.body.textContent).not.toContain(technicalError)
  expect(router.refresh).not.toHaveBeenCalled()
})

it('reports upload, summary and deletion failures while preserving the attachment list', async () => {
  const picker = host.querySelector<HTMLInputElement>('input[type=file]')
  expect(picker).not.toBeNull()
  Object.defineProperty(picker, 'files', { value: [new File(['sample'], '补充.pdf', { type: 'application/pdf' })] })
  await act(async () => picker?.dispatchEvent(new Event('change', { bubbles: true })))
  const [articleId, body] = actions.uploadKnowledgeAttachment.mock.calls[0] as [string, FormData]
  expect(articleId).toBe(article.id)
  expect(body.get('file')).toHaveProperty('name', '补充.pdf')
  expect(document.body.textContent).toContain(safeError)

  await click(button('AI摘要'))
  expect(actions.generateAttachmentSummary).toHaveBeenCalledWith('file-1', article.id)
  await confirmDelete(0)
  expect(actions.deleteKnowledgeAttachment).toHaveBeenCalledWith('file-1', article.id)
  expect(host.textContent).toContain('示例.pdf')
  expect(document.body.textContent).not.toContain(technicalError)
  expect(router.refresh).not.toHaveBeenCalled()
})
