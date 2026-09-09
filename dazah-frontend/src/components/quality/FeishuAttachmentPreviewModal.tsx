'use client'

import { Alert, Button, Modal, Space } from 'antd'
import { DownloadOutlined, FileTextOutlined } from '@ant-design/icons'

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

interface FeishuAttachmentPreviewModalProps {
  open: boolean
  fileName: string
  /** 预览地址（后端 /preview 端点：图片/PDF 原样 inline，office 已转 PDF） */
  previewSrc: string
  /** 原文件下载地址 */
  downloadSrc: string
  onClose: () => void
}

function resolveKind(fileName: string): 'image' | 'pdf' | 'unknown' {
  const ext = (fileName.match(/\.[a-z0-9]+$/i)?.[0] || '').toLowerCase()
  if (IMAGE_EXTS.has(ext)) return 'image'
  if (PDF_EXTS.has(ext) || OFFICE_EXTS.has(ext)) return 'pdf'
  return 'unknown'
}

/** 飞书附件弹窗预览：图片直接显示；PDF（含 office 转换结果）内嵌渲染；其余提示下载。 */
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
      ) : kind === 'pdf' ? (
        <iframe
          src={previewSrc}
          title={fileName || '附件预览'}
          style={{ width: '100%', height: '72vh', border: 'none' }}
        />
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
