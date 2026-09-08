/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FeishuAttachmentPreviewModal } from './FeishuAttachmentPreviewModal'

describe('FeishuAttachmentPreviewModal', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body
      .querySelectorAll('.ant-modal-root')
      .forEach((node) => node.remove())
    vi.restoreAllMocks()
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

  it('renders pdf attachment in an inline iframe pointing at the preview endpoint', () => {
    renderModal({
      fileName: '调查报告.pdf',
      previewSrc: '/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft-1/preview?year=2026',
      downloadSrc: '/api/v1/quality/finished-product-anomaly/records/rec-1/attachments/ft-1/content?year=2026',
    })
    const iframe = document.body.querySelector('iframe')
    expect(iframe).toBeTruthy()
    expect(iframe?.getAttribute('src')).toContain('/preview?year=2026')
    expect(document.body.textContent).toContain('调查报告.pdf')
  })

  it('renders doc attachment as pdf iframe (server converts office to pdf)', () => {
    renderModal({
      fileName: '情况说明.docx',
      previewSrc: '/preview/doc',
      downloadSrc: '/download/doc',
    })
    expect(document.body.querySelector('iframe')).toBeTruthy()
    expect(document.body.querySelector('img')).toBeNull()
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
