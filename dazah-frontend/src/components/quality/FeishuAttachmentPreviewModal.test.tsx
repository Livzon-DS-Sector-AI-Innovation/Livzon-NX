/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const renderDocx = vi.hoisted(() => vi.fn())
vi.mock('docx-preview', () => ({ renderAsync: renderDocx }))
const pdfMocks = vi.hoisted(() => ({ getDocument: vi.fn(), getPage: vi.fn(), render: vi.fn(), destroy: vi.fn(), cancel: vi.fn() }))
vi.mock('pdfjs-dist/build/pdf.min.mjs', () => ({ GlobalWorkerOptions: {}, getDocument: pdfMocks.getDocument }))

import { FeishuAttachmentPreviewModal } from './FeishuAttachmentPreviewModal'

describe('FeishuAttachmentPreviewModal', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    renderDocx.mockReset().mockImplementation(async (_data, target: HTMLElement) => {
      target.textContent = '文档正文与表格'
    })
    pdfMocks.cancel.mockReset()
    pdfMocks.destroy.mockReset().mockResolvedValue(undefined)
    pdfMocks.render.mockReset().mockReturnValue({ promise: Promise.resolve(), cancel: pdfMocks.cancel })
    pdfMocks.getPage.mockReset().mockResolvedValue({
      getViewport: () => ({ width: 600, height: 800 }), render: pdfMocks.render,
    })
    pdfMocks.getDocument.mockReset().mockReturnValue({
      promise: Promise.resolve({ numPages: 2, getPage: pdfMocks.getPage }), destroy: pdfMocks.destroy,
    })
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body
      .querySelectorAll('.ant-modal-root')
      .forEach((node) => node.remove())
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  function renderModal(props: {
    fileName: string
    previewSrc: string
    downloadSrc: string
  }) {
    act(() => {
      root.render(
        <FeishuAttachmentPreviewModal
          open
          fileName={props.fileName}
          previewSrc={props.previewSrc}
          downloadSrc={props.downloadSrc}
          onClose={() => {}}
        />,
      )
    })
  }

  it.each(['pdf', 'doc', 'wps', 'WPS'])('renders %s inside the dialog and supports paging without a browser plugin', async (extension) => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) })
    vi.stubGlobal('fetch', fetchMock)
    renderModal({
      fileName: `调查报告.${extension}`,
      previewSrc: '/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft-1/preview?year=2026',
      downloadSrc: '/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft-1/content?year=2026',
    })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft-1/preview?year=2026',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.querySelector('canvas')?.getAttribute('aria-label')).toBe(`调查报告.${extension} 第 1 页`)
    expect(document.body.querySelector('canvas')?.style.display).toBe('inline-block')
    expect(document.body.textContent).toContain('第 1 / 2 页')
    const next = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent === '下一页')
    await act(async () => next?.click())
    expect(pdfMocks.getPage).toHaveBeenLastCalledWith(2)
    expect(document.body.textContent).toContain('第 2 / 2 页')
    expect(document.body.querySelector('canvas')?.getAttribute('aria-label')).toBe(`调查报告.${extension} 第 2 页`)
    expect(pdfMocks.cancel).toHaveBeenCalled()
    expect(next?.disabled).toBe(true)
  })

  it('shows conversion failure instead of an empty document', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => ({ message: '文档转换失败' }) }))
    renderModal({ fileName: '作业票.wps', previewSrc: '/preview/wps', downloadSrc: '/download/wps' })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
    expect(document.body.textContent).toContain('文档转换失败')
    expect(document.body.textContent).toContain('下载原文件')
    expect(pdfMocks.getDocument).not.toHaveBeenCalled()
  })

  it('shows a readable error for an invalid PDF', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) }))
    pdfMocks.getDocument.mockImplementation(() => ({ promise: Promise.reject(new Error('PDF 文件损坏')), destroy: pdfMocks.destroy }))
    renderModal({ fileName: '报告.pdf', previewSrc: '/preview/pdf', downloadSrc: '/download/pdf' })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
    expect(document.body.textContent).toContain('PDF 文件损坏')
  })

  it('aborts a pending document request when the preview closes', async () => {
    let requestSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn().mockImplementation((_src, options) => {
      requestSignal = options.signal
      return new Promise(() => {})
    }))
    renderModal({ fileName: '作业票.doc', previewSrc: '/preview/doc', downloadSrc: '/download/doc' })
    expect(requestSignal?.aborted).toBe(false)
    await act(async () => root.render(null))
    expect(requestSignal?.aborted).toBe(true)
  })

  it('renders DOCX content inside the dialog without a PDF browser plugin', async () => {
    const buffer = new ArrayBuffer(4)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: async () => buffer })
    vi.stubGlobal('fetch', fetchMock)
    renderModal({
      fileName: '情况说明.docx',
      previewSrc: '/preview/doc',
      downloadSrc: '/download/doc',
    })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
    expect(fetchMock).toHaveBeenCalledWith('/download/doc', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(renderDocx).toHaveBeenCalledWith(buffer, expect.any(HTMLElement), undefined, expect.any(Object))
    expect(document.body.querySelector('[role="document"]')?.textContent).toContain('文档正文与表格')
    expect(document.body.querySelector('iframe')).toBeNull()
    expect(document.body.querySelector('img')).toBeNull()
  })

  it('shows the server error when DOCX cannot be loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 502, json: async () => ({ message: '附件下载失败' }),
    }))
    renderModal({ fileName: '报告.docx', previewSrc: '/preview/doc', downloadSrc: '/download/doc' })
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
    expect(document.body.textContent).toContain('附件下载失败')
    expect(renderDocx).not.toHaveBeenCalled()
  })

  it('renders image attachment inline', () => {
    renderModal({
      fileName: '现场照片.png',
      previewSrc: '/preview/img',
      downloadSrc: '/download/img',
    })
    const img = document.body.querySelector('.ant-modal img')
    expect(img?.getAttribute('src')).toBe('/preview/img')
    expect(document.body.querySelector('iframe')).toBeNull()
  })

  it('fetches and renders text attachments as plain text', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('仪器校准记录\nline2'),
    })
    vi.stubGlobal('fetch', fetchMock)
    renderModal({
      fileName: '校准记录.txt',
      previewSrc: '/preview/txt',
      downloadSrc: '/download/txt',
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(fetchMock).toHaveBeenCalledWith('/preview/txt')
    const modalText = document.body.textContent || ''
    expect(modalText).toContain('仪器校准记录')
    expect(modalText).toContain('line2')
    expect(document.body.querySelector('iframe')).toBeNull()
    vi.unstubAllGlobals()
  })

  it('shows failure alert when the text preview request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    renderModal({
      fileName: '损坏记录.txt',
      previewSrc: '/preview/txt-fail',
      downloadSrc: '/download/txt-fail',
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(document.body.textContent).toContain('文本内容加载失败')
    expect(document.body.textContent).toContain('请点击下方按钮下载原文件查看')
    vi.unstubAllGlobals()
  })

  it('falls back to download hint for unsupported extensions', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    renderModal({
      fileName: '打包资料.zip',
      previewSrc: '/preview/zip',
      downloadSrc: '/download/zip',
    })
    expect(document.body.textContent).toContain('该格式暂不支持在线预览')
    const downloadButton = Array.from(
      document.body.querySelectorAll('.ant-modal button'),
    ).find((btn) => (btn.textContent || '').includes('下载原文件'))
    expect(downloadButton).toBeTruthy()
    await act(async () => {
      ;(downloadButton as HTMLElement | null)?.click()
    })
    expect(openMock).toHaveBeenCalledWith('/download/zip', '_blank', 'noopener,noreferrer')
  })
})
