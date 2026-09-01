'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  App,
  Button,
  Card,
  Collapse,
  DatePicker,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
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
  DownloadOutlined,
  EyeOutlined,
  PaperClipOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import Image from 'next/image'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import {
  fetchDeviationWorkbenchReport,
  fetchDeviationWorkbenchReports,
  fetchDeviationWorkbenchSettings,
  fetchFeishuDeviationReportRecord,
  fetchFeishuDeviationReportRecords,
} from '@/lib/api/client/quality'
import {
  analyzeDeviationWorkbench,
  deleteDeviationWorkbenchAttachment,
  deleteDeviationWorkbenchReport,
  updateDeviationWorkbenchSettings,
  uploadDeviationWorkbenchAttachment,
} from '@/actions/quality-deviation-workbench'
import type {
  DeviationWorkbenchAttachmentDescriptor,
  DeviationWorkbenchReportDetail,
  DeviationWorkbenchReportListItem,
  DeviationWorkbenchSettings,
  DeviationWorkbenchStatus,
  FeishuDeviationReportRecordItem,
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

const statusConfig: Record<string, { color: string; label: string }> = {
  processing: { color: 'processing', label: '生成中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

function statusMeta(status: string): { color: string; label: string } {
  return statusConfig[status] ?? { color: 'default', label: status }
}

const sourceConfig: Record<string, { label: string; color: string }> = {
  report_record: { label: '报告记录', color: 'blue' },
  manual: { label: '手动输入', color: 'default' },
}

function formatTime(value?: string | null): string {
  if (!value) return '-'
  return value.slice(0, 19).replace('T', ' ')
}

/** 生成调查报告的抽屉：来源（报告记录/手动输入）+ 附件上传 + 生成 */
function CreateReportDrawer({
  open,
  initialRecordId,
  onClose,
  onCreated,
}: {
  open: boolean
  initialRecordId?: string | null
  onClose: () => void
  onCreated: (report: DeviationWorkbenchReportDetail) => void
}) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [sourceType, setSourceType] = useState<'report_record' | 'manual'>(
    initialRecordId ? 'report_record' : 'manual'
  )
  const [recordId, setRecordId] = useState<string | null>(initialRecordId || null)
  const [prefill, setPrefill] = useState<FeishuDeviationReportRecordItem | null>(null)
  const [descriptors, setDescriptors] = useState<DeviationWorkbenchAttachmentDescriptor[]>([])
  const [generating, setGenerating] = useState(false)
  // 是否已生成报告（生成的附件已被报告消费，关闭时不再清理）
  const generatedRef = useRef(false)

  const { data: reportRecords, isLoading: recordsLoading } = useQuery({
    queryKey: ['quality-deviation-workbench-records', 1],
    queryFn: () => fetchFeishuDeviationReportRecords({ page: 1, page_size: 50 }),
  })

  // 选择报告记录后拉取详情预填（异步回调内 setState，非副作用内直接同步调用）
  useEffect(() => {
    if (!recordId) return
    let cancelled = false
    void fetchFeishuDeviationReportRecord(recordId)
      .then((record) => {
        if (!cancelled) setPrefill(record)
      })
      .catch(() => {
        if (!cancelled) {
          setPrefill(null)
          message.warning('未能获取报告记录详情（可能飞书未启用），可手动输入偏差内容')
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordId])

  const handleRecordSelect = useCallback((value: string) => {
    setRecordId(value)
    setPrefill(null)
  }, [])

  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const descriptor = await uploadDeviationWorkbenchAttachment(formData)
      if (!descriptor) throw new Error('上传失败')
      setDescriptors((prev) => [...prev, descriptor])
      message.success('上传成功')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败')
    }
  }

  const handleGenerate = async () => {
    const values = await form.validateFields()
    const manualText = sourceType === 'manual' ? (values.manual_text as string | undefined) : undefined
    if (sourceType === 'manual' && !manualText?.trim() && descriptors.length === 0) {
      message.warning('请手动输入偏差内容或上传附件')
      return
    }
    if (sourceType === 'report_record' && !recordId) {
      message.warning('请选择报告记录')
      return
    }
    setGenerating(true)
    try {
      const report = await analyzeDeviationWorkbench({
        source_type: sourceType,
        source_record_id: sourceType === 'report_record' ? recordId : null,
        manual_text: manualText || null,
        attachments: descriptors,
      })
      if (!report) throw new Error('生成失败')
      generatedRef.current = true
      message.success(report.status === 'completed' ? '调查报告已生成' : '生成未完成，请查看结果')
      onCreated(report)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const descriptorKeys = (descriptor: DeviationWorkbenchAttachmentDescriptor): string[] =>
    [descriptor.storage_key, descriptor.converted_md_key, ...(descriptor.asset_keys || [])]
      .filter((key): key is string => Boolean(key))

  const cleanupUploaded = (items: DeviationWorkbenchAttachmentDescriptor[]) => {
    const keys = items.flatMap(descriptorKeys)
    if (keys.length) {
      void deleteDeviationWorkbenchAttachment(keys).catch(() => undefined)
    }
  }

  const handleClose = () => {
    // 未生成报告时清理已上传但未消费的附件，避免孤儿对象残留
    if (!generatedRef.current) {
      cleanupUploaded(descriptors)
    }
    onClose()
  }

  const reportRecordOptions = useMemo(
    () =>
      (reportRecords?.items || []).map((item) => ({
        value: item.record_id || item.feishu_base_record_id || item.id,
        label: `${item.deviation_code || ''}${item.product_batch ? `｜${item.product_batch}` : ''}｜${(item.description || '').slice(0, 24)}`,
      })),
    [reportRecords]
  )

  return (
    <Drawer
      title="新建偏差工作台 - 生成调查报告"
      size={720}
      open={open}
      onClose={handleClose}
      destroyOnHidden
      extra={
        <Button
          type="primary"
          icon={<RobotOutlined />}
          loading={generating}
          onClick={() => void handleGenerate()}
        >
          生成调查报告
        </Button>
      }
    >
      <Card size="small" title="信息来源">
        <Form form={form} layout="vertical">
          <Form.Item label="来源方式">
            <Select
              value={sourceType}
              onChange={(value: 'report_record' | 'manual') => setSourceType(value)}
              options={[
                { value: 'report_record', label: '从偏差管理报告记录获取' },
                { value: 'manual', label: '手动输入 / 上传附件' },
              ]}
            />
          </Form.Item>

          {sourceType === 'report_record' ? (
            <>
              <Form.Item label="选择报告记录">
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="选择偏差报告记录"
                  loading={recordsLoading}
                  options={reportRecordOptions}
                  value={recordId || undefined}
                  onChange={(value) => void handleRecordSelect(value)}
                />
              </Form.Item>
              {prefill && (
                <div
                  style={{
                    padding: 12,
                    border: `1px solid ${qualityTokens.border}`,
                    borderRadius: 6,
                    background: '#fafafa',
                  }}
                >
                  <Typography.Paragraph style={{ marginBottom: 6 }}>
                    <Typography.Text strong>偏差内容：</Typography.Text>
                    {prefill.description || '-'}
                  </Typography.Paragraph>
                  <Typography.Paragraph style={{ marginBottom: 6 }}>
                    <Typography.Text strong>涉及产品/批号：</Typography.Text>
                    {prefill.product_name_batch || prefill.product_batch || '-'}
                  </Typography.Paragraph>
                  {prefill.attachments?.length ? (
                    <Typography.Paragraph style={{ marginBottom: 0 }}>
                      <Typography.Text strong>附件：</Typography.Text>
                      {prefill.attachments.map((attachment, index) => (
                        <span key={index}>
                          <a href={attachment.url} target="_blank" rel="noreferrer">
                            {attachment.name}
                          </a>
                          {index < (prefill.attachments?.length || 0) - 1 ? '、' : ''}
                        </span>
                      ))}
                    </Typography.Paragraph>
                  ) : null}
                </div>
              )}
            </>
          ) : (
            <Form.Item
              name="manual_text"
              label="偏差内容（手动输入）"
              rules={[{ max: 10000 }]}
            >
              <Input.TextArea
                rows={5}
                placeholder="请输入偏差情况，例如：灌装压塞压力超上限，怀疑传感器漂移……"
              />
            </Form.Item>
          )}
        </Form>
      </Card>

      <Card size="small" title="上传附件（doc/docx/wps 自动转标准 MD 供 AI 分析）" style={{ marginTop: 16 }}>
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
          {descriptors.length === 0 && <Typography.Text type="secondary">暂无附件</Typography.Text>}
          {descriptors.map((descriptor) => (
            <div
              key={descriptor.id}
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
                <Typography.Text ellipsis style={{ maxWidth: 320 }}>
                  {descriptor.file_name}
                </Typography.Text>
                {descriptor.converted ? <Tag color="blue">标准MD</Tag> : <Tag>原文件</Tag>}
              </Space>
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => {
                  cleanupUploaded([descriptor])
                  setDescriptors((prev) => prev.filter((item) => item.id !== descriptor.id))
                }}
              >
                移除
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <Card size="small" title="分析依据" style={{ marginTop: 16 }}>
        <Typography.Paragraph style={{ marginBottom: 0, color: 'var(--color-steel)' }}>
          AI 将结合历史偏差、文件管理（文件目录）内容与模型通用知识，从人、机、料、法、环、测（5M1E）六个维度展开调查分析并生成调查报告。
        </Typography.Paragraph>
      </Card>
    </Drawer>
  )
}

/** 报告详情抽屉：结构化调查报告 + 参考来源 + 附件 */
function ReportDetailDrawer({
  report,
  onClose,
}: {
  report: DeviationWorkbenchReportDetail | null
  onClose: () => void
}) {
  const [preview, setPreview] = useState<{ url: string; file_name: string } | null>(null)

  const context = (report?.context_snapshot || {}) as {
    historical_deviations?: Array<Record<string, unknown>>
    documents?: Array<Record<string, unknown>>
  }

  const handleExportMd = () => {
    if (!report?.report_md) return
    const blob = new Blob([report.report_md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${report.code || '偏差调查报告'}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Drawer
      title={report ? `调查报告 - ${report.code}` : '调查报告'}
      size={860}
      open={!!report}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Button icon={<DownloadOutlined />} onClick={handleExportMd}>
          导出 Markdown
        </Button>
      }
    >
      {report ? (
        <Spin spinning={report.status === 'processing'}>
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag color={statusMeta(report.status).color}>{statusMeta(report.status).label}</Tag>
            <Tag color={sourceConfig[report.source_type]?.color}>{sourceConfig[report.source_type]?.label}</Tag>
            {report.model_name && <Typography.Text type="secondary">模型：{report.model_name}</Typography.Text>}
          </Space>

          {report.status === 'failed' && (
            <Typography.Paragraph type="danger">
              生成失败：{report.error_message || '未知错误'}
            </Typography.Paragraph>
          )}

          {report.status === 'completed' && report.report_md ? (
            <div className="rounded bg-gray-50 p-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownPreviewComponents}>
                {report.report_md}
              </ReactMarkdown>
            </div>
          ) : (
            <Typography.Text type="secondary">暂无报告内容</Typography.Text>
          )}

          <Collapse
            style={{ marginTop: 16 }}
            items={[
              {
                key: 'sources',
                label: '参考来源',
                children: (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {!context.historical_deviations?.length && !context.documents?.length && (
                      <Typography.Text type="secondary">未检索到历史偏差 / 文件管理制度</Typography.Text>
                    )}
                    {context.historical_deviations?.map((item, index) => (
                      <div key={index}>
                        <Typography.Text strong>{String(item.code || '')}</Typography.Text>
                        <Typography.Paragraph style={{ marginBottom: 0 }}>
                          事件：{String(item.deviation_event || '-')}
                        </Typography.Paragraph>
                        <Typography.Paragraph style={{ marginBottom: 0 }}>
                          根因：{String(item.root_cause || '-')}
                        </Typography.Paragraph>
                      </div>
                    ))}
                    {context.documents?.map((item, index) => (
                      <div key={index}>
                        <Typography.Text strong>
                          {String(item.code || '')} {String(item.name || '')}
                        </Typography.Text>
                        <Typography.Paragraph style={{ marginBottom: 0 }}>
                          {String(item.content || '-')}
                        </Typography.Paragraph>
                      </div>
                    ))}
                  </div>
                ),
              },
              {
                key: 'attachments',
                label: `附件（${report.attachments?.length || 0}）`,
                children: (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {!report.attachments?.length && <Typography.Text type="secondary">无附件</Typography.Text>}
                    {report.attachments?.map((attachment) => (
                      <Space key={attachment.id}>
                        <PaperClipOutlined className="text-gray-400" />
                        <Typography.Text>{attachment.file_name}</Typography.Text>
                        <Button
                          type="link"
                          size="small"
                          icon={<EyeOutlined />}
                          onClick={() => setPreview({ url: attachment.url, file_name: attachment.file_name })}
                        >
                          预览
                        </Button>
                      </Space>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        </Spin>
      ) : null}

      <Modal
        title={preview ? `附件预览 - ${preview.file_name}` : '附件预览'}
        open={!!preview}
        onCancel={() => setPreview(null)}
        footer={null}
        width={900}
        destroyOnHidden
      >
        {preview && <AttachmentContent key={preview.url} url={preview.url} />}
      </Modal>
    </Drawer>
  )
}

function AttachmentContent({ url }: { url: string }) {
  const [state, setState] = useState<{ text: string; blobUrl: string; contentType: string }>({
    text: '',
    blobUrl: '',
    contentType: '',
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`获取附件内容失败: ${res.status}`)
        const contentType = res.headers.get('content-type') || ''
        if (!contentType || contentType.includes('markdown') || contentType.startsWith('text/')) {
          return res.text().then((text) => ({ text, blobUrl: '', contentType }))
        }
        return res.blob().then((blob) => ({ text: '', blobUrl: URL.createObjectURL(blob), contentType }))
      })
      .then((result) => {
        if (!cancelled) setState(result)
      })
      .catch(() => {
        if (!cancelled) setState({ text: '预览失败', blobUrl: '', contentType: '' })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [url])

  return (
    <Spin spinning={loading}>
      {state.blobUrl ? (
        state.contentType.includes('pdf') ? (
          <iframe src={state.blobUrl} title="PDF 预览" className="h-[68vh] w-full border-0" />
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
  )
}

/** 设置抽屉：可修改调查报告提示词 */
function SettingsDrawer({
  open,
  settings,
  onClose,
  onSaved,
}: {
  open: boolean
  settings: DeviationWorkbenchSettings | null
  onClose: () => void
  onSaved: (settings: DeviationWorkbenchSettings) => void
}) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      form.setFieldsValue({ prompt: settings?.report_system_prompt || '' })
    }
  }, [open, settings, form])

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const result = await updateDeviationWorkbenchSettings(values.prompt as string)
      if (!result) throw new Error('保存失败')
      message.success('提示词已更新')
      onSaved(result)
      onClose()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title="偏差工作台设置 - 调查报告提示词"
      size={680}
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Button type="primary" loading={saving} onClick={() => void handleSave()}>
          保存
        </Button>
      }
    >
      <Typography.Paragraph>
        修改调查报告的系统提示词，指导 AI 从人机料法环测（5M1E）维度分析并输出调查报告。留空时使用默认提示词。
      </Typography.Paragraph>
      <Form form={form} layout="vertical">
        <Form.Item name="prompt" label="调查报告提示词" rules={[{ required: true, message: '请输入提示词' }]}>
          <Input.TextArea rows={14} placeholder="请输入调查报告系统提示词" />
        </Form.Item>
      </Form>
    </Drawer>
  )
}

export function DeviationWorkbenchPage({ initialRecordId }: { initialRecordId?: string | null }) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()

  const [keyword, setKeyword] = useState('')
  const [searchText, setSearchText] = useState('')
  const [sourceType, setSourceType] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [dateRange, setDateRange] = useState<[string, string] | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [createOpen, setCreateOpen] = useState<boolean>(() => Boolean(initialRecordId))
  const [detail, setDetail] = useState<DeviationWorkbenchReportDetail | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['quality-deviation-workbench', page, pageSize, searchText, sourceType, status, dateRange],
    queryFn: () =>
      fetchDeviationWorkbenchReports({
        keyword: searchText || undefined,
        source_type: sourceType,
        status,
        date_from: dateRange?.[0],
        date_to: dateRange?.[1],
        page,
        page_size: pageSize,
      }),
  })

  const { data: settings } = useQuery({
    queryKey: ['quality-deviation-workbench-settings'],
    queryFn: fetchDeviationWorkbenchSettings,
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['quality-deviation-workbench'] })
  }, [queryClient])

  const openDetail = async (reportId: string) => {
    try {
      const report = await fetchDeviationWorkbenchReport(reportId)
      if (!report) throw new Error('未找到报告')
      setDetail(report)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败')
    }
  }

  const handleCreated = (report: DeviationWorkbenchReportDetail) => {
    setCreateOpen(false)
    invalidate()
    setDetail(report)
  }

  const handleDelete = (reportId: string, code: string) => {
    modal.confirm({
      title: '删除工作台记录',
      content: `确定删除「${code}」吗？删除后不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDeviationWorkbenchReport(reportId)
          message.success('已删除')
          invalidate()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  const columns: TableColumnsType<DeviationWorkbenchReportListItem> = [
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
      render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: '来源',
      dataIndex: 'source_type',
      width: 100,
      render: (value: string) => (
        <Tag color={sourceConfig[value]?.color}>{sourceConfig[value]?.label || value}</Tag>
      ),
    },
    {
      title: '偏差摘要',
      dataIndex: 'deviation_summary',
      ellipsis: { showTitle: false },
      render: (value: string | null) => <span title={value ?? ''}>{value || '-'}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: DeviationWorkbenchStatus) => (
        <Tag color={statusMeta(value).color}>{statusMeta(value).label}</Tag>
      ),
    },
    {
      title: '生成时间',
      dataIndex: 'created_at',
      width: 160,
      render: (value: string) => formatTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'end' as const,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => void openDetail(record.id)}>
            查看
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
          偏差工作台
        </Typography.Title>
        <Typography.Paragraph style={{ marginTop: 8, color: 'var(--color-steel)' }}>
          从偏差管理报告记录获取或手动输入 / 上传附件，AI 结合历史偏差、文件管理与模型知识，按人机料法环测（5M1E）生成调查报告并保留记录。
        </Typography.Paragraph>
      </div>

      <Card>
        <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
          <Input.Search
            allowClear
            placeholder="搜索编号 / 偏差摘要 / 报告正文"
            prefix={<SearchOutlined style={{ color: qualityTokens.textMuted }} />}
            style={{ width: 280 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={(value) => {
              setPage(1)
              setSearchText(value.trim())
            }}
          />
          <Select
            allowClear
            placeholder="来源"
            style={{ width: 120 }}
            value={sourceType}
            onChange={(value) => {
              setPage(1)
              setSourceType(value)
            }}
            options={[
              { value: 'report_record', label: '报告记录' },
              { value: 'manual', label: '手动输入' },
            ]}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 120 }}
            value={status}
            onChange={(value) => {
              setPage(1)
              setStatus(value)
            }}
            options={[
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
              { value: 'processing', label: '生成中' },
            ]}
          />
          <DatePicker.RangePicker
            style={{ width: 240 }}
            value={
              dateRange
                ? [dayjs(dateRange[0]), dayjs(dateRange[1])]
                : null
            }
            onChange={(value) => {
              setPage(1)
              setDateRange(
                value && value[0] && value[1]
                  ? [value[0].format('YYYY-MM-DD'), value[1].format('YYYY-MM-DD')]
                  : undefined
              )
            }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建偏差工作台
          </Button>
          <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>
            设置
          </Button>
          <Button icon={<SearchOutlined />} onClick={() => void refetch()}>
            刷新
          </Button>
        </Space>

        <Table<DeviationWorkbenchReportListItem>
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
      </Card>

      {createOpen ? (
        <CreateReportDrawer
          open
          initialRecordId={initialRecordId}
          onClose={() => setCreateOpen(false)}
          onCreated={handleCreated}
        />
      ) : null}

      <ReportDetailDrawer report={detail} onClose={() => setDetail(null)} />

      <SettingsDrawer
        open={settingsOpen}
        settings={settings || null}
        onClose={() => setSettingsOpen(false)}
        onSaved={(nextSettings) => {
          queryClient.setQueryData(['quality-deviation-workbench-settings'], nextSettings)
        }}
      />
    </div>
  )
}
