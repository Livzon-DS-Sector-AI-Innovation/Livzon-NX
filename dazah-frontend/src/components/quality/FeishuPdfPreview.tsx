'use client'

import { Alert, Button, Space, Spin } from 'antd'
import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'

function PdfPage({ pdf, pageNumber, fileName }: {
  pdf: PDFDocumentProxy
  pageNumber: number
  fileName: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let task: RenderTask | undefined
    const render = async () => {
      try {
        const page = await pdf.getPage(pageNumber)
        const canvas = canvasRef.current
        if (cancelled || !canvas) return
        const viewport = page.getViewport({ scale: 1.5 })
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
        canvas.width = Math.ceil(viewport.width * pixelRatio)
        canvas.height = Math.ceil(viewport.height * pixelRatio)
        canvas.style.width = `${viewport.width}px`
        task = page.render({
          canvas,
          viewport,
          transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
        })
        await task.promise
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : '文档页面加载失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void render()
    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [pdf, pageNumber])

  return (
    <div style={{ maxHeight: '65vh', overflow: 'auto', textAlign: 'center' }}>
      {loading && <Spin aria-label="正在绘制文档" />}
      {error && <Alert type="warning" showIcon title="文档页面加载失败" description={error} />}
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`${fileName} 第 ${pageNumber} 页`}
        style={{ maxWidth: '100%', height: 'auto', display: loading || error ? 'none' : 'inline-block' }}
      />
    </div>
  )
}

/** 使用站内阅读器，避免内嵌浏览器缺少 PDF 插件时出现空白。 */
export function FeishuPdfPreview({ src, fileName }: { src: string; fileName: string }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pageNumber, setPageNumber] = useState(1)

  useEffect(() => {
    const controller = new AbortController()
    let task: PDFDocumentLoadingTask | undefined
    const load = async () => {
      try {
        const response = await fetch(src, { signal: controller.signal })
        if (!response.ok) {
          const body = await response.json().catch(() => null)
          throw new Error(body?.message || `文档加载失败（${response.status}）`)
        }
        const data = await response.arrayBuffer()
        // min 入口避免 Next.js Webpack 对 PDF.js 内部模块变量的重命名冲突。
        const pdfjs = await import('pdfjs-dist/build/pdf.min.mjs')
        if (controller.signal.aborted) return
        // Worker 随应用打包、同源加载，附件内容无需交给第三方预览服务。
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          'pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url,
        ).toString()
        task = pdfjs.getDocument({ data: new Uint8Array(data), isEvalSupported: false })
        const document = await task.promise
        if (!controller.signal.aborted) setPdf(document)
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : '文档加载失败')
        }
      }
    }
    void load()
    return () => {
      controller.abort()
      void task?.destroy().catch(() => undefined)
    }
  }, [src])

  if (error) {
    return <Alert type="warning" showIcon title={error} description="请重新打开预览，或下载原文件查看。" />
  }
  if (!pdf) {
    return <div style={{ padding: 48, textAlign: 'center' }}><Spin aria-label="正在加载文档" /></div>
  }
  return (
    <div>
      <Space style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
        <Button disabled={pageNumber === 1} onClick={() => setPageNumber(pageNumber - 1)}>上一页</Button>
        <span role="status">第 {pageNumber} / {pdf.numPages} 页</span>
        <Button disabled={pageNumber === pdf.numPages} onClick={() => setPageNumber(pageNumber + 1)}>下一页</Button>
      </Space>
      <PdfPage key={pageNumber} pdf={pdf} pageNumber={pageNumber} fileName={fileName} />
    </div>
  )
}
