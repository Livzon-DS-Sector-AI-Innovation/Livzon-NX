/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchHistoricalDeviation: vi.fn(),
  fetchHistoricalDeviations: vi.fn(),
}))

const workbenchActions = vi.hoisted(() => ({
  aiExtractHistoricalDeviation: vi.fn(),
  batchImportHistoricalDeviations: vi.fn(),
  createHistoricalDeviation: vi.fn(),
  deleteHistoricalDeviation: vi.fn(),
  deleteHistoricalDeviationAttachment: vi.fn(),
  updateHistoricalDeviation: vi.fn(),
  uploadHistoricalDeviationAttachment: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-deviation-workbench', () => workbenchActions)

import { DeviationHistoryPage } from './DeviationHistoryPage'

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function makeFile(name: string): File {
  return new File(['content'], name, { type: 'application/octet-stream' })
}

/** 触发 antd Upload 的隐藏 file input，走 rc-upload 的 beforeUpload 派发链 */
function triggerFileUpload(files: File[]) {
  const input = document.body.querySelector('input[type="file"]') as HTMLInputElement | null
  expect(input).toBeTruthy()
  if (!input) return
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

/** 抽屉里的上传入口（页面上还有批量导入的 input，需要限定在抽屉内） */
function triggerDrawerUpload(files: File[]) {
  const input = document.body.querySelector(
    '.ant-drawer input[type="file"]'
  ) as HTMLInputElement | null
  expect(input).toBeTruthy()
  if (!input) return
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function clickButton(label: string) {
  const normalize = (value: string) => value.replace(/\s+/g, '')
  const button = Array.from(document.body.querySelectorAll('button')).find(
    (node) => normalize(node.textContent || '') === normalize(label)
  )
  expect(button).toBeTruthy()
  button?.click()
}

function makeItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 'rec1',
    code: 'PC-2501001',
    deviation_event: null,
    deviation_content: null,
    direct_cause: null,
    root_cause: null,
    investigation_conclusion: null,
    attachment_count: 0,
    created_at: '2026-09-23T00:00:00Z',
    updated_at: '2026-09-23T00:00:00Z',
    ...overrides,
  }
}

function makeDetail(overrides: Record<string, unknown> = {}) {
  return { ...makeItem(), attachments: [], ai_extract_payload: null, remark: null, ...overrides }
}

describe('DeviationHistoryPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    apiClient.fetchHistoricalDeviations.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    })
    apiClient.fetchHistoricalDeviation.mockResolvedValue(null)
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body
      .querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message, .ant-drawer')
      .forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderPage() {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <DeviationHistoryPage />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
  }

  it('renders the empty table and batch import actions', async () => {
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('历史偏差')
    expect(text).toContain('批量导入附件')
    expect(apiClient.fetchHistoricalDeviations).toHaveBeenCalledWith({
      keyword: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('imports a batch of attachments successfully', async () => {
    workbenchActions.batchImportHistoricalDeviations.mockResolvedValue({
      total: 2,
      succeeded: 2,
      failed: 0,
      results: [
        { file_name: 'a.docx', status: 'succeeded' },
        { file_name: 'b.docx', status: 'succeeded' },
      ],
    })
    await renderPage()
    await act(async () => {
      triggerFileUpload([makeFile('a.docx'), makeFile('b.docx')])
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(workbenchActions.batchImportHistoricalDeviations).toHaveBeenCalled()
    const formData = workbenchActions.batchImportHistoricalDeviations.mock.calls[0][0]
    expect(formData).toBeInstanceOf(FormData)
    expect(document.body.textContent).toContain('批量导入完成：成功 2 个')
  })

  it('warns with file names when part of the batch fails', async () => {
    workbenchActions.batchImportHistoricalDeviations.mockResolvedValue({
      total: 3,
      succeeded: 1,
      failed: 2,
      results: [
        { file_name: 'ok.docx', status: 'succeeded' },
        { file_name: 'bad1.docx', status: 'failed' },
        { file_name: 'bad2.docx', status: 'failed' },
      ],
    })
    await renderPage()
    await act(async () => {
      triggerFileUpload([makeFile('ok.docx'), makeFile('bad1.docx'), makeFile('bad2.docx')])
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(document.body.textContent).toContain('共 3 个，成功 1，失败 2')
    expect(document.body.textContent).toContain('bad1.docx')
    expect(document.body.textContent).toContain('bad2.docx')
  })

  it('limits a single batch to 20 attachments', async () => {
    await renderPage()
    const files = Array.from({ length: 21 }, (_, i) => makeFile(`f${i}.docx`))
    await act(async () => {
      triggerFileUpload(files)
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(document.body.textContent).toContain('单次最多导入 20 个附件，请分批操作')
    expect(workbenchActions.batchImportHistoricalDeviations).not.toHaveBeenCalled()
  })

  it('surfaces import failures via toast', async () => {
    workbenchActions.batchImportHistoricalDeviations.mockRejectedValue(
      new Error('导入服务不可用'),
    )
    await renderPage()
    await act(async () => {
      triggerFileUpload([makeFile('a.docx')])
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(document.body.textContent).toContain('导入服务不可用')
  })

  it('reveals why AI extraction failed on a successful batch import', async () => {
    workbenchActions.batchImportHistoricalDeviations.mockResolvedValue({
      total: 2,
      succeeded: 2,
      failed: 0,
      results: [
        {
          file_name: 'a.docx',
          status: 'succeeded',
          message: 'AI 提取失败：AI 输出格式错误，请重试',
        },
        { file_name: 'b.docx', status: 'succeeded', message: '' },
      ],
    })
    await renderPage()
    await act(async () => {
      triggerFileUpload([makeFile('a.docx'), makeFile('b.docx')])
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(document.body.textContent).toContain('其中 1 个 AI 提取失败')
    expect(document.body.textContent).toContain('AI 输出格式错误')
  })

  it('auto-extracts after uploading an attachment when fields are empty', async () => {
    apiClient.fetchHistoricalDeviations.mockResolvedValue({
      items: [makeItem()],
      total: 1,
      page: 1,
      page_size: 20,
    })
    apiClient.fetchHistoricalDeviation.mockResolvedValue(makeDetail())
    workbenchActions.uploadHistoricalDeviationAttachment.mockResolvedValue({
      id: 'att1',
      file_name: 'a.docx',
    })
    workbenchActions.aiExtractHistoricalDeviation.mockResolvedValue(
      makeDetail({
        deviation_event: '事件',
        deviation_content: '内容',
        direct_cause: '直接',
        root_cause: '根本',
      }),
    )
    await renderPage()
    await act(async () => {
      clickButton('编辑')
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    await act(async () => {
      triggerDrawerUpload([makeFile('a.docx')])
      await new Promise((resolve) => setTimeout(resolve, 120))
    })
    expect(workbenchActions.aiExtractHistoricalDeviation).toHaveBeenCalledWith('rec1')
    expect(document.body.textContent).toContain('AI 已从附件提取并保存')
  })

  it('skips auto-extract when the record already has content', async () => {
    apiClient.fetchHistoricalDeviations.mockResolvedValue({
      items: [makeItem({ deviation_event: '已填写', deviation_content: '已填写' })],
      total: 1,
      page: 1,
      page_size: 20,
    })
    apiClient.fetchHistoricalDeviation.mockResolvedValue(
      makeDetail({ deviation_event: '已填写', deviation_content: '已填写' }),
    )
    workbenchActions.uploadHistoricalDeviationAttachment.mockResolvedValue({
      id: 'att1',
      file_name: 'a.docx',
    })
    await renderPage()
    await act(async () => {
      clickButton('编辑')
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    await act(async () => {
      triggerDrawerUpload([makeFile('a.docx')])
      await new Promise((resolve) => setTimeout(resolve, 120))
    })
    expect(workbenchActions.aiExtractHistoricalDeviation).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('已有内容，未自动提取')
  })

  it('auto-extracts after creating a record with pending attachments', async () => {
    workbenchActions.createHistoricalDeviation.mockResolvedValue({
      ...makeDetail({ id: 'new1', code: 'HD-202609003' }),
    })
    workbenchActions.uploadHistoricalDeviationAttachment.mockResolvedValue({
      id: 'att1',
      file_name: 'a.docx',
    })
    workbenchActions.aiExtractHistoricalDeviation.mockResolvedValue(
      makeDetail({ id: 'new1', deviation_event: '事件' }),
    )
    await renderPage()
    await act(async () => {
      clickButton('新建历史偏差')
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    await act(async () => {
      triggerDrawerUpload([makeFile('a.docx')])
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    await act(async () => {
      clickButton('保存')
      await new Promise((resolve) => setTimeout(resolve, 150))
    })
    expect(workbenchActions.uploadHistoricalDeviationAttachment).toHaveBeenCalledWith(
      'new1',
      expect.any(FormData),
    )
    expect(workbenchActions.aiExtractHistoricalDeviation).toHaveBeenCalledWith('new1')
  })

  it('re-extracts selected records in batch and lists per-record results', async () => {
    apiClient.fetchHistoricalDeviations.mockResolvedValue({
      items: [
        makeItem({ id: 'rec1', code: 'PC-2501001' }),
        makeItem({ id: 'rec2', code: 'PC-2501002' }),
      ],
      total: 2,
      page: 1,
      page_size: 20,
    })
    workbenchActions.aiExtractHistoricalDeviation.mockResolvedValueOnce(
      makeDetail({ deviation_event: '事件' }),
    )
    workbenchActions.aiExtractHistoricalDeviation.mockRejectedValueOnce(
      new Error('AI 提取失败：AI 服务调用失败，请稍后重试'),
    )
    await renderPage()
    await act(async () => {
      const checkboxes = document.body.querySelectorAll<HTMLInputElement>(
        '.ant-table-tbody tr.ant-table-row .ant-checkbox-input'
      )
      expect(checkboxes.length).toBe(2)
      checkboxes.forEach((node) => node.click())
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    await act(async () => {
      clickButton('批量重新提取（2）')
      await new Promise((resolve) => setTimeout(resolve, 150))
    })
    expect(workbenchActions.aiExtractHistoricalDeviation).toHaveBeenCalledWith('rec1')
    expect(workbenchActions.aiExtractHistoricalDeviation).toHaveBeenCalledWith('rec2')
    const text = document.body.textContent || ''
    expect(text).toContain('批量重新提取完成：成功 1 条，失败 1 条')
    expect(text).toContain('批量重新提取结果')
    expect(text).toContain('AI 服务调用失败')
  })
})