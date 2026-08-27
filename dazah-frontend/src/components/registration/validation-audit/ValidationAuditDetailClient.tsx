'use client'

 'use client'

import { useState, useCallback, useEffect, type JSX } from 'react'
import {
  Button, Space, Tag, App, Card, Descriptions, Upload, Select, Empty,
  Typography,
} from 'antd'
import {
  ArrowLeftOutlined, UploadOutlined, PlayCircleOutlined, FileTextOutlined,
  ReloadOutlined, CheckCircleOutlined, LoadingOutlined,
  FilePdfOutlined, FileWordOutlined, DownloadOutlined,
} from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import type {
  ValidationAuditTask, ValidationAuditFileListItem, ValidationAuditIssue,
  ValidationAuditReport, IssueType,
} from '@/types/validation-audit'
import {
  AUDIT_MODE_LABELS, STATUS_LABELS, CONCLUSION_LABELS,
  ISSUE_TYPE_LABELS, PARSE_STATUS_LABELS,
} from '@/types/validation-audit'
import {
  uploadValidationAuditFiles,
  parseValidationAuditFiles,
  runValidationAudit,
} from '@/actions/validation-audit'
import {
  fetchValidationAuditTaskById,
  fetchValidationAuditFiles,
  fetchValidationAuditIssues,
  fetchValidationAuditReport,
} from '@/lib/api/validation-audit'

const { Text } = Typography

interface Props {
  task: ValidationAuditTask
  initialFiles: ValidationAuditFileListItem[]
  initialIssues: ValidationAuditIssue[]
  initialReport: ValidationAuditReport | null
}

export default function ValidationAuditDetailClient({
  task: serverTask,
  initialFiles,
  initialIssues,
  initialReport,
}: Props) {
  const { message } = App.useApp()
  const router = useRouter()

  const [task, setTask] = useState<ValidationAuditTask>(serverTask)
  const [files, setFiles] = useState<ValidationAuditFileListItem[]>(initialFiles)
  const [issues, setIssues] = useState<ValidationAuditIssue[]>(initialIssues)
  const [report, setReport] = useState<ValidationAuditReport | null>(initialReport)
  const [issueFilter, setIssueFilter] = useState<string>('all')
  const [uploading, setUploading] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [auditing, setAuditing] = useState(false)
  const [loading, setLoading] = useState(false)

  // Fetch fresh data from backend — fixes stale Server Component cache
  const refreshData = useCallback(async () => {
    setLoading(true)
    try {
      const [taskRes, filesRes, issuesRes] = await Promise.all([
        fetchValidationAuditTaskById(task.id),
        fetchValidationAuditFiles(task.id),
        fetchValidationAuditIssues(task.id),
      ])
      if (taskRes?.data) setTask(taskRes.data)
      if (filesRes?.data) setFiles(filesRes.data)
      if (issuesRes?.data) setIssues(issuesRes.data)

      // Report may not exist yet
      try {
        const reportRes = await fetchValidationAuditReport(task.id)
        if (reportRes?.data) setReport(reportRes.data)
      } catch {
        // Report not generated yet, keep current state
      }
    } catch (err) {
      console.error('Failed to refresh data:', err)
    } finally {
      setLoading(false)
    }
  }, [task.id])

  // Fetch fresh data on mount to fix stale initial data from Server Component
  useEffect(() => {
    queueMicrotask(refreshData)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const statusCfg = STATUS_LABELS[task.status as keyof typeof STATUS_LABELS]
  const conclusionCfg = task.conclusion
    ? CONCLUSION_LABELS[task.conclusion as keyof typeof CONCLUSION_LABELS]
    : null

  const filteredIssues = issueFilter === 'all'
    ? issues
    : issues.filter(i => i.issue_type === issueFilter)

  const [uploadFileList, setUploadFileList] = useState<any[]>([])

  const handleUpload = async () => {
    if (uploadFileList.length === 0) {
      message.warning('请先选择要上传的文件')
      return
    }

    const formData = new FormData()
    for (const file of uploadFileList) {
      const originFile = file.originFileObj || file
      formData.append('files', originFile)
    }
    formData.append('file_type', task.audit_mode === 'report' ? 'report' : 'protocol')

    setUploading(true)
    const result = await uploadValidationAuditFiles(task.id, formData)
    setUploading(false)

    if (result.success) {
      message.success('文件上传成功')
      setUploadFileList([])
      // Refresh data from backend
      await refreshData()
    } else {
      message.error(result.message)
    }
  }

  const handleParse = async () => {
    setParsing(true)
    const result = await parseValidationAuditFiles(task.id)
    if (result.success) {
      message.success('文件解析完成')
      // Refresh data from backend
      await refreshData()
    } else {
      message.error(result.message)
    }
    setParsing(false)
  }

  const handleAudit = async () => {
    setAuditing(true)
    const result = await runValidationAudit(task.id)
    if (result.success) {
      message.success('审核完成')
      // Refresh data from backend
      await refreshData()
    } else {
      message.error(result.message)
    }
    setAuditing(false)
  }

  // Workflow conditions based on CURRENT state (not stale initial state)
  const canUpload = ['draft', 'uploaded'].includes(task.status)
  const canParse = files.some(f => f.parse_status === 'pending') && ['draft', 'uploaded'].includes(task.status)
  const canAudit = files.length > 0 && files.every(f => f.parse_status === 'completed') && ['uploaded', 'completed', 'failed'].includes(task.status)

  // Determine workflow step
  const workflowStep = task.status === 'draft' ? 0
    : (task.status === 'uploaded' || task.status === 'parsing') ? (files.every(f => f.parse_status === 'completed') && files.length > 0 ? 2 : 1)
    : task.status === 'auditing' ? 2
    : task.status === 'completed' ? 3
    : task.status === 'failed' ? 2
    : 0

  const getFileIcon = (filename: string) => {
    const ext = filename.toLowerCase().split('.').pop()
    return ext === 'pdf'
      ? <FilePdfOutlined style={{ fontSize: 18, color: '#e03131' }} />
      : <FileWordOutlined style={{ fontSize: 18, color: '#0075de' }} />
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  }

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => router.push('/registration/validation-audit')}
            style={{ borderRadius: 8 }}
          />
          <div>
            <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-1">
              {task.task_name}
            </h1>
            <Space>
              {statusCfg && <Tag color={statusCfg.color}>{statusCfg.label}</Tag>}
              {conclusionCfg && <Tag color={conclusionCfg.color}>{conclusionCfg.label}</Tag>}
              <Tag>{AUDIT_MODE_LABELS[task.audit_mode]}</Tag>
              {loading && <Tag icon={<LoadingOutlined />} color="processing">同步中</Tag>}
            </Space>
          </div>
        </div>
        <Button
          icon={<ReloadOutlined spin={loading} />}
          onClick={refreshData}
          style={{ borderRadius: 8 }}
        >
          刷新
        </Button>
      </div>

      {/* Workflow Progress */}
      <Card
        style={{ borderRadius: 12, marginBottom: 16, border: '1px solid var(--color-hairline)' }}
        styles={{ body: { padding: '20px 24px' } }}
      >
        <div className="flex items-center gap-2 mb-4">
          <span className="text-[14px] font-medium text-[var(--color-charcoal)]">审核流程</span>
          {parsing && <Tag color="processing" icon={<LoadingOutlined />}>正在解析文件...</Tag>}
          {auditing && <Tag color="processing" icon={<LoadingOutlined />}>正在执行AI审核...</Tag>}
        </div>
        <div className="flex items-center">
          {[
            { label: '上传文件', icon: <UploadOutlined /> },
            { label: '文件解析', icon: <FileTextOutlined /> },
            { label: 'AI 审核', icon: <PlayCircleOutlined /> },
            { label: '审核完成', icon: <CheckCircleOutlined /> },
          ].map((step, idx) => {
            const isDone = idx < workflowStep
            const isActive = idx === workflowStep
            return (
              <div key={idx} className="flex items-center flex-1">
                <div className="flex flex-col items-center flex-1">
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-[15px] mb-2 transition-all"
                    style={{
                      backgroundColor: isDone ? '#1aae39' : isActive ? 'var(--color-primary)' : 'var(--color-surface)',
                      color: isDone || isActive ? '#fff' : 'var(--color-stone)',
                      boxShadow: isActive ? '0 0 0 3px rgba(86,69,212,0.15)' : 'none',
                    }}
                  >
                    {isDone ? <CheckCircleOutlined /> : step.icon}
                  </div>
                  <span className={`text-[12px] ${isActive ? 'font-semibold text-[var(--color-primary)]' : isDone ? 'text-[var(--color-charcoal)]' : 'text-[var(--color-stone)]'}`}>
                    {step.label}
                  </span>
                </div>
                {idx < 3 && (
                  <div
                    className="h-0.5 flex-shrink-0 -mt-5"
                    style={{
                      width: '60px',
                      backgroundColor: isDone ? '#1aae39' : 'var(--color-hairline)',
                    }}
                  />
                )}
              </div>
            )
          })}
        </div>
      </Card>

      {/* Task Info */}
      <Card
        style={{ borderRadius: 12, marginBottom: 16, border: '1px solid var(--color-hairline)' }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        <Descriptions size="small" column={4}>
          <Descriptions.Item label={<Text type="secondary" className="text-[12px]">品种</Text>}>
            <span className="text-[13px]">{task.product_name}</span>
          </Descriptions.Item>
          <Descriptions.Item label={<Text type="secondary" className="text-[12px]">方法</Text>}>
            <span className="text-[13px]">{task.method_name}</span>
          </Descriptions.Item>
          <Descriptions.Item label={<Text type="secondary" className="text-[12px]">来源公司</Text>}>
            <span className="text-[13px]">{task.source_company}</span>
          </Descriptions.Item>
          <Descriptions.Item label={<Text type="secondary" className="text-[12px]">创建时间</Text>}>
            <span className="text-[13px]">{task.created_at?.slice(0, 16).replace('T', ' ')}</span>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Action Bar */}
      <Card
        style={{ borderRadius: 12, marginBottom: 16, border: '1px solid var(--color-hairline)' }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        <div className="flex items-center justify-between">
          <Space size={8} wrap>
            {canUpload && (
              <>
                <Upload
                  multiple
                  accept=".docx,.pdf"
                  fileList={uploadFileList}
                  beforeUpload={() => false}
                  onChange={({ fileList }) => setUploadFileList(fileList)}
                >
                  <Button icon={<UploadOutlined />} style={{ borderRadius: 8 }}>
                    选择文件
                  </Button>
                </Upload>
                {uploadFileList.length > 0 && (
                  <Button
                    type="primary"
                    icon={<UploadOutlined />}
                    loading={uploading}
                    onClick={handleUpload}
                    style={{ borderRadius: 8 }}
                  >
                    上传 ({uploadFileList.length})
                  </Button>
                )}
              </>
            )}
            {canParse && (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={parsing}
                onClick={handleParse}
                style={{ borderRadius: 8, backgroundColor: '#dd5b00' }}
              >
                开始解析
              </Button>
            )}
            {canAudit && (
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={auditing}
                onClick={handleAudit}
                style={{ borderRadius: 8 }}
              >
                开始审核
              </Button>
            )}
            {!canUpload && !canParse && !canAudit && task.status !== 'completed' && (
              <Text type="secondary" className="text-[13px]">
                {parsing || auditing ? '处理中，请稍候...' : '暂无可执行操作'}
              </Text>
            )}
            {task.status === 'completed' && (
              <Tag color="success" icon={<CheckCircleOutlined />} style={{ fontSize: 13, padding: '2px 12px' }}>
                审核已完成
              </Tag>
            )}
          </Space>
          <Space>
            {report && (
              <Button
                icon={<DownloadOutlined />}
                style={{ borderRadius: 8 }}
                onClick={() => window.open(`/api/v1/registration/validation-audit/tasks/${task.id}/export`, '_blank')}
              >
                导出报告
              </Button>
            )}
          </Space>
        </div>
      </Card>

      {/* Files Section */}
      <Card
        title={
          <span className="text-[14px] font-medium">
            <FileTextOutlined className="mr-2" />
            审核文件 ({files.length})
          </span>
        }
        size="small"
        style={{ borderRadius: 12, marginBottom: 16, border: '1px solid var(--color-hairline)' }}
        styles={{ body: { padding: files.length === 0 ? '24px' : '8px 16px' } }}
      >
        {files.length === 0 ? (
          <Empty description="暂无文件，请先上传审核文件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="space-y-0">
            {files.map((file) => {
              const parseCfg = PARSE_STATUS_LABELS[file.parse_status as keyof typeof PARSE_STATUS_LABELS]
              return (
                <div
                  key={file.id}
                  className="flex items-center justify-between py-3 px-2 border-b border-[var(--color-hairline-soft)] last:border-b-0"
                >
                  <div className="flex items-center gap-3">
                    {getFileIcon(file.original_filename)}
                    <div>
                      <div className="text-[13px] text-[var(--color-charcoal)] font-medium">
                        {file.original_filename}
                      </div>
                      <div className="text-[11px] text-[var(--color-stone)]">
                        {formatFileSize(file.file_size)} · {file.file_type}
                      </div>
                    </div>
                  </div>
                  {parseCfg && (
                    <Tag color={parseCfg.color} style={{ marginRight: 0 }}>
                      {parseCfg.label}
                    </Tag>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {/* Issues & Report */}
      {(issues.length > 0 || report) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {/* Issues */}
          <Card
            title={
              <span className="text-[14px] font-medium">
                问题列表 ({issues.length})
              </span>
            }
            size="small"
            style={{ borderRadius: 12, border: '1px solid var(--color-hairline)' }}
            styles={{ body: { padding: issues.length === 0 ? '24px' : '8px 12px' } }}
            extra={
              issues.length > 0 ? (
                <Select
                  size="small"
                  value={issueFilter}
                  onChange={setIssueFilter}
                  style={{ width: 110 }}
                  options={[
                    { label: '全部', value: 'all' },
                    { label: '严重问题', value: 'serious' },
                    { label: '一般问题', value: 'general' },
                    { label: '建议优化', value: 'suggestion' },
                  ]}
                />
              ) : null
            }
          >
            {filteredIssues.length === 0 ? (
              <Empty description="暂无问题" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {filteredIssues.map((issue) => {
                  const typeCfg = ISSUE_TYPE_LABELS[issue.issue_type as IssueType]
                  return (
                    <div
                      key={issue.id}
                      className="border border-[var(--color-hairline)] p-3"
                      style={{ borderRadius: 8 }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <Space size={4}>
                          <span className="text-[12px] font-semibold text-[var(--color-charcoal)]">
                            {issue.issue_no}
                          </span>
                          {typeCfg && (
                            <Tag color={typeCfg.color} style={{ fontSize: 11, marginRight: 0 }}>
                              {typeCfg.label}
                            </Tag>
                          )}
                        </Space>
                        {issue.page_no && (
                          <span className="text-[11px] text-[var(--color-stone)]">
                            P.{issue.page_no}
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-[var(--color-steel)] mb-1">
                        {issue.dimension} · {issue.check_item}
                      </div>
                      <div className="text-[13px] text-[var(--color-charcoal)] mb-2 leading-relaxed">
                        {issue.description}
                      </div>
                      {issue.suggestion && (
                        <div className="text-[12px] text-[var(--color-primary)] bg-[var(--color-surface)] p-2" style={{ borderRadius: 6 }}>
                          💡 {issue.suggestion}
                        </div>
                      )}
                      {issue.evidence_text && (
                        <div className="text-[11px] text-[var(--color-stone)] mt-2 italic border-l-2 border-[var(--color-hairline)] pl-2">
                          &ldquo;{issue.evidence_text}&rdquo;
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </Card>

          {/* Report */}
          <Card
            title={
              <span className="text-[14px] font-medium">
                审核报告
              </span>
            }
            size="small"
            style={{ borderRadius: 12, border: '1px solid var(--color-hairline)' }}
            styles={{ body: { padding: report ? '16px 20px' : '24px' } }}
          >
            {report ? (
              <div className="max-h-[600px] overflow-y-auto">
                <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)] mb-4">
                  {report.report_title}
                </h2>
                {report.report_markdown && (
                  <MarkdownContent content={report.report_markdown} />
                )}
              </div>
            ) : (
              <Empty description="报告尚未生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

// Simple markdown renderer (no external dependency)
function MarkdownContent({ content }: { content: string }) {
  const lines = content.split('\n')
  const elements: JSX.Element[] = []
  let inCodeBlock = false
  let codeLines: string[] = []

  lines.forEach((line, idx) => {
    if (line.startsWith('```')) {
      if (inCodeBlock) {
        elements.push(
          <pre key={idx} className="bg-[var(--color-surface)] p-3 overflow-x-auto text-[12px]" style={{ borderRadius: 6 }}>
            <code>{codeLines.join('\n')}</code>
          </pre>
        )
        codeLines = []
        inCodeBlock = false
      } else {
        inCodeBlock = true
      }
      return
    }

    if (inCodeBlock) {
      codeLines.push(line)
      return
    }

    if (line.startsWith('### ')) {
      elements.push(<h3 key={idx} className="text-[16px] font-semibold text-[var(--color-charcoal)] mt-4 mb-2">{line.slice(4)}</h3>)
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={idx} className="text-[18px] font-semibold text-[var(--color-charcoal)] mt-5 mb-2">{line.slice(3)}</h2>)
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={idx} className="text-[22px] font-semibold text-[var(--color-charcoal)] mt-6 mb-3">{line.slice(2)}</h1>)
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(<li key={idx} className="text-[13px] text-[var(--color-charcoal)] ml-4 list-disc">{line.slice(2)}</li>)
    } else if (line.startsWith('---')) {
      elements.push(<hr key={idx} className="border-[var(--color-hairline)] my-4" />)
    } else if (line.trim() === '') {
      elements.push(<div key={idx} className="h-2" />)
    } else {
      elements.push(<p key={idx} className="text-[13px] text-[var(--color-charcoal)] leading-relaxed mb-1">{line}</p>)
    }
  })

  return <>{elements}</>
}
