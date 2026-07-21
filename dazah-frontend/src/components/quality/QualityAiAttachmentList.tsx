'use client'

import { Button, Card, List, Space, Tag, Typography, Upload } from 'antd'
import type { DeviationAiSessionAttachment } from '@/types/quality'

interface QualityAiAttachmentListProps {
  attachments: DeviationAiSessionAttachment[]
  uploading: boolean
  deletingId: string | null
  onUpload: (file: File) => Promise<void>
  onDelete: (attachmentId: string) => Promise<void>
}

function formatFileSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

export function QualityAiAttachmentList({
  attachments,
  uploading,
  deletingId,
  onUpload,
  onDelete,
}: QualityAiAttachmentListProps) {
  return (
    <Card
      size="small"
      title="附件上下文"
      extra={
        <Upload
          accept=".doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
          showUploadList={false}
          beforeUpload={(file) => {
            void onUpload(file as File)
            return false
          }}
          disabled={uploading}
        >
          <Button loading={uploading}>上传附件</Button>
        </Upload>
      }
    >
      {attachments.length === 0 ? (
        <Typography.Text type="secondary">暂未上传附件，可上传 Word、表格或图片补充 AI 上下文。</Typography.Text>
      ) : (
        <List
          dataSource={attachments}
          renderItem={(attachment) => (
            <List.Item
              actions={[
                <Button
                  key="delete"
                  danger
                  type="link"
                  loading={deletingId === attachment.id}
                  onClick={() => void onDelete(attachment.id)}
                >
                  删除
                </Button>,
              ]}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space wrap>
                  <Typography.Text strong>{attachment.file_name}</Typography.Text>
                  <Tag color={attachment.parse_status === 'completed' ? 'green' : 'red'}>
                    {attachment.parse_status === 'completed' ? '已纳入上下文' : '解析失败'}
                  </Tag>
                  <Tag>{formatFileSize(attachment.file_size)}</Tag>
                </Space>
                {attachment.parsed_summary ? (
                  <Typography.Text type="secondary">{attachment.parsed_summary}</Typography.Text>
                ) : null}
                {attachment.parse_error ? (
                  <Typography.Text type="danger">{attachment.parse_error}</Typography.Text>
                ) : null}
              </Space>
            </List.Item>
          )}
        />
      )}
    </Card>
  )
}
