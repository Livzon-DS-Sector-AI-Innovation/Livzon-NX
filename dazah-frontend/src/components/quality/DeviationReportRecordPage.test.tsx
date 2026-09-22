/* @vitest-environment happy-dom */
/* @vitest-environment-options {"settings":{"disableIframePageLoading":true,"handleDisabledFileLoadingAsSuccess":true}} */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { feishuColumnLayouts } from './feishuColumnLayout'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ list: vi.fn(), update: vi.fn(), fetch: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/actions/quality', () => ({ pullQualityRecordsFromFeishu: vi.fn() }))
vi.mock('docx-preview', () => ({ renderAsync: async (_data: ArrayBuffer, target: HTMLElement) => { target.textContent = '报告正文' } }))
vi.mock('@/actions/quality-deviation', () => ({ updateDeviationReportRecord: mocks.update, deleteDeviationReportRecord: vi.fn() }))
vi.mock('@/lib/api/client/quality', () => ({
  fetchFeishuDeviationReportRecords: mocks.list,
  fetchQualityFeishuAppSettings: async () => ({}),
  fetchQualityPersonDirectory: async () => [
    { name: '原报告人', open_id: 'ou_old' }, { name: '新报告人', open_id: 'ou_new' },
  ],
  formatQualitySyncSummary: () => '',
}))
import { DeviationReportRecordPage } from './DeviationReportRecordPage'

let root: Root
let container: HTMLDivElement
let client: QueryClient
beforeEach(() => {
  class ImmediateIntersectionObserver implements IntersectionObserver {
    readonly root = null
    readonly rootMargin = '0px'
    readonly thresholds = [0]
    constructor(private readonly callback: IntersectionObserverCallback) {}
    observe(target: Element) {
      this.callback(
        [{ isIntersecting: true, target } as IntersectionObserverEntry],
        this,
      )
    }
    unobserve() {}
    disconnect() {}
    takeRecords() { return [] }
  }
  vi.stubGlobal('IntersectionObserver', ImmediateIntersectionObserver)
  mocks.fetch.mockReset().mockResolvedValue({
    ok: true,
    blob: async () => new Blob(['image'], { type: 'image/jpeg' }),
    arrayBuffer: async () => new ArrayBuffer(4),
  })
  vi.stubGlobal('fetch', mocks.fetch)
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test-thumbnail')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  localStorage.clear()
  mocks.update.mockReset().mockResolvedValue({})
  mocks.list.mockReset().mockResolvedValue({ items: [{
    id: 'record', record_id: 'record', deviation_code: null, description: '测试', product_batch: '产品',
    reporters: [{ name: '原报告人', id: 'ou_old' }],
    attachments: [
      { name: '照片.png', url: 'https://example.test/image.png', file_token: 'ft_image' },
      { name: '报告.docx', file_token: 'ft_doc' },
    ],
  }], total: 1 })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})
afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
async function renderPage() {
  await act(async () => root.render(<App><QueryClientProvider client={client}><DeviationReportRecordPage /></QueryClientProvider></App>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 40)) })
}
async function clickButton(text: string) {
  const button = Array.from(document.querySelectorAll('button')).find(item => item.textContent?.replace(/\s/g, '') === text)
  expect(button).toBeTruthy()
  await act(async () => button!.click())
}
it('shows attachments in both the list and details with the narrower columns', async () => {
  await renderPage()
  expect(Array.from(container.querySelectorAll('th')).map(el => el.textContent)).toEqual([...feishuColumnLayouts.deviationReport, '操作'])
  const widths = Array.from(container.querySelectorAll('col')).map(col => col.style.width)
  expect(widths.slice(0, 7)).toEqual(['107px', '180px', '280px', '220px', '200px', '93px', '107px'])
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 40)) })
  expect(container.querySelector('img[alt="照片.png"]')).toBeTruthy()
  expect(mocks.fetch).toHaveBeenCalledWith(
    '/api/v1/quality/deviation-report-records/record/attachments/ft_image/thumbnail',
  )
  expect(container.querySelector('img[alt="照片.png"]')?.getAttribute('src')).toBe('blob:test-thumbnail')
  expect(container.textContent).toContain('报告.docx')
  await clickButton('详情')
  const detailDialog = document.querySelector('[role="dialog"]')
  expect(detailDialog?.querySelector('img[alt="照片.png"]')).toBeTruthy()
  expect(detailDialog?.textContent).toContain('报告.docx')
  const documentButton = Array.from(document.querySelectorAll('button')).find(
    item => item.textContent === '报告.docx',
  )
  expect(documentButton).toBeTruthy()
  await act(async () => documentButton!.click())
  expect(mocks.fetch).toHaveBeenCalledWith(
    '/api/v1/quality/deviation-report-records/record/attachments/ft_doc/content',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  )
  expect(document.querySelector('[role="document"]')?.textContent).toContain('报告正文')
})
it('saves a new reporter without asking for a deviation code or report document', async () => {
  await renderPage()
  await clickButton('编辑')
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 40)) })
  const input = document.querySelector<HTMLInputElement>('[role="dialog"] input[role="combobox"]')!
  await act(async () => input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find(el => el.textContent === '新报告人')!
  expect(option).toBeTruthy()
  await act(async () => option.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  await clickButton('保存')
  expect(mocks.update).toHaveBeenCalledWith('record', { description: '测试', product_batch: '产品', reporter_open_id: 'ou_new' })
})
it('retains the edit dialog and entered values after save failure', async () => {
  mocks.update.mockRejectedValue(new Error('保存失败，请重试'))
  await renderPage()
  await clickButton('编辑')
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 40)) })
  await clickButton('保存')
  expect(document.querySelector('[role="dialog"]')).toBeTruthy()
  expect(document.querySelector('textarea')?.value).toBe('测试')
  expect(document.body.textContent).toContain('保存失败，请重试')
})
