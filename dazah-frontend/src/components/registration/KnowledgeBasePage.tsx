'use client'

import { useMemo, useState, useTransition } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'

import {
  createKnowledgeArticle,
  createKnowledgeCategory,
  deleteKnowledgeArticle,
  deleteKnowledgeCategory,
  extractArticleFromFile,
  updateKnowledgeArticle,
  updateKnowledgeCategory,
  uploadKnowledgeAttachment,
} from '@/actions/registration'
import type {

  KnowledgeArticleCreate,
  KnowledgeArticleListItem,
  KnowledgeArticleUpdate,
  KnowledgeCategory,
  KnowledgeCategoryCreate,
  KnowledgeCategoryUpdate,
  KnowledgeOverview,
} from '@/types/registration'

interface KnowledgeBasePageProps {
  articles: KnowledgeArticleListItem[]
  categories: KnowledgeCategory[]
  overview: KnowledgeOverview
}

type ArticleFormMode = 'create' | 'edit'
type CategoryFormMode = 'create' | 'edit'

export default function KnowledgeBasePage({
  articles,
  categories,
  overview,
}: KnowledgeBasePageProps) {
  const router = useRouter()
  const { message } = App.useApp()

  // Article state
  const [articleForm] = Form.useForm<KnowledgeArticleCreate>()
  const [keyword, setKeyword] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>()
  const [publishedFilter, setPublishedFilter] = useState<boolean>()
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null)
  const [editingArticle, setEditingArticle] = useState<KnowledgeArticleListItem | null>(null)
  const [articleModalOpen, setArticleModalOpen] = useState(false)
  const [articleFormMode, setArticleFormMode] = useState<ArticleFormMode>('create')
  const [articlePending, startArticleTransition] = useTransition()
  const [extracting, setExtracting] = useState(false)
  const [pendingFile, setPendingFile] = useState<{ base64: string; file_name: string; content_type: string } | null>(null)

  // Category state
  const [categoryForm] = Form.useForm<KnowledgeCategoryCreate>()
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)
  const [editingCategory, setEditingCategory] = useState<KnowledgeCategory | null>(null)
  const [categoryModalOpen, setCategoryModalOpen] = useState(false)
  const [categoryFormMode, setCategoryFormMode] = useState<CategoryFormMode>('create')
  const [categoryPending, startCategoryTransition] = useTransition()

  const filteredArticles = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    return articles.filter((article) => {
      if (categoryFilter && article.category_id !== categoryFilter) return false
      if (publishedFilter !== undefined && article.is_published !== publishedFilter) return false
      if (!normalizedKeyword) return true
      return (
        article.title.toLowerCase().includes(normalizedKeyword) ||
        article.tags?.toLowerCase().includes(normalizedKeyword) ||
        article.country?.toLowerCase().includes(normalizedKeyword) ||
        article.product?.toLowerCase().includes(normalizedKeyword)
      )
    })
  }, [articles, keyword, categoryFilter, publishedFilter])

  const selectedArticle = useMemo(
    () => filteredArticles.find((a) => a.id === selectedArticleId) || null,
    [filteredArticles, selectedArticleId]
  )

  const articleColumns: ColumnsType<KnowledgeArticleListItem> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 240,
      ellipsis: true,
      render: (value: string, record: KnowledgeArticleListItem) => (
        <a onClick={() => router.push(`/registration/knowledge/${record.id}`)} style={{ cursor: 'pointer' }}>
          {value}
        </a>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category_name',
      key: 'category_name',
      width: 120,
      align: 'center',
      render: (value: string | null) => value || '—',
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 160,
      render: (value: string | null) =>
        value
          ? value.split(',').map((tag) => (
              <Tag key={tag} style={{ marginInlineEnd: 4 }}>
                {tag.trim()}
              </Tag>
            ))
          : '—',
    },
    {
      title: '国家',
      dataIndex: 'country',
      key: 'country',
      width: 90,
      align: 'center',
      render: (value: string | null) => value || '—',
    },
    {
      title: '产品',
      dataIndex: 'product',
      key: 'product',
      width: 120,
      ellipsis: true,
      render: (value: string | null) => value || '—',
    },
    {
      title: '状态',
      dataIndex: 'is_published',
      key: 'is_published',
      width: 80,
      align: 'center',
      render: (value: boolean) => (
        <Tag color={value ? 'green' : 'default'}>{value ? '已发布' : '草稿'}</Tag>
      ),
    },
    {
      title: '作者',
      dataIndex: 'author',
      key: 'author',
      width: 100,
      align: 'center',
      render: (value: string | null) => value || '—',
    },
    {
      title: '浏览',
      dataIndex: 'view_count',
      key: 'view_count',
      width: 70,
      align: 'center',
    },
    {
      title: '来源',
      dataIndex: 'source_url',
      key: 'source_url',
      width: 70,
      align: 'center',
      render: (value: string | null) => value ? <a href={value} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-primary)' }}>链接</a> : '-',
    },
  ]

  const categoryColumns: ColumnsType<KnowledgeCategory> = [
    {
      title: '分类名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (value: string | null) => value || '—',
    },
    {
      title: '文章数',
      dataIndex: 'article_count',
      key: 'article_count',
      width: 80,
      align: 'center',
    },
    {
      title: '排序',
      dataIndex: 'sort_order',
      key: 'sort_order',
      width: 70,
      align: 'center',
    },
  ]

  // Article handlers
  function openCreateArticleModal() {
    setArticleFormMode('create')
    setEditingArticle(null)
    articleForm.resetFields()
    articleForm.setFieldsValue({ is_published: false })
    setArticleModalOpen(true)
  }

  function openEditArticleModal() {
    if (!selectedArticle) {
      message.warning('请先选择一篇文章')
      return
    }
    setArticleFormMode('edit')
    setEditingArticle(selectedArticle)
    articleForm.setFieldsValue({
      title: selectedArticle.title,
      category_id: selectedArticle.category_id,
      tags: selectedArticle.tags || undefined,
      country: selectedArticle.country || undefined,
      product: selectedArticle.product || undefined,
      is_published: selectedArticle.is_published,
      author: selectedArticle.author || undefined,
      source_url: selectedArticle.source_url || undefined,
    })
    setArticleModalOpen(true)
  }

  async function handleAiExtract(file: File) {
    setExtracting(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const data = (await extractArticleFromFile(formData)) as {
        title?: string
        content?: string
        tags?: string
        country?: string
        file_base64: string
        file_name: string
        content_type: string
      } | null
      if (data) {
        articleForm.setFieldsValue({
          title: data.title || '',
          content: data.content || '',
          tags: data.tags || '',
          country: data.country || '',
        })
        // 存储文件信息，保存文章时一起上传附件
        setPendingFile({
          base64: data.file_base64,
          file_name: data.file_name,
          content_type: data.content_type,
        })
        message.success('AI提取成功，已自动填充表单，保存后将自动上传附件')
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI提取失败')
    } finally {
      setExtracting(false)
    }
    return false
  }

  function handleDeleteArticle() {
    if (!selectedArticle) {
      message.warning('请先选择一篇文章')
      return
    }
    startArticleTransition(async () => {
      try {
        await deleteKnowledgeArticle(selectedArticle.id)
        message.success('文章已删除')
        setSelectedArticleId(null)
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    })
  }

  async function handleArticleSubmit(values: KnowledgeArticleCreate) {
    startArticleTransition(async () => {
      try {
        let articleId: string | null = null
        if (articleFormMode === 'edit' && editingArticle) {
          const updateData: KnowledgeArticleUpdate = { ...values }
          await updateKnowledgeArticle(editingArticle.id, updateData)
          articleId = editingArticle.id
          message.success('文章已更新')
        } else {
          const result = await createKnowledgeArticle(values)
          articleId = result?.id || null
          message.success('文章已新增')
          if (!articleId && pendingFile) {
            message.warning('未获取到新文章 ID，AI 提取的附件未上传，请手动上传')
          }
        }

        // 如果有待上传的附件（AI提取的文件），自动上传
        if (pendingFile && articleId) {
          try {
            const binary = atob(pendingFile.base64)
            const bytes = new Uint8Array(binary.length)
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
            const blob = new Blob([bytes], { type: pendingFile.content_type })
            const file = new File([blob], pendingFile.file_name, { type: pendingFile.content_type })
            const formData = new FormData()
            formData.append('file', file)
            await uploadKnowledgeAttachment(articleId, formData)
            message.success('附件已自动上传')
          } catch (e) {
            console.error('附件上传失败:', e)
            message.warning('文章已保存，但 AI 提取的附件自动上传失败，请手动上传')
          }
        }

        setPendingFile(null)
        setArticleModalOpen(false)
        articleForm.resetFields()
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '保存失败')
      }
    })
  }

  // Category handlers
  function openCreateCategoryModal() {
    setCategoryFormMode('create')
    setEditingCategory(null)
    categoryForm.resetFields()
    categoryForm.setFieldsValue({ sort_order: 0 })
    setCategoryModalOpen(true)
  }

  function openEditCategoryModal() {
    if (!selectedCategoryId) {
      message.warning('请先选择一个分类')
      return
    }
    const category = categories.find((c) => c.id === selectedCategoryId)
    if (!category) return
    setCategoryFormMode('edit')
    setEditingCategory(category)
    categoryForm.setFieldsValue({
      name: category.name,
      description: category.description || undefined,
      sort_order: category.sort_order,
    })
    setCategoryModalOpen(true)
  }

  function handleDeleteCategory() {
    if (!selectedCategoryId) {
      message.warning('请先选择一个分类')
      return
    }
    startCategoryTransition(async () => {
      try {
        await deleteKnowledgeCategory(selectedCategoryId)
        message.success('分类已删除')
        setSelectedCategoryId(null)
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    })
  }

  async function handleCategorySubmit(values: KnowledgeCategoryCreate) {
    startCategoryTransition(async () => {
      try {
        if (categoryFormMode === 'edit' && editingCategory) {
          const updateData: KnowledgeCategoryUpdate = { ...values }
          await updateKnowledgeCategory(editingCategory.id, updateData)
          message.success('分类已更新')
        } else {
          await createKnowledgeCategory(values)
          message.success('分类已新增')
        }
        setCategoryModalOpen(false)
        categoryForm.resetFields()
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '保存失败')
      }
    })
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={3} style={{ marginBottom: 0 }}>
        注册知识库
      </Typography.Title>

      {/* 统计卡片 */}
      <Card size="small">
        <Space wrap size={24}>
          <div>
            <Typography.Text type="secondary">分类数</Typography.Text>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{overview.total_categories}</div>
          </div>
          <div>
            <Typography.Text type="secondary">文章总数</Typography.Text>
            <div style={{ fontSize: 20, fontWeight: 600 }}>{overview.total_articles}</div>
          </div>
          <div>
            <Typography.Text type="secondary">已发布</Typography.Text>
            <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--color-success, #1aae39)' }}>{overview.published_articles}</div>
          </div>
          <div>
            <Typography.Text type="secondary">草稿</Typography.Text>
            <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--color-warning, #dd5b00)' }}>{overview.draft_articles}</div>
          </div>
        </Space>
      </Card>

      {/* 分类管理 */}
      <Card
        size="small"
        title="分类管理"
        extra={
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreateCategoryModal}>
              新增分类
            </Button>
            <Button icon={<EditOutlined />} disabled={!selectedCategoryId} onClick={openEditCategoryModal}>
              编辑分类
            </Button>
            <Popconfirm
              title="确认删除选中的分类吗？"
              okText="删除"
              cancelText="取消"
              onConfirm={handleDeleteCategory}
              disabled={!selectedCategoryId}
            >
              <Button danger icon={<DeleteOutlined />} disabled={!selectedCategoryId}>
                删除分类
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        <Table<KnowledgeCategory>
          rowKey="id"
          columns={categoryColumns}
          dataSource={categories}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedCategoryId ? [selectedCategoryId] : [],
            onChange: (keys) => setSelectedCategoryId((keys[0] as string) || null),
          }}
          pagination={false}
          size="small"
        />
      </Card>

      {/* 文章管理 */}
      <Card
        size="small"
        title="文章管理"
        extra={
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreateArticleModal}>
              新增文章
            </Button>
            <Button icon={<EditOutlined />} disabled={!selectedArticle} onClick={openEditArticleModal}>
              编辑文章
            </Button>
            <Popconfirm
              title="确认删除选中的文章吗？"
              okText="删除"
              cancelText="取消"
              onConfirm={handleDeleteArticle}
              disabled={!selectedArticle}
            >
              <Button danger icon={<DeleteOutlined />} disabled={!selectedArticle}>
                删除文章
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Space wrap size={12}>
            <Select
              allowClear
              placeholder="按分类筛选"
              value={categoryFilter}
              onChange={(value) => setCategoryFilter(value)}
              options={categories.map((c) => ({ label: c.name, value: c.id }))}
              style={{ width: 180 }}
            />
            <Select
              allowClear
              placeholder="按状态筛选"
              value={publishedFilter}
              onChange={(value) => setPublishedFilter(value)}
              options={[
                { label: '已发布', value: true },
                { label: '草稿', value: false },
              ]}
              style={{ width: 140 }}
            />
            <Input
              allowClear
              placeholder="搜索标题、标签、国家等"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              style={{ width: 280 }}
            />
          </Space>

          <Table<KnowledgeArticleListItem>
            rowKey="id"
            columns={articleColumns}
            dataSource={filteredArticles}
            rowSelection={{
              type: 'radio',
              selectedRowKeys: selectedArticleId ? [selectedArticleId] : [],
              onChange: (keys) => setSelectedArticleId((keys[0] as string) || null),
            }}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            scroll={{ x: 'max-content' }}
          />
        </Space>
      </Card>

      {/* Article Modal */}
      <Modal
        destroyOnHidden
        confirmLoading={articlePending}
        open={articleModalOpen}
        width={700}
        title={articleFormMode === 'create' ? '新增文章' : '编辑文章'}
        okText="保存"
        cancelText="取消"
        onCancel={() => {
          // 取消弹窗时清掉 AI 提取的待上传附件，避免残留文件被上传到下一篇文章
          if (pendingFile) {
            setPendingFile(null)
            message.info('已取消：AI 提取的附件不会上传')
          }
          setArticleModalOpen(false)
        }}
        onOk={() => articleForm.submit()}
      >
        <Form<KnowledgeArticleCreate> form={articleForm} layout="vertical" onFinish={handleArticleSubmit}>
          {articleFormMode === 'create' && (
            <Form.Item label="AI 智能提取">
              <Upload showUploadList={false} beforeUpload={handleAiExtract} accept=".txt,.md,.pdf,.doc,.docx">
                <Button icon={<ThunderboltOutlined />} loading={extracting} style={{ borderRadius: 6 }}>
                  上传文件自动提取内容
                </Button>
              </Upload>
              <div style={{ fontSize: 12, color: 'var(--color-steel)', marginTop: 4 }}>支持 txt/md/pdf/doc/docx 格式，AI 将自动提取标题、内容、标签等信息</div>
            </Form.Item>
          )}
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="category_id" label="分类" rules={[{ required: true, message: '请选择分类' }]}>
            <Select options={categories.map((c) => ({ label: c.name, value: c.id }))} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '请输入内容' }]}>
            <Input.TextArea rows={8} />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="tags" label="标签" style={{ flex: 1, marginBottom: 0 }}>
              <Input placeholder="逗号分隔" />
            </Form.Item>
            <Form.Item name="country" label="适用国家" style={{ flex: 1, marginBottom: 0 }}>
              <Input />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="product" label="关联产品" style={{ flex: 1, marginBottom: 0 }}>
              <Input />
            </Form.Item>
            <Form.Item name="author" label="作者" style={{ flex: 1, marginBottom: 0 }}>
              <Input />
            </Form.Item>
          </div>
          <Form.Item name="source_url" label="信息来源链接">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="is_published" label="是否发布" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Category Modal */}
      <Modal
        destroyOnHidden
        confirmLoading={categoryPending}
        open={categoryModalOpen}
        width={500}
        title={categoryFormMode === 'create' ? '新增分类' : '编辑分类'}
        okText="保存"
        cancelText="取消"
        onCancel={() => setCategoryModalOpen(false)}
        onOk={() => categoryForm.submit()}
      >
        <Form<KnowledgeCategoryCreate> form={categoryForm} layout="vertical" onFinish={handleCategorySubmit}>
          <Form.Item name="name" label="分类名称" rules={[{ required: true, message: '请输入分类名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="sort_order" label="排序序号">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
