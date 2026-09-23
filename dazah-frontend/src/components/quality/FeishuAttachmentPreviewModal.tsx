'use client'

import { Alert, Button, Modal, Space, Spin } from 'antd'
import { DownloadOutlined, FileTextOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState } from 'react'
import { FeishuPdfPreview } from './FeishuPdfPreview'

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'])
const PDF_EXTS = new Set(['.pdf'])
// 与后端 PREVIEW_OFFICE_EXTS 对应：服务端转换成 PDF 后返回
const OFFICE_EXTS = new Set([
  '.doc',
  '.docx',
  '.wps',
  '.xls',
  '.xlsx',
  '.csv',
  '.ppt',
  '.pptx',
])
// 与后端 PREVIEW_TEXT_EXTS 对应：/preview 返回 text/plain 纯文本
const TEXT_EXTS = new Set(['.txt', '.log', '.md', '.json', '.xml', '.yaml', '.yml'])

interface FeishuAttachmentPreviewModalProps {
  open: boolean
  fileName: string
  /** 预览地址（后端 /preview 端点：图片/PDF 原样 inline，office 已转 PDF，文本为纯文本） */
  previewSrc: string
  /** 原文件下载地址 */
  downloadSrc: string
  onClose: () => void
}

type PreviewKind = 'image' | 'pdf' | 'docx' | 'text' | 'unknown'

function resolveKind(fileName: string): PreviewKind {
  const ext = (fileName.match(/\.[a-z0-9]+$/i)?.[0] || '').toLowerCase()
  if (IMAGE_EXTS.has(ext)) return 'image'
  if (ext === '.docx') return 'docx'
  if (PDF_EXTS.has(ext) || OFFICE_EXTS.has(ext)) return 'pdf'
  if (TEXT_EXTS.has(ext)) return 'text'
  return 'unknown'
}

/** DOCX 使用本地渲染库展示正文，兼容未内置 PDF 阅读器的浏览器。 */
function DocxPreview({ src, fileName }: { src: string; fileName: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const controller = new AbortController()
    const render = async () => {
      try {
        const response = await fetch(src, { signal: controller.signal })
        if (!response.ok) {
          const body = await response.json().catch(() => null)
          throw new Error(body?.message || `文档加载失败（${response.status}）`)
        }
        const buffer = await response.arrayBuffer()
        const { renderAsync } = await import('docx-preview')
        if (controller.signal.aborted) return
        // 在独立容器中渲染，关闭或切换附件时不把旧文档挂载到新预览。
        const rendered = document.createElement('div')
        await renderAsync(buffer, rendered, undefined, {
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          breakPages: true,
          useBase64URL: true,
        })
        if (!controller.signal.aborted) container.replaceChildren(rendered)
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : '文档加载失败')
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void render()
    return () => controller.abort()
  }, [src])

  return (
    <div>
      {loading && <div style={{ textAlign: 'center', padding: 48 }}><Spin /></div>}
      {error && <Alert type="warning" showIcon title={error} description="请重试或下载原文件查看。" />}
      <div
        ref={containerRef}
        role="document"
        aria-label={fileName}
        style={{ maxHeight: '72vh', overflow: 'auto' }}
      />
    </div>
  )
}

/** 文本附件：fetch /preview 的 text/plain 内容并以等宽文本展示。 */
function TextPreview({ src, fileName }: { src: string; fileName: string }) {
  const [text, setText] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setText(null)
    setFailed(false)
    fetch(src)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.text()
      })
      .then((body) => {
        if (!cancelled) setText(body)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [src])

  if (failed) {
    return (
      <Alert
        type="warning"
        showIcon
        message="文本内容加载失败"
        description="请点击下方按钮下载原文件查看。"
      />
    )
  }
  if (text === null) {
    return (
      <div style={{ textAlign: 'center', padding: '48px 0' }}>
        <Spin />
      </div>
    )
  }
  return (
    <pre
      title={fileName || '附件预览'}
      style={{
        margin: 0,
        maxHeight: '72vh',
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: 13,
        lineHeight: 1.6,
        background: 'var(--color-bg-soft, rgba(0,0,0,0.02))',
        padding: 12,
        borderRadius: 6,
      }}
    >
      {text}
    </pre>
  )
}

/** 飞书附件弹窗预览：图片直接显示；DOCX 页内渲染；PDF（含其他 office 转换结果）内嵌渲染；
 * 文本类展示纯文本；其余提示下载。 */
export function FeishuAttachmentPreviewModal({
  open,
  fileName = '',
  previewSrc = '',
  downloadSrc = '',
  onClose,
}: FeishuAttachmentPreviewModalProps) {
  const kind = resolveKind(fileName ?? '')

  return (
    <Modal
      title={
        <Space size={8} style={{ maxWidth: '100%' }}>
          <FileTextOutlined />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {fileName || '附件预览'}
          </span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={960}
      destroyOnHidden
      footer={
        <Space>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => window.open(downloadSrc, '_blank', 'noopener,noreferrer')}
          >
            下载原文件
          </Button>
        </Space>
      }
    >
      {kind === 'image' ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={previewSrc}
          alt={fileName || '附件预览'}
          style={{ maxWidth: '100%', maxHeight: '70vh', display: 'block', margin: '0 auto' }}
        />
      ) : kind === 'docx' && open ? (
        <DocxPreview key={downloadSrc} src={downloadSrc} fileName={fileName} />
      ) : kind === 'pdf' && open ? (
        <FeishuPdfPreview key={previewSrc} src={previewSrc} fileName={fileName} />
      ) : kind === 'text' && open ? (
        <TextPreview src={previewSrc} fileName={fileName} />
      ) : (
        <Alert
          type="warning"
          showIcon
          message="该格式暂不支持在线预览"
          description="请点击下方按钮下载原文件查看。"
        />
      )}
    </Modal>
  )
}
