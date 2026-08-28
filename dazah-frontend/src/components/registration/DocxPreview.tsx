'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import { Spin, Empty, Button, App } from 'antd'
import { DownloadOutlined, ReloadOutlined, FileWordOutlined } from '@ant-design/icons'
import { fetchChapterDocx } from '@/lib/api/dossier-writer-client'

interface DocxPreviewProps {
  chapterId: string | null
  chapterTitle?: string
  onDownload?: () => void
  refreshKey?: number
}

export function DocxPreview({ chapterId, chapterTitle, onDownload, refreshKey }: DocxPreviewProps) {
  const { message } = App.useApp()
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasContent, setHasContent] = useState(false)

  const renderDocx = useCallback(async () => {
    if (!chapterId || !containerRef.current) return

    setLoading(true)
    setError(null)

    try {
      const buffer = await fetchChapterDocx(chapterId)
      if (!buffer) {
        setHasContent(false)
        setError(null)
        return
      }

      setHasContent(true)

      // Dynamic import to avoid SSR issues
      const docx = await import('docx-preview')

      // Clear previous content
      containerRef.current.innerHTML = ''

      await docx.renderAsync(buffer, containerRef.current, undefined, {
        className: 'docx-preview-wrapper',
        inWrapper: true,
        ignoreWidth: false,
        ignoreHeight: false,
        ignoreFonts: false,
        breakPages: true,
        ignoreLastRenderedPageBreak: true,
        experimental: false,
        renderHeaders: true,
        renderFooters: true,
      })
    } catch (err) {
      console.error('DocxPreview render error:', err)
      setError((err instanceof Error ? err.message : '') || '文档渲染失败')
      setHasContent(false)
    } finally {
      setLoading(false)
    }
  }, [chapterId])

  useEffect(() => {
    queueMicrotask(renderDocx)
  }, [renderDocx, refreshKey])

  const handleRefresh = () => {
    renderDocx()
  }

  if (!chapterId) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <Empty description="请从左侧目录选择一个章节" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileWordOutlined className="text-blue-500 flex-shrink-0" />
          <span className="text-sm font-medium truncate">
            {chapterTitle || '文档预览'}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button
            size="small"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
          >
            刷新
          </Button>
          {hasContent && (
            <Button
              size="small"
              type="primary"
              icon={<DownloadOutlined />}
              onClick={onDownload}
            >
              下载
            </Button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {loading && (
          <div className="flex items-center justify-center h-64">
            <Spin size="large"><span className="text-sm text-gray-500">加载文档中...</span></Spin>
          </div>
        )}

        {!loading && error && (
          <Empty
            description={error}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}

        {!loading && !error && !hasContent && (
          <Empty description="该章节尚无工作副本文件" />
        )}

        <div
          ref={containerRef}
          className="docx-preview-container bg-white shadow-sm rounded"
          style={{ minHeight: hasContent ? 'auto' : '100%' }}
        />
      </div>

      {/* Global styles for docx-preview */}
      <style jsx global>{`
        .docx-preview-wrapper {
          background: white;
          padding: 40px 60px;
          min-height: 297mm;
          width: 210mm;
          margin: 0 auto;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .docx-preview-container {
          max-width: 100%;
        }
        .docx-preview-wrapper table {
          border-collapse: collapse;
          width: 100%;
        }
        .docx-preview-wrapper td,
        .docx-preview-wrapper th {
          border: 1px solid #333;
          padding: 4px 8px;
        }
      `}</style>
    </div>
  )
}
