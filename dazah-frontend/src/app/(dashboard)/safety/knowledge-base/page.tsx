'use client'

import { useEffect, useState } from 'react'
import {
  Table,
  Button,
  Space,
  Input,
  Select,
  Modal,
  Form,
  DatePicker,
  Tag,
  Card,
  Row,
  Col,
  Typography,
  Descriptions,
  App,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Upload } from 'antd'
import { PaperClipOutlined, UploadOutlined } from '@ant-design/icons'
import {
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  CloudDownloadOutlined,
  FilePdfOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import { useSafetyStore } from '@/stores/safety'
import {
  uploadKnowledgeAttachments,
  deleteKnowledgeAttachment,
  getKnowledgeArticles,
  getKnowledgeArticle,
  createKnowledgeArticle,
  updateKnowledgeArticle,
  deleteKnowledgeArticle,
  syncSafetyKnowledge,
} from '@/actions/safety'
import type {
  SafetyKnowledgeArticle,
  SafetyKnowledgeArticleFormData,
} from '@/types/safety'
import dayjs from 'dayjs'

const { Text } = Typography

const REGULATION_STATUS_OPTIONS = [
  { value: '现行有效', label: '现行有效' },
  { value: '已废止', label: '已废止' },
  { value: '已失效', label: '已失效' },
  { value: '部分有效', label: '部分有效' },
]

function formatDate(value?: string | null): string {
  return value ? dayjs(value).format('YYYY-MM-DD') : '-'
}

function regulationStatusColor(status?: string | null): string {
  if (status === '现行有效') return 'green'
  if (status === '已废止' || status === '已失效') return 'default'
  return 'blue'
}

function attachmentUrl(recordId: string, fileToken: string, kind: 'content' | 'preview'): string {
  return `/api/v1/safety/knowledge-articles/feishu/records/${recordId}/attachments/${fileToken}/${kind}`
}

function openAttachment(recordId: string, fileToken: string, kind: 'content' | 'preview'): void {
  window.open(attachmentUrl(recordId, fileToken, kind), '_blank', 'noopener')
}


function localAttachmentUrl(articleId: string, token: string, kind: 'content' | 'preview'): string {
  return `/api/v1/safety/knowledge-articles/${articleId}/attachments/${token}/${kind}`
}

function openLocalAttachment(articleId: string, token: string, kind: 'content' | 'preview'): void {
  window.open(localAttachmentUrl(articleId, token, kind), '_blank', 'noopener')
}

function formatSize(bytes?: number): string {
  if (!bytes) return ''
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`
  return `${Math.round(bytes / 1024)}KB`
}

function AttachmentActions({ article }: { article: SafetyKnowledgeArticle }) {
  const feishuItems = article.feishu_attachments ?? []
  const localItems = article.local_attachments ?? []
  if (!feishuItems.length && !localItems.length) return <Text type="secondary">-</Text>
  return (
    <Space size={4} wrap>
      {feishuItems.map((item) => (
        <Space key={item.file_token} size={0}>
          <Button
            type="link"
            size="small"
            icon={<FilePdfOutlined />}
            title={item.name}
            disabled={!article.feishu_record_id}
            onClick={() =>
              article.feishu_record_id &&
              openAttachment(article.feishu_record_id, item.file_token, 'preview')
            }
          >
            预览
          </Button>
          <Button
            type="link"
            size="small"
            disabled={!article.feishu_record_id}
            onClick={() =>
              article.feishu_record_id &&
              openAttachment(article.feishu_record_id, item.file_token, 'content')
            }
          >
            下载
          </Button>
        </Space>
      ))}
      {localItems.map((item) => (
        <Space key={item.token} size={0}>
          <Button
            type="link"
            size="small"
            icon={<PaperClipOutlined />}
            title={item.name}
            onClick={() => openLocalAttachment(article.id, item.token, 'preview')}
          >
            预览
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => openLocalAttachment(article.id, item.token, 'content')}
          >
            下载
          </Button>
        </Space>
      ))}
    </Space>
  )
}

export default function KnowledgeBasePage() {
  const { message, modal } = App.useApp()
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [detailVisible, setDetailVisible] = useState(false)
  const [editingRecord, setEditingRecord] = useState<SafetyKnowledgeArticle | null>(null)
  const [detailRecord, setDetailRecord] = useState<SafetyKnowledgeArticle | null>(null)
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [uploadingCount, setUploadingCount] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [regulationStatusFilter, setRegulationStatusFilter] = useState<string | undefined>()

  const {
    articles,
    articleTotal,
    articleQueryParams,
    setArticles,
    setArticleTotal,
    setArticleQueryParams,
    addArticle,
    updateArticle: updateArticleInStore,
    removeArticle,
  } = useSafetyStore()

  const loadData = async () => {
    setLoading(true)
    try {
      const response = await getKnowledgeArticles({
        ...articleQueryParams,
        regulation_status: regulationStatusFilter,
        keyword: searchText || undefined,
      })
      if (response.code === 200) {
        setArticles(response.data)
        setArticleTotal(response.meta?.total || 0)
      }
    } catch {
      message.error('加载知识库列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // 关键词仅在点击查询时生效，避免输入过程触发请求（loadData 依赖刻意省略）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleQueryParams.page, articleQueryParams.page_size, regulationStatusFilter])

  const handleSearch = () => {
    setArticleQueryParams({ page: 1 })
    loadData()
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const response = await syncSafetyKnowledge()
      if (response.code === 200 && response.data) {
        const d = response.data as Record<string, number>
        message.success(
          `同步完成：新增 ${d.created ?? 0} 条，更新 ${d.updated ?? 0} 条，移除 ${d.removed ?? 0} 条` +
            (d.failed ? `，失败 ${d.failed} 条` : '')
        )
        setArticleQueryParams({ page: 1 })
        await loadData()
      } else {
        message.error(response.message || '同步失败')
      }
    } finally {
      setSyncing(false)
    }
  }

  const handleAdd = () => {
    setEditingRecord(null)
    form.resetFields()
    setPendingFiles([])
    setModalVisible(true)
  }

  const handleEdit = (record: SafetyKnowledgeArticle) => {
    setEditingRecord(record)
    editForm.setFieldsValue({
      ...record,
      promulgation_date: record.promulgation_date ? dayjs(record.promulgation_date) : undefined,
      implement_date: record.implement_date ? dayjs(record.implement_date) : undefined,
    })
    setModalVisible(true)
  }

  const handleRemoveLocalAttachment = async (token: string) => {
    if (!editingRecord) return
    const response = await deleteKnowledgeAttachment(editingRecord.id, token)
    if (response.code === 200) {
      message.success('附件已删除')
      updateArticleInStore(editingRecord.id, response.data)
      setEditingRecord(response.data)
    } else {
      message.error(response.message || '删除附件失败')
    }
  }

  const handleEditUpload = async (file: File) => {
    if (!editingRecord) return false
    setUploadingCount((n) => n + 1)
    try {
      const response = await uploadKnowledgeAttachments(editingRecord.id, [file])
      if (response.code === 200 && response.data) {
        message.success(`附件已上传：${file.name}`)
        updateArticleInStore(editingRecord.id, response.data)
        setEditingRecord(response.data)
      } else {
        message.error(response.message || '上传附件失败')
      }
    } finally {
      setUploadingCount((n) => n - 1)
    }
    return false
  }

  const handleViewDetail = async (record: SafetyKnowledgeArticle) => {
    try {
      const response = await getKnowledgeArticle(record.id)
      if (response.code === 200) {
        setDetailRecord(response.data)
        setDetailVisible(true)
        updateArticleInStore(record.id, response.data)
      }
    } catch {
      message.error('获取详情失败')
    }
  }

  const handleDelete = (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除该知识文档吗？（飞书镜像记录下次同步会恢复）',
      onOk: async () => {
        const response = await deleteKnowledgeArticle(id)
        if (response.code === 200) { message.success('删除成功'); removeArticle(id) }
        else { message.error(response.message || '删除失败') }
      },
    })
  }

  const handleSubmit = async () => {
    try {
      const values = editingRecord ? await editForm.validateFields() : await form.validateFields()
      const formattedValues: SafetyKnowledgeArticleFormData = {
        ...values,
        promulgation_date: values.promulgation_date ? values.promulgation_date.toISOString() : undefined,
        implement_date: values.implement_date ? values.implement_date.toISOString() : undefined,
      }

      if (editingRecord) {
        const response = await updateKnowledgeArticle(editingRecord.id, formattedValues)
        if (response.code === 200) { message.success('更新成功'); updateArticleInStore(editingRecord.id, response.data); setModalVisible(false) }
        else { message.error(response.message || '更新失败') }
      } else {
        const response = await createKnowledgeArticle(formattedValues as SafetyKnowledgeArticleFormData)
        if (response.code === 200) {
          if (pendingFiles.length) {
            const uploadRes = await uploadKnowledgeAttachments(response.data.id, pendingFiles)
            if (uploadRes.code === 200 && uploadRes.data) {
              message.success(`创建成功，已上传 ${pendingFiles.length} 个附件`)
              addArticle(uploadRes.data)
            } else {
              message.warning(`文档已创建，但附件上传失败：${uploadRes.message || '未知错误'}`)
              addArticle(response.data)
            }
          } else {
            message.success('创建成功')
            addArticle(response.data)
          }
          setModalVisible(false); form.resetFields(); setPendingFiles([])
        } else {
          message.error(response.message || '创建失败')
        }
      }
    } catch { console.error('表单验证失败') }
  }

  const columns: ColumnsType<SafetyKnowledgeArticle> = [
    { title: '编号', dataIndex: 'article_no', key: 'article_no', width: 80 },
    {
      title: '法律法规及标准名称',
      dataIndex: 'title',
      key: 'title',
      width: 260,
      ellipsis: true,
    },
    {
      title: '法规类别',
      dataIndex: 'regulation_category',
      key: 'regulation_category',
      width: 100,
      render: (c: string | null) => (c ? <Tag>{c}</Tag> : '-'),
    },
    { title: '颁布机关', dataIndex: 'source', key: 'source', width: 130, ellipsis: true },
    {
      title: '颁布/修订',
      dataIndex: 'promulgation_date',
      key: 'promulgation_date',
      width: 105,
      render: (d: string | null) => formatDate(d),
    },
    {
      title: '实施日期',
      dataIndex: 'implement_date',
      key: 'implement_date',
      width: 105,
      render: (d: string | null) => formatDate(d),
    },
    {
      title: '法规状态',
      dataIndex: 'regulation_status',
      key: 'regulation_status',
      width: 100,
      render: (s: string | null) =>
        s ? <Tag color={regulationStatusColor(s)}>{s}</Tag> : '-',
    },
    {
      title: '附件',
      key: 'attachments',
      width: 130,
      render: (_, record) => <AttachmentActions article={record} />,
    },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>查看</Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)}>删除</Button>
        </Space>
      ),
    },
  ]

  const formContent = (
    <>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="article_no" label="法规编号">
            <Input placeholder="如 001" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="regulation_category" label="法规类别">
            <Input placeholder="如 安全类" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="regulation_status" label="法规状态">
            <Select options={REGULATION_STATUS_OPTIONS} allowClear placeholder="如 现行有效" />
          </Form.Item>
        </Col>
      </Row>
      <Form.Item name="title" label="法律法规及标准名称" rules={[{ required: true }]}>
        <Input placeholder="请输入名称" />
      </Form.Item>
      <Row gutter={16}>
        <Col span={8}>
          <Form.Item name="source" label="颁布机关">
            <Input placeholder="如 全国人大" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="promulgation_date" label="颁布/修订日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="implement_date" label="实施日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
      <Form.Item name="regulation_link" label="法规链接">
        <Input placeholder="https://..." />
      </Form.Item>
      <Form.Item name="summary" label="核心要点总结">
        <Input.TextArea rows={3} placeholder="请输入核心要点总结" />
      </Form.Item>
      <Form.Item name="notes" label="备注">
        <Input.TextArea rows={2} placeholder="请输入备注" />
      </Form.Item>
      <Form.Item label="附件">
        {editingRecord?.feishu_record_id ? (
          <Text type="secondary">
            该文档来自飞书法规库镜像，附件请在多维表格「附件」列中维护
            （当前 {editingRecord.feishu_attachments?.length ?? 0} 个）。
          </Text>
        ) : editingRecord ? (
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {(editingRecord.local_attachments ?? []).map((item) => (
              <Space key={item.token} size={8}>
                <PaperClipOutlined />
                <Text ellipsis style={{ maxWidth: 320 }} title={item.name}>
                  {item.name}
                </Text>
                <Text type="secondary">{formatSize(item.size)}</Text>
                <Button
                  type="link"
                  size="small"
                  danger
                  onClick={() => handleRemoveLocalAttachment(item.token)}
                >
                  删除
                </Button>
              </Space>
            ))}
            <Upload
              multiple
              showUploadList={false}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt,.md"
              beforeUpload={(file) => {
                void handleEditUpload(file)
                return false
              }}
            >
              <Button icon={<UploadOutlined />} loading={uploadingCount > 0}>
                上传附件（PDF/Office/图片/文本，单个 ≤ 20MB）
              </Button>
            </Upload>
          </Space>
        ) : (
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {pendingFiles.length === 0 ? null : (
              <>
                {pendingFiles.map((file, index) => (
                  <Space key={`${file.name}-${index}`} size={8}>
                    <PaperClipOutlined />
                    <Text ellipsis style={{ maxWidth: 320 }} title={file.name}>
                      {file.name}
                    </Text>
                    <Text type="secondary">{formatSize(file.size)}</Text>
                    <Button
                      type="link"
                      size="small"
                      danger
                      onClick={() =>
                        setPendingFiles((files) => files.filter((_, i) => i !== index))
                      }
                    >
                      移除
                    </Button>
                  </Space>
                ))}
              </>
            )}
            <Upload
              multiple
              showUploadList={false}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt,.md"
              beforeUpload={(file) => {
                setPendingFiles((files) => [...files, file])
                return false
              }}
            >
              <Button icon={<UploadOutlined />}>选择附件（保存文档后自动上传）</Button>
            </Upload>
          </Space>
        )}
      </Form.Item>
    </>
  )

  return (
    <div className="p-6">
      <Card
        title="安全知识库（EHS 法规数据库）"
        extra={
          <Space>
            <Button
              icon={<CloudDownloadOutlined />}
              onClick={() => void handleSync()}
              loading={syncing}
            >
              同步飞书法规库
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
              新建文档
            </Button>
          </Space>
        }
      >
        <Row gutter={16} className="mb-4">
          <Col span={12}>
            <Input placeholder="搜索编号/名称/机关/要点/备注" prefix={<SearchOutlined />}
              value={searchText} onChange={e => setSearchText(e.target.value)} onPressEnter={handleSearch} />
          </Col>
          <Col span={8}>
            <Select placeholder="法规状态" allowClear value={regulationStatusFilter}
              onChange={v => { setRegulationStatusFilter(v); setArticleQueryParams({ page: 1 }) }}
              style={{ width: '100%' }}
              options={REGULATION_STATUS_OPTIONS} />
          </Col>
          <Col span={4}>
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
          </Col>
        </Row>

        <Table columns={columns} dataSource={articles} rowKey="id" loading={loading} scroll={{ x: 1400 }}
          pagination={{
            current: articleQueryParams.page, pageSize: articleQueryParams.page_size, total: articleTotal,
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
            onChange: (page, pageSize) => setArticleQueryParams({ page, page_size: pageSize }),
          }} />
      </Card>

      <Modal title={editingRecord ? '编辑文档' : '新建文档'} open={modalVisible}
        onOk={handleSubmit} onCancel={() => setModalVisible(false)} width={860} okText="确认" cancelText="取消">
        <Form form={editingRecord ? editForm : form} layout="vertical">
          {formContent}
        </Form>
      </Modal>

      <Modal title="法规详情" open={detailVisible} width={860}
        onCancel={() => { setDetailVisible(false); setDetailRecord(null) }}
        footer={<Button onClick={() => { setDetailVisible(false); setDetailRecord(null) }}>关闭</Button>}>
        {detailRecord && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="编号">{detailRecord.article_no || '-'}</Descriptions.Item>
            <Descriptions.Item label="法规类别">
              {detailRecord.regulation_category || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="名称" span={2}>{detailRecord.title}</Descriptions.Item>
            <Descriptions.Item label="颁布机关">{detailRecord.source || '-'}</Descriptions.Item>
            <Descriptions.Item label="法规状态">
              {detailRecord.regulation_status
                ? <Tag color={regulationStatusColor(detailRecord.regulation_status)}>{detailRecord.regulation_status}</Tag>
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="颁布/修订日期">{formatDate(detailRecord.promulgation_date)}</Descriptions.Item>
            <Descriptions.Item label="实施日期">{formatDate(detailRecord.implement_date)}</Descriptions.Item>
            <Descriptions.Item label="法规链接" span={2}>
              {detailRecord.regulation_link ? (
                <Button type="link" size="small" icon={<LinkOutlined />} href={detailRecord.regulation_link} target="_blank" rel="noopener noreferrer">
                  打开原文链接
                </Button>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="核心要点总结" span={2}>
              <div className="whitespace-pre-wrap">{detailRecord.summary || '-'}</div>
            </Descriptions.Item>
            <Descriptions.Item label="附件" span={2}>
              <AttachmentActions article={detailRecord} />
            </Descriptions.Item>
            <Descriptions.Item label="备注" span={2}>
              <div className="whitespace-pre-wrap">{detailRecord.notes || '-'}</div>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
