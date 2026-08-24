'use client'

import { useState } from 'react'
import { App, Avatar, Button, Card, Divider, Form, Input, List, Space, Tag, Typography, Upload } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, DownloadOutlined, EyeOutlined, FileOutlined, MessageOutlined, ThunderboltOutlined, LinkOutlined, UploadOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import { createKnowledgeComment, deleteKnowledgeComment, generateAttachmentSummary, uploadKnowledgeAttachment, deleteKnowledgeAttachment } from '@/actions/registration'
import type { KnowledgeArticleDetail as ArticleDetail, KnowledgeCommentCreate } from '@/types/registration'

const { Title, Text, Link } = Typography

// 安全的 Markdown 渲染样式映射（替代手写正则拼 HTML，避免 XSS）
const markdownComponents: Components = {
  h2: ({ children }) => (
    <h2 style={{ color: '#5645d4', marginTop: 24, marginBottom: 12, fontSize: 20, fontWeight: 600 }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ color: '#37352f', marginTop: 20, marginBottom: 8, fontSize: 16, fontWeight: 600 }}>{children}</h3>
  ),
  strong: ({ children }) => <strong style={{ color: '#37352f' }}>{children}</strong>,
  ul: ({ children }) => <ul style={{ listStyle: 'disc', paddingLeft: 20 }}>{children}</ul>,
  li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
}

interface KnowledgeArticleDetailProps {
  article: ArticleDetail
}

export default function KnowledgeArticleDetail({ article }: KnowledgeArticleDetailProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [commentForm] = Form.useForm<KnowledgeCommentCreate>()
  const [submitting, setSubmitting] = useState(false)
  const [summarizing, setSummarizing] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const handleComment = async (values: KnowledgeCommentCreate) => {
    setSubmitting(true)
    try {
      await createKnowledgeComment(article.id, values)
      message.success('评论成功')
      commentForm.resetFields()
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '评论失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteComment = async (commentId: string) => {
    try {
      await deleteKnowledgeComment(commentId, article.id)
      message.success('删除成功')
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const handleSummarize = async (attachmentId: string) => {
    setSummarizing(attachmentId)
    try {
      await generateAttachmentSummary(attachmentId, article.id)
      message.success('AI摘要生成成功')
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '摘要生成失败')
    } finally {
      setSummarizing(null)
    }
  }

  const handleDeleteAttachment = async (attachmentId: string) => {
    try {
      await deleteKnowledgeAttachment(attachmentId, article.id)
      message.success('附件已删除')
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await uploadKnowledgeAttachment(article.id, formData)
      message.success('附件上传成功')
      router.refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败')
    } finally {
      setUploading(false)
    }
    return false // prevent antd default upload
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const tags = article.tags ? article.tags.split(',').map(t => t.trim()).filter(Boolean) : []

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '0 8px' }}>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => router.push('/registration/knowledge')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>

      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #e5e3df',
          boxShadow: '0 4px 24px rgba(15,23,42,0.06)',
        }}
        styles={{ body: { padding: '32px 40px' } }}
      >
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <Title level={2} style={{ marginTop: 0, marginBottom: 12, color: '#1a1a1a', fontSize: 28, fontWeight: 700 }}>{article.title}</Title>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
            <Tag color="purple" style={{ borderRadius: 6, padding: '2px 12px', fontSize: 13 }}>{article.category_name}</Tag>
            {tags.map(tag => <Tag key={tag} style={{ borderRadius: 6, padding: '2px 12px', fontSize: 13, background: '#e6e0f5', border: 'none', color: '#5645d4' }}>{tag}</Tag>)}
            {article.country && <Tag color="green" style={{ borderRadius: 6, padding: '2px 12px', fontSize: 13 }}>{article.country}</Tag>}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, color: '#787671', fontSize: 13 }}>
            <span>作者：{article.author || '未知'}</span>
            <span>发布：{article.published_at ? new Date(article.published_at).toLocaleDateString('zh-CN') : '未发布'}</span>
            <span>浏览：{article.view_count} 次</span>
            {article.source_url && (
              <Link href={article.source_url} target="_blank" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <LinkOutlined /> 来源链接
              </Link>
            )}
          </div>
        </div>

        <Divider style={{ margin: '20px 0', borderColor: '#ede9e4' }} />

        {/* Content */}
        <div style={{ lineHeight: 1.9, fontSize: 15, color: '#37352f' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {article.content}
          </ReactMarkdown>
        </div>

        {/* Attachments section - always visible */}
        <Divider style={{ margin: '32px 0 20px', borderColor: '#ede9e4' }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0, color: '#1a1a1a' }}>
            <FileOutlined style={{ color: '#5645d4' }} /> 附件 ({article.attachments.length})
          </Title>
          <Upload
            showUploadList={false}
            beforeUpload={handleUpload}
            multiple={false}
          >
            <Button
              type="primary"
              ghost
              icon={<UploadOutlined />}
              loading={uploading}
              style={{ borderRadius: 6, borderColor: '#5645d4', color: '#5645d4' }}
            >
              上传附件
            </Button>
          </Upload>
        </div>

        {article.attachments.length > 0 ? (
          <List
            dataSource={article.attachments}
            renderItem={item => (
              <List.Item style={{ borderBottom: '1px solid #f0eeec', padding: '16px 0' }}>
                <div style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: 8,
                        background: 'linear-gradient(135deg, #e6e0f5 0%, #dcecfa 100%)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <FileOutlined style={{ fontSize: 18, color: '#5645d4' }} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, color: '#1a1a1a' }}>{item.file_name}</div>
                        <Text type="secondary" style={{ fontSize: 12 }}>{formatFileSize(item.file_size)} · {item.content_type}</Text>
                      </div>
                    </div>
                    <Space>
                      <Button
                        type="text"
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => window.open(`/api/v1/registration/knowledge/attachments/${item.id}/preview`, '_blank')}
                      >
                        预览
                      </Button>
                      {!item.ai_summary && (
                        <Button
                          type="primary"
                          ghost
                          size="small"
                          icon={<ThunderboltOutlined />}
                          loading={summarizing === item.id}
                          onClick={() => handleSummarize(item.id)}
                          style={{ borderRadius: 6 }}
                        >
                          AI摘要
                        </Button>
                      )}
                      <Button
                        type="text"
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => window.open(`/api/v1/registration/knowledge/attachments/${item.id}`, '_blank')}
                      />
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDeleteAttachment(item.id)}
                      />
                    </Space>
                  </div>

                  {item.ai_summary && (
                    <Card
                      size="small"
                      style={{
                        marginTop: 12,
                        borderRadius: 8,
                        background: 'linear-gradient(135deg, #fafaf9 0%, #f8f5e8 100%)',
                        border: '1px solid #ede9e4',
                      }}
                      title={<span style={{ fontSize: 13, color: '#5645d4' }}><ThunderboltOutlined /> AI 结构化摘要</span>}
                    >
                      <div style={{ fontSize: 14, lineHeight: 1.8, color: '#37352f' }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                          {item.ai_summary}
                        </ReactMarkdown>
                      </div>
                    </Card>
                  )}
                </div>
              </List.Item>
            )}
          />
        ) : (
          <div style={{ textAlign: 'center', padding: '24px 0', color: '#bbb8b1' }}>
            <FileOutlined style={{ fontSize: 32, marginBottom: 8 }} />
            <div>暂无附件，点击上方按钮上传</div>
          </div>
        )}

        {/* Comments */}
        <Divider style={{ margin: '32px 0 20px', borderColor: '#ede9e4' }} />
        <Title level={4} style={{ marginBottom: 16, color: '#1a1a1a' }}>
          <MessageOutlined style={{ color: '#5645d4' }} /> 评论 ({article.comments.length})
        </Title>

        <List
          dataSource={article.comments}
          locale={{ emptyText: '暂无评论' }}
          renderItem={comment => (
            <List.Item
              style={{ borderBottom: '1px solid #f0eeec', padding: '12px 0' }}
              actions={[
                <Button key="delete" type="text" danger icon={<DeleteOutlined />} onClick={() => handleDeleteComment(comment.id)} />
              ]}
            >
              <List.Item.Meta
                avatar={<Avatar style={{ background: '#5645d4' }}>{comment.author?.[0] || '匿'}</Avatar>}
                title={<Text strong>{comment.author || '匿名用户'}</Text>}
                description={
                  <div>
                    <div style={{ margin: '6px 0', color: '#37352f' }}>{comment.content}</div>
                    <Text type="secondary" style={{ fontSize: 12 }}>{new Date(comment.created_at).toLocaleString('zh-CN')}</Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />

        <Divider style={{ margin: '24px 0 16px', borderColor: '#ede9e4' }} />

        <Form form={commentForm} onFinish={handleComment}>
          <Form.Item name="content" rules={[{ required: true, message: '请输入评论内容' }]}>
            <Input.TextArea rows={3} placeholder="分享你的想法..." style={{ borderRadius: 8 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting} style={{ borderRadius: 6, background: '#5645d4' }}>
              提交评论
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
