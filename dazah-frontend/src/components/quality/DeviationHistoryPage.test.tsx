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
})