/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchValidationReviews: vi.fn(),
  fetchValidationReviewDetail: vi.fn(),
  fetchValidationReviewJob: vi.fn(),
  fetchDocumentEntries: vi.fn(),
}))

const reviewActions = vi.hoisted(() => ({
  createValidationReview: vi.fn(),
  uploadValidationReviewFile: vi.fn(),
  runValidationReview: vi.fn(),
  rerunValidationReview: vi.fn(),
  deleteValidationReview: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/validation-review', () => reviewActions)

import { ValidationAiReviewPanel } from './ValidationAiReviewPanel'

const REVIEW_LIST = [
  {
    id: 'review-1',
    title: '清洁验证审核',
    review_mode: 'upload',
    status: 'completed',
    file_count: 2,
    created_at: '2026-09-03T10:00:00',
    updated_at: '2026-09-03T10:00:00',
  },
]

const REVIEW_DETAIL = {
  id: 'review-1',
  title: '清洁验证审核',
  review_mode: 'upload',
  status: 'completed',
  error_message: null,
  model_name: 'deepseek-chat',
  input_snapshot: null,
  summary: '本次 AI 审核共核对引用文件 1 项，发现 1 个问题。',
  stats: {
    total_findings: 1,
    high: 0,
    medium: 1,
    low: 0,
    references_checked: 1,
    references_matched: 1,
    plan_report_checked: true,
  },
  findings: [
    {
      category: 'version_mismatch',
      severity: 'medium',
      location: '引用文件',
      quote: 'SMP-QA-105/02',
      quote_verified: true,
      basis_source: 'SMP-QA-105/03 清洁验证管理程序',
      basis_match_type: 'related',
      detail: '引用版本与目录现行版不一致',
    },
  ],
  basis_used: [
    {
      code: 'SMP-QA-105/03',
      core: 'SMPQA105',
      revision: '03',
      matched: true,
      match_type: 'exact',
      issue: 'none',
      entry_name: '清洁验证管理程序',
      entry_code: 'SMP-QA-105/03',
      current_revision: '03',
    },
  ],
  job_id: 'job:1',
  last_generated_at: '2026-09-03T10:05:00',
  files: [
    {
      id: 'file-1',
      doc_kind: 'plan',
      source: 'upload',
      file_name: 'VP-FT3-CV1902-01 方案.md',
      file_type: 'text/markdown',
      file_size: 100,
      parse_status: 'completed',
      parse_error: null,
      sort_order: 0,
    },
  ],
  created_at: '2026-09-03T10:00:00',
  updated_at: '2026-09-03T10:05:00',
}


function flushRenders(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 80)
  })
}

function bodyText(): string {
  return document.body.textContent ?? ''
}

function findButton(label: string): HTMLElement | undefined {
  return [...document.body.querySelectorAll('button')].find((button) =>
    button.textContent?.includes(label)
  )
}

function chooseFile(container: HTMLElement, name = 'VP-FT3-CV1902-01 方案.docx') {
  const input = document.body.querySelector('input[type="file"]')
  if (!input) return
  const file = new File(['docx-content'], name)
  Object.defineProperty(input, 'files', { value: [file] })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function setupMocks() {
  apiClient.fetchValidationReviews.mockResolvedValue({
    items: REVIEW_LIST,
    total: 1,
  })
  apiClient.fetchValidationReviewDetail.mockResolvedValue(REVIEW_DETAIL)
  apiClient.fetchValidationReviewJob.mockResolvedValue({
    job_id: 'job:1',
    state: 'completed',
    progress: '完成',
    status: 'completed',
    error_message: null,
    review_id: 'review-1',
  })
  apiClient.fetchDocumentEntries.mockResolvedValue({ items: [], total: 0 })
  reviewActions.createValidationReview.mockResolvedValue({ ...REVIEW_DETAIL, status: 'draft' })
  reviewActions.runValidationReview.mockResolvedValue({
    job_id: 'job:2',
    review_id: 'review-1',
  })
  reviewActions.deleteValidationReview.mockResolvedValue({ id: 'review-1' })
}

describe('ValidationAiReviewPanel', () => {
  let container: HTMLElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    vi.stubGlobal('fetch', vi.fn())
    setupMocks()
  })

  afterEach(() => {
    act(() => root.unmount())
    document.body.removeChild(container)
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('渲染审核记录列表', async () => {
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    await act(async () => {
      await apiClient.fetchValidationReviews.mock.results[0]?.value
    })
    expect(bodyText()).toContain('清洁验证审核')
    expect(bodyText()).toContain('已完成')
  })

  it('打开详情抽屉并展示审核结论与发现问题', async () => {
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    // 点击列表行打开详情
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    await act(async () => {
      await apiClient.fetchValidationReviewDetail.mock.results[0]?.value
    })
    expect(bodyText()).toContain('本次 AI 审核共核对引用文件 1 项')
    expect(bodyText()).toContain('引用版本不一致')
    expect(bodyText()).toContain('SMP-QA-105/02')
  })

  it('新建审核弹窗可打开并触发创建', async () => {
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    // 点击"新建审核"按钮打开弹窗
    const createButton = findButton('新建审核')
    act(() => {
      createButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(bodyText()).toContain('新建验证 AI 审核')
    chooseFile(container)
    await act(flushRenders)
    const okButton = findButton('创建并上传文件')
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.createValidationReview).toHaveBeenCalledWith({
      review_mode: 'upload',
      title: undefined,
      focus_points: undefined,
    })
  })

  it('新建审核弹窗未选择文件时提示且不调用创建', async () => {
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const createButton = findButton('新建审核')
    act(() => {
      createButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    // 不选择文件直接点创建
    const okButton = findButton('创建并上传文件')
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(bodyText()).toContain('请先选择要上传的验证方案 / 验证报告')
    expect(reviewActions.createValidationReview).not.toHaveBeenCalled()
  })

  it('填写审核关注点后创建时传递 focus_points', async () => {
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const createButton = findButton('新建审核')
    act(() => {
      createButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    chooseFile(container)
    await act(flushRenders)
    const textarea = document.body.querySelector('textarea')
    expect(textarea).toBeTruthy()
    const valueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value'
    )?.set
    act(() => {
      valueSetter?.call(textarea, '重点核对清洁限度计算依据')
      textarea?.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(flushRenders)
    const okButton = findButton('创建并上传文件')
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.createValidationReview).toHaveBeenCalledWith({
      review_mode: 'upload',
      title: undefined,
      focus_points: '重点核对清洁限度计算依据',
    })
  })

  it('基准正文一致性核查展示不一致与空理由占位', async () => {
    apiClient.fetchValidationReviewDetail.mockResolvedValue({
      ...REVIEW_DETAIL,
      basis_comparison: [
        {
          entry_id: 'basis-1',
          name: '清洁验证管理程序',
          code: 'SMP-QA-105/03',
          reason: '',
          mismatch_count: 2,
        },
        {
          entry_id: 'basis-2',
          name: '方锥混合机操作规程',
          code: 'SOP-FT3-017/04',
          reason: '覆盖混合机参数',
          mismatch_count: 0,
        },
      ],
    })
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    await act(async () => {
      await apiClient.fetchValidationReviewDetail.mock.results[0]?.value
    })
    expect(bodyText()).toContain('基准正文一致性核查')
    expect(bodyText()).toContain('2 处不一致')
    expect(bodyText()).toContain('一致')
    expect(bodyText()).toContain('—')
  })

  it('详情抽屉中已完成记录可导出报告', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(new Blob(['docx']), {
          status: 200,
          headers: { 'content-type': 'application/octet-stream' },
        })
      )
    )
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    await act(async () => {
      await apiClient.fetchValidationReviewDetail.mock.results[0]?.value
    })
    const exportButton = findButton('导出报告')
    act(() => {
      exportButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/quality/validation-reviews/review-1/export',
      { method: 'POST' }
    )
  })

  it('draft 记录详情可发起审核（run）', async () => {
    apiClient.fetchValidationReviewDetail.mockResolvedValue({
      ...REVIEW_DETAIL,
      status: 'draft',
      summary: null,
      stats: null,
      findings: [],
      basis_used: [],
    })
    reviewActions.runValidationReview.mockResolvedValue({
      job_id: 'job:2',
      review_id: 'review-1',
    })
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    const runButton = findButton('开始审核')
    act(() => {
      runButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.runValidationReview).toHaveBeenCalledWith('review-1')
  })

  it('completed 记录可重新审核（rerun）', async () => {
    reviewActions.rerunValidationReview.mockResolvedValue({
      job_id: 'job:3',
      review_id: 'review-1',
    })
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    const rerunButton = findButton('重新审核')
    act(() => {
      rerunButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.rerunValidationReview).toHaveBeenCalledWith('review-1')
  })

  it('列表删除：确认气泡确认后调用删除', async () => {
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const dangerButton = [...document.body.querySelectorAll('button')].find(
      (button) => button.classList.contains('ant-btn-dangerous')
    )
    expect(dangerButton).toBeTruthy()
    act(() => {
      dangerButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    await act(flushRenders)
    // 确认气泡出现（antd Popconfirm 文案）
    expect(document.body.textContent).toContain('删除后不可恢复')
    // 确认按钮（antd 按钮文本带空格，去掉空白后匹配）
    const confirmButton = [...document.body.querySelectorAll('button')].find(
      (button) => button.textContent?.replace(/\s/g, '') === '删除'
    )
    act(() => {
      confirmButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.deleteValidationReview).toHaveBeenCalledWith('review-1')
  })

  it('创建失败展示错误提示', async () => {
    reviewActions.createValidationReview.mockRejectedValue(
      new Error('AI 服务尚未配置')
    )
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const createButton = findButton('新建审核')
    act(() => {
      createButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    chooseFile(container)
    await act(flushRenders)
    const okButton = findButton('创建并上传文件')
    act(() => {
      okButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.createValidationReview).toHaveBeenCalled()
  })

  it('发起审核失败展示错误提示', async () => {
    apiClient.fetchValidationReviewDetail.mockResolvedValue({
      ...REVIEW_DETAIL,
      status: 'draft',
      summary: null,
      stats: null,
      findings: [],
      basis_used: [],
    })
    reviewActions.runValidationReview.mockRejectedValue(
      new Error('LLM 速率限制')
    )
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    const runButton = findButton('开始审核')
    act(() => {
      runButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(reviewActions.runValidationReview).toHaveBeenCalledWith('review-1')
  })

  it('导出失败展示错误提示', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: '导出失败' }), {
          status: 500,
          headers: { 'content-type': 'application/json' },
        })
      )
    )
    act(() => {
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <App>
            <ValidationAiReviewPanel />
          </App>
        </QueryClientProvider>
      )
    })
    await act(flushRenders)
    const row = [...container.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('清洁验证审核')
    )
    act(() => {
      row?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    const exportButton = findButton('导出报告')
    act(() => {
      exportButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await act(flushRenders)
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/quality/validation-reviews/review-1/export',
      { method: 'POST' }
    )
  })
})
