'use client'

import { useCallback, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  Modal,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import Image from 'next/image'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import {
  fetchHistoricalDeviation,
  fetchHistoricalDeviations,
} from '@/lib/api/client/quality'
import {
  aiExtractHistoricalDeviation,
  batchImportHistoricalDeviations,
  createHistoricalDeviation,
  deleteHistoricalDeviation,
  deleteHistoricalDeviationAttachment,
  updateHistoricalDeviation,
  uploadHistoricalDeviationAttachment,
} from '@/actions/quality-deviation-workbench'
import type {
  HistoricalDeviationAttachment,
  HistoricalDeviationDetail,
  HistoricalDeviationListItem,
} from '@/types/quality'
import { TableEmptyState } from './TableEmptyState'
import { qualityTokens } from './themeTokens'

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

interface PreviewState {
  open: boolean
  url: string
  file_name: string
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 附件在线预览：word 附件展示标准 MD（保留表格/图片）；图片直接展示；PDF 内嵌 */
function AttachmentPreviewModal({ preview, onClose }: { preview: PreviewState | null; onClose: () => void }) {
  const [state, setState] = useState<{ text: string; blobUrl: string; contentType: string }>({
    text: '',
    blobUrl: '',
    contentType: '',
  })
  const [loading, setLoading] = useState(false)
  // happy-dom（vitest）下 blob: iframe 会抛 ERR_INVALID_URL 崩掉测试进程
  const isTestEnv = import.meta.env?.MODE === 'test'

  const { modal } = App.useApp()

  const load = useCallback(async () => {
    if (!preview) return
    setLoading(true)
    try {
      const res = await fetch(preview.url)
      if (!res.ok) throw new Error(`获取附件内容失败: ${res.status}`)
      const contentType = res.headers.get('content-type') || ''
      if (!contentType || contentType.includes('markdown') || contentType.startsWith('text/')) {
        setState({ text: await res.text(), blobUrl: '', contentType })
      } else {
        const blob = await res.blob()
        setState({ text: '', blobUrl: URL.createObjectURL(blob), contentType })
      }
    } catch (error) {
      modal.error({ title: '预览失败', content: error instanceof Error ? error.message : '无法读取附件内容' })
    } finally {
      setLoading(false)
    }
  }, [preview, modal])

  return (
    <Modal
      title={
        <span>
          <EyeOutlined className="mr-2" />
          附件预览 - {preview?.file_name || ''}
        </span>
      }
      open={!!preview && preview.open}
      onCancel={onClose}
      footer={null}
      width={900}
      destroyOnHidden
      afterOpenChange={(open) => {
        if (open) void load()
      }}
    >
      <Spin spinning={loading}>
        {state.blobUrl ? (
          state.contentType.includes('pdf') && !isTestEnv ? (
            <iframe src={state.blobUrl} title="PDF 预览" className="h-[68vh] w-full border-0" />
          ) : state.blobUrl.startsWith('blob:') && isTestEnv ? (
            <a href={state.blobUrl} download>
              当前测试环境不支持内嵌预览，点击下载查看
            </a>
          ) : (
            <Image src={state.blobUrl} alt="附件预览" width={1200} height={900} unoptimized className="h-auto max-w-full" />
          )
        ) : (
          <div className="whitespace-pre-wrap break-words bg-gray-50 p-4 text-sm leading-relaxed">
            {state.text ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownPreviewComponents}>
                {state.text}
              </ReactMarkdown>
            ) : (
              '无预览内容'
            )}
          </div>
        )}
      </Spin>
    </Modal>
  )
}

interface EditDrawerState {
  open: boolean
  record: HistoricalDeviationDetail | null
  attachments: HistoricalDeviationAttachment[]
  // 新建模式下尚未落库的本地文件；保存时随记录一起上传
  pendingFiles: File[]
  aiExtracting: boolean
}

export function DeviationHistoryPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm()

  const [keyword, setKeyword] = useState('')
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [drawer, setDrawer] = useState<EditDrawerState>({
    open: false,
    record: null,
    attachments: [],
    pendingFiles: [],
    aiExtracting: false,
  })
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [batchImporting, setBatchImporting] = useState(false)

  const { data, isLoading, isError, error: loadError, refetch } = useQuery({
    queryKey: ['quality-deviation-history', page, pageSize, searchText],
    queryFn: () =>
      fetchHistoricalDeviations({ keyword: searchText || undefined, page, page_size: pageSize }),
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['quality-deviation-history'] })
  }, [queryClient])

  const openCreate = () => {
    // 新建先在弹窗内填写，点"确定"时才真正创建，避免遗留空记录
    form.resetFields()
    setDrawer({
      open: true,
      record: null,
      attachments: [],
      pendingFiles: [],
      aiExtracting: false,
    })
  }

  const openEdit = async (recordId: string) => {
    try {
      const detail = await fetchHistoricalDeviation(recordId)
      if (!detail) throw new Error('未找到记录')
      setDrawer({
        open: true,
        record: detail,
        attachments: detail.attachments || [],
        pendingFiles: [],
        aiExtracting: false,
      })
      form.setFieldsValue({
        deviation_event: detail.deviation_event || '',
        deviation_content: detail.deviation_content || '',
        direct_cause: detail.direct_cause || '',
        root_cause: detail.root_cause || '',
        investigation_conclusion: detail.investigation_conclusion || '',
        remark: detail.remark || '',
      })
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败')
    }
  }

  const closeDrawer = () => setDrawer((prev) => ({ ...prev, open: false }))

  const removePendingFile = (index: number) => {
    setDrawer((prev) => ({
      ...prev,
      pendingFiles: prev.pendingFiles.filter((_, i) => i !== index),
    }))
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    const payload = {
      deviation_event: values.deviation_event || null,
      deviation_content: values.deviation_content || null,
      direct_cause: values.direct_cause || null,
      root_cause: values.root_cause || null,
      investigation_conclusion: values.investigation_conclusion || null,
      remark: values.remark || null,
    }
    const record = drawer.record
    try {
      if (!record) {
        const created = await createHistoricalDeviation(payload)
        if (!created) throw new Error('创建失败')
        // 新建时把本地暂存的附件一并上传；单个失败不影响记录与其余附件
        let uploadFailed = 0
        for (const file of drawer.pendingFiles) {
          try {
            const formData = new FormData()
            formData.append('file', file)
            await uploadHistoricalDeviationAttachment(created.id, formData)
          } catch {
            uploadFailed += 1
          }
        }
        if (uploadFailed > 0) {
          message.warning(
            `记录已创建，但 ${uploadFailed} 个附件上传失败；可在列表"编辑"中重新上传`
          )
        } else {
          message.success('已创建')
        }
      } else {
        await updateHistoricalDeviation(record.id, payload)
        message.success('已保存')
      }
      invalidate()
      closeDrawer()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    }
  }

  const handleAiExtract = async () => {
    const record = drawer.record
    if (!record) {
      message.warning('请先点"确定"保存记录，上传附件后再用 AI 提取')
      return
    }
    setDrawer((prev) => ({ ...prev, aiExtracting: true }))
    try {
      const detail = await aiExtractHistoricalDeviation(record.id)
      if (!detail) throw new Error('AI 未返回结果')
      setDrawer((prev) => ({
        ...prev,
        record: detail,
        attachments: detail.attachments || [],
      }))
      form.setFieldsValue({
        deviation_event: detail.deviation_event || '',
        deviation_content: detail.deviation_content || '',
        direct_cause: detail.direct_cause || '',
        root_cause: detail.root_cause || '',
        investigation_conclusion: detail.investigation_conclusion || '',
      })
      message.success('AI 提取完成，请核对后保存')
      invalidate()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI 提取失败')
    } finally {
      setDrawer((prev) => ({ ...prev, aiExtracting: false }))
    }
  }

  const handleUpload = async (file: File) => {
    const record = drawer.record
    if (!record) {
      // 新建模式：先本地暂存，保存时随记录上传
      setDrawer((prev) => ({ ...prev, pendingFiles: [...prev.pendingFiles, file] }))
      return
    }
    const formData = new FormData()
    formData.append('file', file)
    try {
      const attachment = await uploadHistoricalDeviationAttachment(record.id, formData)
      if (!attachment) throw new Error('上传失败')
      setDrawer((prev) => ({ ...prev, attachments: [...prev.attachments, attachment] }))
      message.success('上传成功（Word 附件已自动转标准 MD）')
      invalidate()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败')
    }
  }

  const handleDeleteAttachment = async (attachmentId: string) => {
    const record = drawer.record
    if (!record) return
    modal.confirm({
      title: '删除附件',
      content: '确定删除该附件吗？',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          const detail = await deleteHistoricalDeviationAttachment(record.id, attachmentId)
          setDrawer((prev) => ({ ...prev, attachments: detail?.attachments || [] }))
          message.success('已删除')
          invalidate()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  const handleDelete = (recordId: string, code: string) => {
    modal.confirm({
      title: '删除历史偏差',
      content: `确定删除历史偏差「${code}」吗？删除后不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteHistoricalDeviation(recordId)
          message.success('已删除')
          invalidate()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  const handleBatchImport = async (files: File[]) => {
    if (files.length === 0) return
    if (files.length > 20) {
      message.warning('单次最多导入 20 个附件，请分批操作')
      return
    }
    setBatchImporting(true)
    try {
      const formData = new FormData()
      files.forEach((file) => formData.append('files', file))
      const result = await batchImportHistoricalDeviations(formData)
      if (!result) throw new Error('批量导入失败')
      const failed = (result.results || []).filter((r) => r.status !== 'succeeded')
      const failedNames = failed.slice(0, 3).map((r) => r.file_name).join('、')
      if (result.failed > 0) {
        message.warning(`共 ${result.total} 个，成功 ${result.succeeded}，失败 ${result.failed}${failedNames ? `（如：${failedNames}）` : ''}`)
      } else {
        message.success(`批量导入完成：成功 ${result.succeeded} 个`)
      }
      invalidate()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '批量导入失败')
    } finally {
      setBatchImporting(false)
    }
  }

  const columns: TableColumnsType<HistoricalDeviationListItem> = [
    {
      title: '序号',
      key: 'index',
      width: 60,
      render: (_, __, index) => (page - 1) * pageSize + index + 1,
    },
    {
      title: '编号',
      dataIndex: 'code',
      width: 150,
      render: (value: string) => (
        <Typography.Text strong>{value && value.startsWith('PC-') ? value : '-'}</Typography.Text>
      ),
    },
    {
      title: '偏差事件',
      dataIndex: 'deviation_event',
      width: 220,
      render: (value: string | null) => (
        <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{value || '-'}</span>
      ),
    },
    {
      title: '偏差内容',
      dataIndex: 'deviation_content',
      width: 280,
      render: (value: string | null) => (
        <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{value || '-'}</span>
      ),
    },
    {
      title: '调查结论',
      key: 'conclusion',
      width: 260,
      render: (_, record) => {
        const parts = [
          record.direct_cause && `直接原因：${record.direct_cause}`,
          record.root_cause && `根本原因：${record.root_cause}`,
        ].filter(Boolean)
        const text = parts.join('\n')
        return (
          <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{text || '-'}</span>
        )
      },
    },
    {
      title: '附件',
      dataIndex: 'attachment_count',
      width: 100,
      render: (value: number) => (
        <Space size={4}>
          <PaperClipOutlined className="text-gray-400" />
          {value > 0 ? `${value} 个` : '-'}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
      fixed: 'end' as const,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => void openEdit(record.id)}>
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id, record.code)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          历史偏差
        </Typography.Title>
        <Typography.Paragraph style={{ marginTop: 8, color: 'var(--color-steel)' }}>
          记录历史偏差情况，偏差事件 / 偏差内容（人机料法环测） / 调查结论（直接原因、根本原因）可由 AI 从附件提取。
        </Typography.Paragraph>
      </div>

      <Card>
        <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
          <Input.Search
            allowClear
            placeholder="搜索编号 / 偏差事件 / 偏差内容 / 调查结论"
            prefix={<SearchOutlined style={{ color: qualityTokens.textMuted }} />}
            style={{ width: 320 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={(value) => {
              setPage(1)
              setSearchText(value.trim())
            }}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => void openCreate()}
          >
            新建历史偏差
          </Button>
          <Upload
            accept=".doc,.docx,.wps,.pdf,.png,.jpg,.jpeg,.md"
            multiple
            showUploadList={false}
            beforeUpload={(file, all) => {
              if (file === all[0]) void handleBatchImport(all as unknown as File[])
              return false
            }}
          >
            <Button icon={<UploadOutlined />} loading={batchImporting}>
              批量导入附件
            </Button>
          </Upload>
          <Button icon={<ReloadOutlined />} onClick={() => void refetch()}>
            刷新
          </Button>
        </Space>

        {isError ? (
          <Alert
            type="error"
            showIcon
            message="历史偏差加载失败"
            description={loadError instanceof Error ? loadError.message : undefined}
            action={
              <Button size="small" onClick={() => void refetch()}>
                重试
              </Button>
            }
          />
        ) : (
          <Table<HistoricalDeviationListItem>
            rowKey="id"
            loading={isLoading}
            columns={columns}
            dataSource={data?.items || []}
            locale={{ emptyText: <TableEmptyState /> }}
            pagination={{
              current: page,
              pageSize,
              total: data?.total || 0,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage)
                setPageSize(nextPageSize)
              },
            }}
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>

      <Drawer
        title={drawer.record ? `历史偏差 - ${drawer.record.code}` : '新建历史偏差'}
        size={760}
        open={drawer.open}
        onClose={closeDrawer}
        destroyOnHidden
        extra={
          <Space>
            <Button
              icon={<RobotOutlined />}
              loading={drawer.aiExtracting}
              onClick={() => void handleAiExtract()}
            >
              AI 提取
            </Button>
            <Button type="primary" onClick={() => void handleSave()}>
              保存
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="deviation_event" label="偏差事件" rules={[{ max: 2000 }]}>
            <Input.TextArea rows={2} placeholder="由 AI 从附件提取或手动填写" />
          </Form.Item>
          <Form.Item name="deviation_content" label="偏差内容" rules={[{ max: 5000 }]}>
            <Input.TextArea
              rows={4}
              placeholder="由 AI 从附件提取，按人机料法环测（5M1E）总结，可手动编辑"
            />
          </Form.Item>
          <Form.Item name="direct_cause" label="调查结论 - 直接原因" rules={[{ max: 2000 }]}>
            <Input.TextArea rows={2} placeholder="由 AI 从附件提取，可手动编辑" />
          </Form.Item>
          <Form.Item name="root_cause" label="调查结论 - 根本原因" rules={[{ max: 2000 }]}>
            <Input.TextArea rows={2} placeholder="由 AI 从附件提取，可手动编辑" />
          </Form.Item>
          <Form.Item name="investigation_conclusion" label="调查结论（汇总）" rules={[{ max: 5000 }]}>
            <Input.TextArea rows={2} placeholder="调查结论汇总（可编辑）" />
          </Form.Item>
          <Form.Item name="remark" label="备注" rules={[{ max: 2000 }]}>
            <Input.TextArea rows={1} placeholder="备注（可选）" />
          </Form.Item>
        </Form>

        <Typography.Title level={5} style={{ marginTop: 8 }}>
          附件（doc/docx/wps 上传后自动转为标准 MD，保留正文图片与表格）
        </Typography.Title>
        <Upload
          multiple
          accept=".doc,.docx,.wps,.pdf,.png,.jpg,.jpeg"
          showUploadList={false}
          beforeUpload={(file) => {
            void handleUpload(file)
            return false
          }}
        >
          <Button icon={<PlusOutlined />}>上传附件</Button>
        </Upload>

        <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
          {drawer.attachments.length === 0 && drawer.pendingFiles.length === 0 && (
            <Typography.Text type="secondary">暂无附件</Typography.Text>
          )}
          {drawer.attachments.map((attachment) => (
            <div
              key={attachment.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 10px',
                border: `1px solid ${qualityTokens.border}`,
                borderRadius: 6,
              }}
            >
              <Space size={8}>
                <PaperClipOutlined className="text-gray-400" />
                <Typography.Text ellipsis style={{ maxWidth: 300 }}>
                  {attachment.file_name}
                </Typography.Text>
                {attachment.converted ? <Tag color="blue">标准MD</Tag> : <Tag>原文件</Tag>}
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {formatSize(attachment.file_size)}
                </Typography.Text>
              </Space>
              <Space size={4}>
                <Button
                  type="link"
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() =>
                    setPreview({ open: true, url: attachment.url, file_name: attachment.file_name })
                  }
                >
                  预览
                </Button>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => void handleDeleteAttachment(attachment.id)}
                >
                  删除
                </Button>
              </Space>
            </div>
          ))}
          {drawer.pendingFiles.map((file, index) => (
            <div
              key={`${file.name}-${index}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 10px',
                border: `1px dashed ${qualityTokens.border}`,
                borderRadius: 6,
              }}
            >
              <Space size={8}>
                <PaperClipOutlined className="text-gray-400" />
                <Typography.Text ellipsis style={{ maxWidth: 300 }}>
                  {file.name}
                </Typography.Text>
                <Tag>待上传</Tag>
              </Space>
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => removePendingFile(index)}
              >
                移除
              </Button>
            </div>
          ))}
        </div>
      </Drawer>

      <AttachmentPreviewModal
        preview={preview}
        onClose={() => setPreview(null)}
      />
    </div>
  )
}
