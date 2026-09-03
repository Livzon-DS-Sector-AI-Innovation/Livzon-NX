'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
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
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  PaperClipOutlined,
  PlayCircleOutlined,
  PlusOutlined,
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
  analyzeDeviationWorkbench,
  deleteDeviationWorkbenchAttachment,
  deleteDeviationWorkbenchReport,
  updateDeviationWorkbenchSettings,
  uploadDeviationWorkbenchAttachment,
} from '@/actions/quality-deviation-workbench'
import {
  fetchDeviationWorkbenchReport,
  fetchDeviationWorkbenchReports,
  fetchDeviationWorkbenchSettings,
  fetchFeishuDeviationReportRecord,
  fetchFeishuDeviationReportRecords,
} from '@/lib/api/client/quality'
import type {
  CreateDeviationWorkbenchPayload,
  DeviationWorkbenchAttachmentDescriptor,
  DeviationWorkbenchReportDetail,
  DeviationWorkbenchReportListItem,
  DeviationWorkbenchSettings,
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

/** 附件内容预览（MD 渲染 / PDF iframe / 图片） */
function AttachmentContent({ url }: { url: string }) {
  const [state, setState] = useState<{ text: string; blobUrl: string; contentType: string }>({
    text: '',
    blobUrl: '',
    contentType: '',
  })
  const [loading, setLoading] = useState(true)
  // happy-dom（vitest）下 blob: iframe 会抛 ERR_INVALID_URL 崩掉测试进程
  const isTestEnv = import.meta.env?.MODE === 'test'

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

  // 输入区状态
  const [deviationContent, setDeviationContent] = useState('')
  const [affectedItems, setAffectedItems] = useState('')
  const [supplementText, setSupplementText] = useState('')
  const [recordId, setRecordId] = useState<string | null>(initialRecordId || null)
  const [recordSelectOpen, setRecordSelectOpen] = useState(false)
  const [descriptors, setDescriptors] = useState<DeviationWorkbenchAttachmentDescriptor[]>([])
  const [generating, setGenerating] = useState(false)

  // 结果区状态
  const [report, setReport] = useState<DeviationWorkbenchReportDetail | null>(null)

  // 生成记录台账状态
  const [keyword, setKeyword] = useState('')
  const [searchText, setSearchText] = useState('')
  const [sourceType, setSourceType] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [dateRange, setDateRange] = useState<[string, string] | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [preview, setPreview] = useState<{ url: string; file_name: string } | null>(null)

  const { data, isLoading, isError: recordsError, error: recordsErrorObj, refetch } = useQuery({
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

  const { data: reportRecords, isLoading: recordsLoading } = useQuery({
    queryKey: ['quality-deviation-workbench-records', 1],
    queryFn: () => fetchFeishuDeviationReportRecords({ page: 1, page_size: 50 }),
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['quality-deviation-workbench'] })
  }, [queryClient])

  const descriptorKeys = (descriptor: DeviationWorkbenchAttachmentDescriptor): string[] =>
    [descriptor.storage_key, descriptor.converted_md_key, ...(descriptor.asset_keys || [])]
      .filter((key): key is string => Boolean(key))

  const cleanupUploaded = (items: DeviationWorkbenchAttachmentDescriptor[]) => {
    const keys = items.flatMap(descriptorKeys)
    if (keys.length) {
      void deleteDeviationWorkbenchAttachment(keys).catch(() => undefined)
    }
  }

  // 报告记录选择 / 预填（含从报告记录详情跳入的 initialRecordId）
  useEffect(() => {
    if (!recordId) return
    let cancelled = false
    void fetchFeishuDeviationReportRecord(recordId)
      .then((record) => {
        if (cancelled) return
        if (record.description) setDeviationContent(record.description)
        if (record.product_name_batch || record.product_batch) {
          setAffectedItems(record.product_name_batch || record.product_batch || '')
        }
      })
      .catch(() => {
        if (!cancelled) {
          message.warning('未能获取报告记录详情（可能飞书未启用），可手动输入偏差内容')
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- message 来自 App.useApp()，实例稳定
  }, [recordId])

  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const descriptor = await uploadDeviationWorkbenchAttachment(formData)
      if (!descriptor) throw new Error('上传失败')
      setDescriptors((prev) => [...prev, descriptor])
      message.success('上传成功（word 已自动转标准 MD）')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败')
    }
  }

  const handleGenerate = async () => {
    if (!deviationContent.trim() && descriptors.length === 0) {
      message.warning('请填写偏差内容或上传附件')
      return
    }
    setGenerating(true)
    try {
      const payload: CreateDeviationWorkbenchPayload = {
        source_type: recordId ? 'report_record' : 'manual',
        source_record_id: recordId,
        manual_text: deviationContent || null,
        affected_items: affectedItems || null,
        supplement_text: supplementText || null,
        attachments: descriptors,
      }
      const result = await analyzeDeviationWorkbench(payload)
      if (!result) throw new Error('生成失败')
      setDescriptors([])
      setReport(result)
      if (result.status !== 'completed') {
        message.warning(result.error_message || '生成未完成，请查看报告')
      }
      invalidate()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const handleCopyReport = async () => {
    if (!report?.report_md) return
    try {
      await navigator.clipboard.writeText(report.report_md)
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择复制')
    }
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

  const openDetail = async (reportId: string) => {
    try {
      const detail = await fetchDeviationWorkbenchReport(reportId)
      if (!detail) throw new Error('未找到报告')
      setReport(detail)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败')
    }
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
          if (report?.id === reportId) setReport(null)
          invalidate()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '删除失败')
        }
      },
    })
  }

  const recordColumns: TableColumnsType<DeviationWorkbenchReportListItem> = [
    {
      title: '生成时间',
      dataIndex: 'created_at',
      width: 150,
      render: (value: string) => formatTime(value),
    },
    {
      title: '偏差编号',
      dataIndex: 'code',
      width: 140,
      render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: '偏差内容',
      dataIndex: 'deviation_summary',
      ellipsis: { showTitle: false },
      render: (value: string | null) => (
        <span title={value ?? ''}>{value || '-'}</span>
      ),
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
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string) => {
        const meta = statusMeta(value)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
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

  const reportRecordOptions = useMemo(
    () =>
      (reportRecords?.items || []).map((item) => ({
        value: item.record_id || item.feishu_base_record_id || item.id,
        label: `${item.deviation_code || ''}${item.product_batch ? `｜${item.product_batch}` : ''}｜${(item.description || '').slice(0, 24)}`,
      })),
    [reportRecords]
  )

  const context = (report?.context_snapshot || {}) as {
    source?: Record<string, unknown>
    historical_deviations?: Array<Record<string, unknown>>
    documents?: Array<Record<string, unknown>>
    training_ledgers?: Array<Record<string, unknown>>
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            偏差工作台
          </Typography.Title>
          <Typography.Paragraph style={{ marginTop: 8, marginBottom: 0, color: 'var(--color-steel)' }}>
            从报告记录带入或手动输入偏差信息，AI 结合历史偏差、文件管理、培训台账与行业知识，从人机料法环测维度生成调查报告。
          </Typography.Paragraph>
        </div>
        <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>
          设置
        </Button>
      </div>

      {/* 两栏：左输入 / 右报告 */}
      <div
        style={{
          display: 'grid',
          gap: 16,
          gridTemplateColumns: 'minmax(0, 5fr) minmax(0, 6fr)',
          alignItems: 'start',
        }}
      >
        {/* 左栏：偏差信息 + 附件材料 + 生成按钮 */}
        <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <Card title="1. 偏差信息" extra={
            <Button size="small" onClick={() => setRecordSelectOpen(true)}>从报告记录选择</Button>
          }>
            {recordId && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message="已带入报告记录信息，可继续补充后生成"
              />
            )}
            <Typography.Text strong style={{ display: 'block', marginBottom: 6 }}>偏差内容</Typography.Text>
            <Input.TextArea
              rows={4}
              placeholder="描述发现的偏差情况（可从报告记录带入）"
              value={deviationContent}
              onChange={(e) => setDeviationContent(e.target.value)}
            />
            <Typography.Text strong style={{ display: 'block', margin: '12px 0 6px' }}>涉及产品名称/批号</Typography.Text>
            <Input
              placeholder="如 阿司匹林原料药 批号20240101（用于匹配历史偏差与体系文件）"
              value={affectedItems}
              onChange={(e) => setAffectedItems(e.target.value)}
            />
            <Typography.Text strong style={{ display: 'block', margin: '12px 0 6px' }}>补充说明</Typography.Text>
            <Input.TextArea
              rows={3}
              placeholder="调查背景、已采取的措施、需要重点分析的问题等"
              value={supplementText}
              onChange={(e) => setSupplementText(e.target.value)}
            />
          </Card>

          {/* 左栏下方：附件材料 + 生成按钮 */}
          <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
            <Card title="2. 附件材料（word 自动转标准 MD）">
              <Upload
                multiple
                accept=".doc,.docx,.wps,.pdf,.png,.jpg,.jpeg,.md"
                showUploadList={false}
                beforeUpload={(file) => {
                  void handleUpload(file)
                  return false
                }}
              >
                <Button icon={<PlusOutlined />}>选择文件</Button>
              </Upload>
              <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
                {descriptors.length === 0 && (
                  <Typography.Text type="secondary">暂无附件</Typography.Text>
                )}
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
                      <Typography.Text ellipsis style={{ maxWidth: 260 }}>
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
            <Button
              type="primary"
              size="large"
              block
              icon={<PlayCircleOutlined />}
              loading={generating}
              onClick={() => void handleGenerate()}
            >
              {generating ? 'AI 分析中（约 1-3 分钟）…' : '生成调查报告'}
            </Button>
          </div>
        </div>

          {/* 右栏：调查报告 */}
          <Card
            title={report ? `调查报告 - ${report.code}` : '调查报告'}
            extra={
              report?.report_md ? (
                <Space size={4}>
                  <Button size="small" icon={<CopyOutlined />} onClick={() => void handleCopyReport()}>
                    复制 Markdown
                  </Button>
                  <Button size="small" icon={<DownloadOutlined />} onClick={handleExportMd}>
                    导出 Markdown
                  </Button>
                </Space>
              ) : null
            }
          >
            {generating ? (
              <div style={{ display: 'grid', minHeight: 320, placeItems: 'center' }}>
                <Spin tip="AI 分析中（约 1-3 分钟）…" />
              </div>
            ) : report ? (
              <div style={{ display: 'grid', gap: 12 }}>
                <Space wrap>
                  <Tag color={statusMeta(report.status).color}>{statusMeta(report.status).label}</Tag>
                  <Tag color={sourceConfig[report.source_type]?.color}>
                    {sourceConfig[report.source_type]?.label || report.source_type}
                  </Tag>
                  {report.model_name && (
                    <Typography.Text type="secondary">模型：{report.model_name}</Typography.Text>
                  )}
                </Space>
                {report.status === 'failed' && (
                  <Typography.Paragraph type="danger">
                    生成失败：{report.error_message || '未知错误'}
                  </Typography.Paragraph>
                )}
                {report.report_md ? (
                  <div className="max-h-[62vh] overflow-auto rounded bg-gray-50 p-4">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownPreviewComponents}>
                      {report.report_md}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <Typography.Text type="secondary">暂无报告内容</Typography.Text>
                )}
                <Collapse
                  items={[
                    {
                      key: 'sources',
                      label: '参考来源（历史偏差 / 文件管理 / 培训台账）',
                      children: (
                        <div style={{ display: 'grid', gap: 8 }}>
                          {!context.historical_deviations?.length &&
                            !context.documents?.length &&
                            !context.training_ledgers?.length && (
                              <Typography.Text type="secondary">
                                未检索到历史偏差 / 文件管理 / 培训台账记录
                              </Typography.Text>
                            )}
                          {context.historical_deviations?.map((item, index) => (
                            <div key={`h-${index}`}>
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
                            <div key={`d-${index}`}>
                              <Typography.Text strong>
                                {String(item.code || '')} {String(item.name || '')}
                              </Typography.Text>
                              <Typography.Paragraph style={{ marginBottom: 0 }}>
                                {String(item.content || '-')}
                              </Typography.Paragraph>
                            </div>
                          ))}
                          {context.training_ledgers?.map((item, index) => (
                            <div key={`t-${index}`}>
                              <Typography.Text strong>
                                {String(item.training_date || '')} {String(item.training_subject || '')}
                              </Typography.Text>
                              <Typography.Paragraph style={{ marginBottom: 0 }}>
                                {String(item.training_content || '-')}
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
                          {!report.attachments?.length && (
                            <Typography.Text type="secondary">无附件</Typography.Text>
                          )}
                          {report.attachments?.map((attachment) => (
                            <Space key={attachment.id}>
                              <PaperClipOutlined className="text-gray-400" />
                              <Typography.Text>{attachment.file_name}</Typography.Text>
                              <Button
                                type="link"
                                size="small"
                                icon={<EyeOutlined />}
                                onClick={() =>
                                  setPreview({ url: attachment.url, file_name: attachment.file_name })
                                }
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
              </div>
            ) : (
              <div style={{ display: 'grid', minHeight: 320, placeItems: 'center' }}>
                <Typography.Text type="secondary">
                  填写左侧信息后点击「生成调查报告」
                </Typography.Text>
              </div>
            )}
          </Card>
        </div>

        {/* 底部：生成记录台账 */}
        <Card title="生成记录">
          <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
            <Input.Search
              allowClear
              placeholder="搜索偏差编号 / 偏差摘要"
              prefix={<SearchOutlined style={{ color: qualityTokens.textMuted }} />}
              style={{ width: 260 }}
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
              value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
              onChange={(value) => {
                setPage(1)
                setDateRange(
                  value && value[0] && value[1]
                    ? [value[0].format('YYYY-MM-DD'), value[1].format('YYYY-MM-DD')]
                    : undefined
                )
              }}
            />
            <Button icon={<SearchOutlined />} onClick={() => void refetch()}>
              刷新
            </Button>
          </Space>

          {recordsError ? (
            <Alert
              type="error"
              showIcon
              message="生成记录加载失败"
              description={recordsErrorObj instanceof Error ? recordsErrorObj.message : undefined}
              action={
                <Button size="small" onClick={() => void refetch()}>
                  重试
                </Button>
              }
            />
          ) : (
            <Table<DeviationWorkbenchReportListItem>
              rowKey="id"
              loading={isLoading}
              columns={recordColumns}
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

      {/* 报告记录选择弹窗 */}
      <Modal
        title="从报告记录选择"
        open={recordSelectOpen}
        onCancel={() => setRecordSelectOpen(false)}
        footer={null}
        width={720}
        destroyOnHidden
      >
        <Spin spinning={recordsLoading}>
          <Select
            showSearch
            optionFilterProp="label"
            placeholder="选择偏差报告记录"
            style={{ width: '100%' }}
            options={reportRecordOptions}
            value={recordId || undefined}
            onChange={(value) => {
              setRecordId(value)
              setRecordSelectOpen(false)
            }}
          />
        </Spin>
      </Modal>

      {/* 附件内容预览 */}
      <Modal
        title={preview ? `附件预览 - ${preview.file_name}` : '附件预览'}
        open={!!preview}
        onCancel={() => setPreview(null)}
        footer={null}
        width={900}
        destroyOnHidden
      >
        {preview ? <AttachmentContent key={preview.url} url={preview.url} /> : null}
      </Modal>

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
