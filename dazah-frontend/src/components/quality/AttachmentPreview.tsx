'use client'

import { useState, useEffect } from 'react'
import { App, Modal, Button, List, Input, Space, Typography, Image, Spin } from 'antd'
import { DownloadOutlined, FileTextOutlined, CommentOutlined, DeleteOutlined, SendOutlined } from '@ant-design/icons'
import type { AttachmentReview, FileAttachmentInfo } from '@/types/quality'
import { createAttachmentReview, deleteAttachmentReview } from '@/actions/quality'

const { TextArea } = Input
const { Text, Paragraph } = Typography


type FileType = 'pdf' | 'docx' | 'image' | 'unknown'

function getFileType(fileName: string): FileType {
  const ext = fileName.split('.').pop()?.toLowerCase() || ''
  if (ext === 'pdf') return 'pdf'
  if (ext === 'docx') return 'docx'
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return 'image'
  return 'unknown'
}

interface AttachmentPreviewProps {
  attachment: FileAttachmentInfo | null
  deviationId?: string
  capaId?: string
  onClose: () => void
  open: boolean
}

export function AttachmentPreview({
  attachment,
  deviationId,
  capaId,
  onClose,
  open,
}: AttachmentPreviewProps) {
  const { message } = App.useApp()
  const [reviews, setReviews] = useState<AttachmentReview[]>([])

  const fetchReviews = async () => {
    try {
      const response = await fetch(`/api/v1/quality/attachment-reviews?attachment_url=${encodeURIComponent(attachment?.downloadUrl || '')}`)
      if (response.ok) {
        const data = await response.json()
        setReviews(data)
      }
    } catch (err) {
      console.error('Failed to fetch reviews:', err)
    }
  }
  const [newComment, setNewComment] = useState('')
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open || !attachment) return
    let cancelled = false

    const fetchReviews = async () => {
      if (!attachment?.downloadUrl) return
      setLoading(true)
      try {
        const params = new URLSearchParams()
        params.append('attachment_url', attachment.downloadUrl)
        if (deviationId) params.append('deviation_id', deviationId)
        if (capaId) params.append('capa_id', capaId)

        const response = await fetch(`/api/v1/quality/attachment-reviews?${params.toString()}`)
        if (!response.ok) throw new Error('请求失败')
        const result = await response.json()
        if (!cancelled) setReviews(result?.data || [])
      } catch {
        if (!cancelled) message.error('加载审阅记录失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchReviews()

    return () => {
      cancelled = true
    }
  }, [open, attachment, deviationId, capaId, message])

  const handleSubmitReview = async () => {
    if (!newComment.trim() || !attachment?.downloadUrl) return
    setSubmitting(true)
    try {
      await createAttachmentReview({
        deviation_id: deviationId || null,
        capa_id: capaId || null,
        attachment_url: attachment.downloadUrl,
        content: newComment.trim(),
      })
      setNewComment('')
      await fetchReviews()
      message.success('审阅意见已提交')
    } catch {
      message.error('提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteReview = async (reviewId: string) => {
    try {
      await deleteAttachmentReview(reviewId)
      await fetchReviews()
      message.success('已删除')
    } catch {
      message.error('删除失败')
    }
  }

  const handleDownload = () => {
    if (attachment?.downloadUrl) {
      window.open(attachment.downloadUrl, '_blank')
    }
  }

  if (!attachment) return null

  const fileType = getFileType(attachment.fileName || '')
  const isImage = fileType === 'image'

  return (
    <Modal
      title={
        <Space>
          <FileTextOutlined />
          <span>{attachment.fileName || '附件预览'}</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={1000}
      footer={null}
    >
      <div style={{ display: 'flex', gap: 24 }}>
        {/* Preview area */}
        <div style={{ flex: 1, minHeight: 400, background: '#f5f5f5', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {isImage ? (
            <Image
              src={attachment.downloadUrl || ''}
              alt={attachment.fileName || ''}
              style={{ maxWidth: '100%', maxHeight: 500 }}
              fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            />
          ) : fileType === 'pdf' ? (
            <iframe
              src={attachment.downloadUrl || ''}
              style={{ width: '100%', height: 500, border: 'none' }}
              title="PDF Preview"
            />
          ) : (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <FileTextOutlined style={{ fontSize: 64, color: '#999' }} />
              <p style={{ marginTop: 16, color: '#666' }}>
                {fileType === 'docx' ? 'Word 文档' : '未知文件类型'}
              </p>
              <Button type="primary" icon={<DownloadOutlined />} onClick={handleDownload}>
                下载文件
              </Button>
            </div>
          )}
        </div>

        {/* Reviews sidebar */}
        <div style={{ width: 320, borderLeft: '1px solid #f0f0f0', paddingLeft: 24 }}>
          <Space style={{ marginBottom: 16 }}>
            <CommentOutlined />
            <Text strong>审阅意见 ({reviews.length})</Text>
          </Space>

          {loading ? (
            <Spin />
          ) : reviews.length === 0 ? (
            <Text type="secondary">暂无审阅意见</Text>
          ) : (
            <List
              size="small"
              dataSource={reviews}
              renderItem={(review) => (
                <List.Item
                  actions={[
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDeleteReview(review.id)}
                    />,
                  ]}
                >
                  <List.Item.Meta
                    title={review.reviewer_id}
                    description={
                      <>
                        <Paragraph style={{ marginBottom: 0 }}>{review.content}</Paragraph>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {review.review_time ? new Date(review.review_time).toLocaleString() : ''}
                        </Text>
                      </>
                    }
                  />
                </List.Item>
              )}
            />
          )}

          <div style={{ marginTop: 16 }}>
            <TextArea
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              placeholder="输入审阅意见..."
              autoSize={{ minRows: 2, maxRows: 4 }}
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSubmitReview}
              loading={submitting}
              disabled={!newComment.trim()}
              style={{ marginTop: 8, width: '100%' }}
            >
              提交
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
