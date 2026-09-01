'use client'

import Image from 'next/image'
import {
  App,
  Button,
  Empty,
  Modal,
  Space,
  Spin,
  Table,
  Tag,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  DeleteOutlined,
  EyeOutlined,
  PaperClipOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import { deleteDocumentEntryAttachment } from '@/actions/quality'
import type { DocumentEntryAttachment, DocumentEntryItem } from '@/types/quality'

/** 标准 MD 预览渲染：表格带边框、图片经相对 API 路径加载（同源 cookie 鉴权） */
const markdownPreviewComponents: Components = {
  img: (props) => (
    <Image
      src={typeof props.src === 'string' ? props.src : ''}
      alt={props.alt ?? ''}
      width={1200}
      height={900}
      unoptimized
      className="h-auto max-w-full rounded border border-gray-200"
    />
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-gray-300 bg-gray-50 px-2 py-1 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-gray-300 px-2 py-1 align-top">{children}</td>
  ),
}

export interface AttachmentPreviewState {
  attachment: DocumentEntryAttachment
  text: string
  blobUrl: string
  contentType: string
  loading: boolean
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 附件在线预览弹窗：word 附件展示标准 MD；图片直接展示；PDF 内嵌预览 */
export function DocumentAttachmentPreviewModal({
  preview,
  onClose,
}: {
  preview: AttachmentPreviewState | null
  onClose: () => void
}) {
  return (
    <Modal
      title={
        <span>
          <EyeOutlined className="mr-2" />
          附件预览 - {preview?.attachment.file_name || ''}
        </span>
      }
      open={!!preview}
      onCancel={onClose}
      footer={null}
      width={900}
      destroyOnHidden
    >
      <Spin spinning={preview?.loading ?? false}>
        {preview && !preview.loading && (
          <div className="max-h-[70vh] overflow-auto">
            {preview.blobUrl ? (
              preview.contentType.includes('pdf') ? (
                <iframe
                  src={preview.blobUrl}
                  title="PDF 预览"
                  className="h-[68vh] w-full border-0"
                />
              ) : (
                <Image
                  src={preview.blobUrl}
                  alt={preview.attachment.file_name}
                  width={1200}
                  height={900}
                  unoptimized
                  className="h-auto max-w-full"
                />
              )
            ) : (
              <div className="whitespace-pre-wrap break-words bg-gray-50 p-4 text-sm leading-relaxed">
                {preview.text ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownPreviewComponents}
                  >
                    {preview.text}
                  </ReactMarkdown>
                ) : (
                  '无预览内容'
                )}
              </div>
            )}
          </div>
        )}
      </Spin>
    </Modal>
  )
}

interface Props {
  open: boolean
  entry: DocumentEntryItem | null
  onClose: () => void
  onChanged: () => void
  onPreview: (attachment: DocumentEntryAttachment) => void
}

/** 文件条目附件管理弹窗：导入附件（自动识别文件名/编号绑定）+ 列表 + 预览 + 删除 */
export default function DocumentEntryAttachmentModal({
  open,
  entry,
  onClose,
  onChanged,
  onPreview,
}: Props) {
  const { message, modal } = App.useApp()

  const attachments: DocumentEntryAttachment[] = entry?.attachments ?? []

  const handleDelete = (attachment: DocumentEntryAttachment) => {
    if (!entry) return
    modal.confirm({
      title: '删除附件',
      content: `确定删除「${attachment.file_name}」吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDocumentEntryAttachment(entry.id, attachment.storage_key)
          message.success('已删除')
          onChanged()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  const columns: TableColumnsType<DocumentEntryAttachment> = [
    {
      title: '附件文件',
      dataIndex: 'file_name',
      ellipsis: { showTitle: false },
      render: (value: string) => (
        <Space size={4}>
          <PaperClipOutlined className="text-gray-400" />
          <span>{value}</span>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'converted',
      width: 90,
      render: (_: unknown, record: DocumentEntryAttachment) =>
        record.converted ? <Tag color="blue">标准MD</Tag> : <Tag>原文件</Tag>,
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      width: 90,
      render: (value: number | null) => formatSize(value),
    },
    {
      title: '上传时间',
      dataIndex: 'uploaded_at',
      width: 160,
      render: (value: string | null) => (value ? value.slice(0, 19).replace('T', ' ') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      render: (_: unknown, record: DocumentEntryAttachment) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => onPreview(record)}
          >
            预览
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Modal
      title={
        <span>
          <PaperClipOutlined className="mr-2" />
          附件管理{entry ? ` - ${entry.name}` : ''}
        </span>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={860}
      destroyOnHidden
    >
      <div className="mb-4 text-sm text-gray-500">
        附件通过页面顶部「导入附件」统一导入，系统按文件名/编号自动识别绑定（识别失败时由
        LLM 匹配）。此处可查看、预览或删除当前条目的附件。
      </div>

      <Table<DocumentEntryAttachment>
        rowKey="storage_key"
        size="small"
        columns={columns}
        dataSource={attachments}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无附件" /> }}
      />
    </Modal>
  )
}
