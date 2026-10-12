'use client'

import { useState, useEffect, useCallback } from 'react'
import { App,
  Modal,
  Input,
  Checkbox,
  List,
  Tag,
  Typography,
  Space,
  Empty,
  Spin
} from 'antd'
import { SearchOutlined, FileTextOutlined } from '@ant-design/icons'
import { getKnowledgeArticles } from '@/actions/safety'
import type { SafetyKnowledgeArticle } from '@/types/safety'

const { Text } = Typography

interface Props {
  open: boolean
  onClose: () => void
  onSelect: (articles: SafetyKnowledgeArticle[]) => void
  /** 已选中的知识库文章 ID 列表（避免重复选择） */
  excludeIds?: string[]
}

const PAGE_SIZE = 50

export default function KnowledgeBasePicker({ open, onClose, onSelect, excludeIds = [] }: Props) {
  const { message } = App.useApp()
  const [articles, setArticles] = useState<SafetyKnowledgeArticle[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const fetchArticles = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getKnowledgeArticles({
        page_size: PAGE_SIZE,
        keyword: keyword || undefined
      })
      if (res.code === 200 && res.data) {
        setArticles(res.data.filter((a) => !excludeIds.includes(a.id)))
      }
    } catch {
      message.error('获取知识库文章失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, excludeIds])

  useEffect(() => {
    if (open) {
      fetchArticles()
    }
  }, [open, fetchArticles])

  // 重置状态
  useEffect(() => {
    if (!open) {
      setSelectedIds([])
      setKeyword('')
    }
  }, [open])

  const handleConfirm = () => {
    const selected = articles.filter((a) => selectedIds.includes(a.id))
    if (selected.length === 0) {
      message.warning('请至少选择一篇文章')
      return
    }
    onSelect(selected)
    onClose()
  }

  const toggleSelect = (id: string, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? [...prev, id] : prev.filter((i) => i !== id)
    )
  }

  return (
    <Modal
      title={
        <Space>
          <FileTextOutlined />
          <span>从知识库选择文章</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      onOk={handleConfirm}
      okText={`确认选择 (${selectedIds.length} 篇)`}
      cancelText="取消"
      width={680}
      styles={{
        body: { padding: '16px 24px', maxHeight: '60vh', overflow: 'auto' }
      }}
    >
      {/* ── 搜索 & 筛选 ── */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <Input
          prefix={<SearchOutlined style={{ color: '#bbb8b1' }} />}
          placeholder="搜索文章标题..."
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={fetchArticles}
          allowClear
          style={{ flex: 1, borderRadius: 8 }}
        />
      </div>

      {/* ── 文章列表 ── */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : articles.length === 0 ? (
        <Empty description="暂无可选的法规文档" />
      ) : (
        <List
          dataSource={articles}
          renderItem={(article) => {
            const isSelected = selectedIds.includes(article.id)
            return (
              <List.Item
                style={{
                  padding: '10px 12px',
                  borderRadius: 8,
                  marginBottom: 4,
                  background: isSelected ? '#f0edff' : '#fafaf9',
                  border: isSelected ? '1px solid #d5cfff' : '1px solid transparent',
                  cursor: 'pointer'
                }}
                onClick={() => toggleSelect(article.id, !isSelected)}
              >
                <Checkbox
                  checked={isSelected}
                  onChange={(e) => toggleSelect(article.id, e.target.checked)}
                  style={{ marginRight: 12 }}
                />
                <div style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, color: '#37352f' }}>{article.title}</Text>
                  <div style={{ marginTop: 4, display: 'flex', gap: 8, alignItems: 'center' }}>
                    {article.regulation_category && (
                      <Tag color="blue" style={{ borderRadius: 4, fontSize: 11 }}>
                        {article.regulation_category}
                      </Tag>
                    )}
                    {article.regulation_status && (
                      <Tag
                        color={article.regulation_status === '现行有效' ? 'green' : 'default'}
                        style={{ borderRadius: 4, fontSize: 11 }}
                      >
                        {article.regulation_status}
                      </Tag>
                    )}
                  </div>
                </div>
              </List.Item>
            )
          }}
        />
      )}
    </Modal>
  )
}
