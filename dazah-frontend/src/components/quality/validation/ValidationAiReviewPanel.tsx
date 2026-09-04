'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Modal,
  Popconfirm,
  Input,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'

import {
  createValidationReview,
  deleteValidationReview,
  rerunValidationReview,
  runValidationReview,
  uploadValidationReviewFile,
} from '@/actions/validation-review'
import {
  fetchValidationReviewDetail,
  fetchValidationReviewJob,
  fetchValidationReviews,
} from '@/lib/api/client/quality'
import {
  VALIDATION_REVIEW_MODE_LABELS,
  VALIDATION_REVIEW_STATUS_LABELS,
} from '@/types/quality'
import type { ValidationReviewListItem } from '@/types/quality'
import { ValidationReviewFindingsTable } from './ValidationReviewFindingsTable'

const REVIEW_LIST_KEY = ['quality', 'validation-reviews', 'list']
const REVIEW_DETAIL_KEY = ['quality', 'validation-reviews', 'detail']

function statusTag(status: string) {
  const colorMap: Record<string, string> = {
    draft: 'default',
    processing: 'processing',
    completed: 'success',
    failed: 'error',
  }
  return (
    <Tag color={colorMap[status] ?? 'default'}>
      {VALIDATION_REVIEW_STATUS_LABELS[status] ?? status}
    </Tag>
  )
}

export function ValidationAiReviewPanel() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [createOpen, setCreateOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [pollerJobId, setPollerJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [uploadFiles, setUploadFiles] = useState<UploadFile[]>([])
  const [focusPoints, setFocusPoints] = useState('')
  const [exportingId, setExportingId] = useState<string | null>(null)

  const listQuery = useQuery({
    queryKey: [...REVIEW_LIST_KEY, page, pageSize],
    queryFn: () => fetchValidationReviews({ page, page_size: pageSize }),
  })

  const detailQuery = useQuery({
    queryKey: [...REVIEW_DETAIL_KEY, detailId],
    queryFn: () => fetchValidationReviewDetail(detailId as string),
    enabled: !!detailId,
  })

  const record = detailQuery.data ?? null

  // 后台任务轮询：审核完成后刷新详情与列表
  useEffect(() => {
    if (!pollerJobId) return
    const timer = window.setInterval(async () => {
      try {
        const status = await fetchValidationReviewJob(pollerJobId)
        if (status.state === 'completed' || status.state === 'failed') {
          window.clearInterval(timer)
          setPollerJobId(null)
          if (status.review_id) setDetailId(status.review_id)
          queryClient.invalidateQueries({ queryKey: REVIEW_LIST_KEY })
          queryClient.invalidateQueries({ queryKey: REVIEW_DETAIL_KEY })
          if (status.state === 'failed') {
            message.error(status.error_message || 'AI 审核失败，请重试')
          } else {
            message.success('AI 审核完成')
          }
        }
      } catch {
        // 轮询瞬时失败忽略，下个周期重试
      }
    }, 2000)
    return () => {
      window.clearInterval(timer)
    }
  }, [pollerJobId, queryClient, message])

  const openDetail = useCallback(
    (id: string) => {
      setDetailId(id)
      queryClient.invalidateQueries({ queryKey: [...REVIEW_DETAIL_KEY, id] })
    },
    [queryClient]
  )

  const handleRun = useCallback(
    async (reviewId: string) => {
      try {
        const result = await runValidationReview(reviewId)
        if (result?.job_id) {
          setPollerJobId(result.job_id)
          message.success('已提交 AI 审核，正在运行…')
        }
      } catch (error) {
        message.error(error instanceof Error ? error.message : '发起审核失败')
      }
    },
    [message]
  )

  const handleRerun = useCallback(
    async (reviewId: string) => {
      try {
        const result = await rerunValidationReview(reviewId)
        if (result?.job_id) {
          setPollerJobId(result.job_id)
          message.success('已重新提交 AI 审核')
        }
      } catch (error) {
        message.error(error instanceof Error ? error.message : '重新审核失败')
      }
    },
    [message]
  )

  const handleDelete = useCallback(
    async (reviewId: string) => {
      try {
        await deleteValidationReview(reviewId)
        message.success('已删除审核记录')
        if (detailId === reviewId) setDetailId(null)
        queryClient.invalidateQueries({ queryKey: REVIEW_LIST_KEY })
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    },
    [message, queryClient, detailId]
  )

  const handleExport = useCallback(
    async (reviewId: string) => {
      setExportingId(reviewId)
      try {
        const res = await fetch(
          `/api/v1/quality/validation-reviews/${reviewId}/export`,
          { method: 'POST' }
        )
        if (!res.ok) {
          const body = await res.json().catch(() => null)
          throw new Error(body?.message || `导出失败: ${res.status}`)
        }
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = `验证AI审核-${reviewId}.docx`
        anchor.click()
        URL.revokeObjectURL(url)
        message.success('审核报告已导出')
      } catch (error) {
        message.error(error instanceof Error ? error.message : '导出失败')
      } finally {
        setExportingId(null)
      }
    },
    [message]
  )

  const handleCreate = useCallback(async () => {
    if (uploadFiles.length === 0) {
      message.warning('请先选择要上传的验证方案 / 验证报告')
      return
    }
    setSubmitting(true)
    try {
      const created = await createValidationReview({
        review_mode: 'upload',
        focus_points: focusPoints.trim() || undefined,
      })
      if (!created?.id) throw new Error('创建审核会话失败')
      for (const file of uploadFiles) {
        if (!file.originFileObj) continue
        const formData = new FormData()
        formData.append('file', file.originFileObj)
        await uploadValidationReviewFile(created.id, formData)
      }
      setCreateOpen(false)
      setUploadFiles([])
      setFocusPoints('')
      queryClient.invalidateQueries({ queryKey: REVIEW_LIST_KEY })
      openDetail(created.id)
      message.success('审核会话已创建，可点击开始审核')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建失败')
    } finally {
      setSubmitting(false)
    }
  }, [focusPoints, uploadFiles, queryClient, openDetail, message])

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (value: string, item: ValidationReviewListItem) =>
        value || `审核记录 ${item.id.slice(0, 8)}`,
    },
    {
      title: '来源',
      dataIndex: 'review_mode',
      width: 100,
      render: (value: string) => VALIDATION_REVIEW_MODE_LABELS[value] ?? value,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) => statusTag(value),
    },
    {
      title: '文件数',
      dataIndex: 'file_count',
      width: 80,
      align: 'center' as const,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value: string) => (value ? value.replace('T', ' ').slice(0, 16) : '—'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, item: ValidationReviewListItem) => (
        <Space size={4}>
          <Button size="small" onClick={() => openDetail(item.id)}>
            查看
          </Button>
          {item.status === 'failed' || item.status === 'completed' ? (
            <Popconfirm
              title="重新运行 AI 审核"
              description="将使用当前文件重新执行一次完整审核"
              okText="重跑"
              cancelText="取消"
              trigger="click"
              onConfirm={() => handleRerun(item.id)}
            >
              <Button size="small" icon={<ReloadOutlined />} />
            </Popconfirm>
          ) : null}
          <Popconfirm
            title="删除审核记录"
            description="删除后不可恢复，不影响文件管理目录"
            okText="删除"
            cancelText="取消"
            trigger="click"
            onConfirm={() => handleDelete(item.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const files = record?.files ?? []
  const findings = record?.findings ?? []
  const basisUsed = record?.basis_used ?? []
  const stats = record?.stats ?? null
  const running = pollerJobId != null || record?.status === 'processing'

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="验证方案与报告 AI 审核"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateOpen(true)}
          >
            新建审核
          </Button>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          上传 VP/VR 文档或从文件管理目录选择条目，AI 将对照目录核对引用的文件编号
          、修订版本，并检查方案与报告的一致性。结果仅用于辅助审核，不写回台账，
          审批仍按线下流程执行。
        </Typography.Paragraph>
      </Card>

      <Card>
        <Table<ValidationReviewListItem>
          rowKey="id"
          columns={columns}
          dataSource={listQuery.data?.items ?? []}
          loading={listQuery.isLoading}
          scroll={{ x: 900 }}
          pagination={{
            current: page,
            pageSize,
            total: listQuery.data?.total ?? 0,
            onChange: (next) => setPage(next),
            showSizeChanger: false,
          }}
          locale={{ emptyText: '暂无审核记录，点击「新建审核」开始' }}
          onRow={(item) => ({ onClick: () => openDetail(item.id), style: { cursor: 'pointer' } })}
        />
      </Card>

      <Modal
        title="新建验证 AI 审核"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        okText="创建并上传文件"
        confirmLoading={submitting}
        width={640}
        destroyOnHidden
      >
        <Upload.Dragger
          multiple
          beforeUpload={() => false}
          fileList={uploadFiles}
          onChange={({ fileList }) => setUploadFiles(fileList)}
          accept=".doc,.docx,.md,.wps,.txt"
          maxCount={4}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽上传验证方案 / 验证报告</p>
          <p className="ant-upload-hint">
            支持 .doc/.docx/.md/.wps/.txt，单个不超过 20MB；系统自动识别方案（VP）与报告（VR）并匹配文件管理依据
          </p>
        </Upload.Dragger>
        <Form layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item label="审核关注点（可选）">
            <Input.TextArea
              value={focusPoints}
              onChange={(event) => setFocusPoints(event.target.value)}
              placeholder="例如：重点核对清洁限度计算依据；检查再验证周期与偏差处理"
              rows={3}
              maxLength={2000}
              showCount
            />
          </Form.Item>
        </Form>
        <Alert
          type="info"
          showIcon
          message="AI 将自动识别文档类型与编号，匹配文件管理依据并做正文一致性核查；也可在上方补充您特别关注的审核内容。"
        />
      </Modal>

      <Drawer
        title={record?.title || '审核详情'}
        width={860}
        open={!!detailId}
        onClose={() => setDetailId(null)}
        destroyOnHidden
        extra={
          <Space>
            {record?.status === 'draft' ? (
              <Button
                type="primary"
                loading={running}
                onClick={() => detailId && handleRun(detailId)}
              >
                开始审核
              </Button>
            ) : null}
            {record?.status === 'completed' ? (
              <Button
                icon={<DownloadOutlined />}
                loading={exportingId === detailId}
                onClick={() => detailId && handleExport(detailId)}
              >
                导出报告
              </Button>
            ) : null}
            {record?.status === 'completed' || record?.status === 'failed' ? (
              <Button
                icon={<ReloadOutlined />}
                onClick={() => detailId && handleRerun(detailId)}
              >
                重新审核
              </Button>
            ) : null}
          </Space>
        }
      >
        {detailQuery.isLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : record ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card size="small">
              <Descriptions column={3} size="small">
                <Descriptions.Item label="来源">
                  {VALIDATION_REVIEW_MODE_LABELS[record.review_mode] ?? record.review_mode}
                </Descriptions.Item>
                <Descriptions.Item label="状态">{statusTag(record.status)}</Descriptions.Item>
                <Descriptions.Item label="生成时间">
                  {record.last_generated_at
                    ? record.last_generated_at.replace('T', ' ').slice(0, 16)
                    : '—'}
                </Descriptions.Item>
                <Descriptions.Item label="模型">{record.model_name || '—'}</Descriptions.Item>
                <Descriptions.Item label="记录号">
                  <Typography.Text code>{record.id.slice(0, 8)}</Typography.Text>
                </Descriptions.Item>
              </Descriptions>
              {record.error_message ? (
                <Alert
                  style={{ marginTop: 12 }}
                  type="error"
                  showIcon
                  message="审核失败"
                  description={record.error_message}
                />
              ) : null}
            </Card>

            {files.length > 0 ? (
              <Card size="small" title="审核文档">
                <Table
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={files}
                  columns={[
                    {
                      title: '类型',
                      dataIndex: 'doc_kind',
                      width: 90,
                      render: (value: string) => (
                        <Tag color={value === 'plan' ? 'blue' : 'green'}>
                          {value === 'plan' ? '方案' : '报告'}
                        </Tag>
                      ),
                    },
                    { title: '文件', dataIndex: 'file_name', ellipsis: true },
                    {
                      title: '解析',
                      dataIndex: 'parse_status',
                      width: 110,
                      render: (value: string, item) =>
                        value === 'failed' ? (
                          <Tooltip title={item.parse_error || '解析失败'}>
                            <Tag color="red">解析失败</Tag>
                          </Tooltip>
                        ) : value === 'completed' ? (
                          <Tag color="success">已解析</Tag>
                        ) : (
                          <Tag>待解析</Tag>
                        ),
                    },
                  ]}
                />
              </Card>
            ) : null}

            {running ? (
              <Card size="small">
                <Space>
                  <Spin />
                  <Typography.Text>AI 审核运行中，正在解析文档并核对引用…</Typography.Text>
                </Space>
              </Card>
            ) : null}

            {record.summary ? (
              <Card size="small" title="审核结论">
                <Typography.Paragraph style={{ marginBottom: 0 }}>
                  {record.summary}
                </Typography.Paragraph>
              </Card>
            ) : null}

            {stats ? (
              <Card size="small" title="问题统计">
                <Space size={32} wrap>
                  <Statistic title="问题总数" value={stats.total_findings} />
                  <Statistic title="高" value={stats.high} valueStyle={{ color: '#cf1322' }} />
                  <Statistic title="中" value={stats.medium} valueStyle={{ color: '#d46b08' }} />
                  <Statistic title="低" value={stats.low} />
                  <Statistic title="引用核对" value={`${stats.references_matched}/${stats.references_checked}`} />
                  <Statistic
                    title="方案报告核对"
                    value={stats.plan_report_checked ? '已核对' : '未核对'}
                  />
                </Space>
              </Card>
            ) : null}

            <Card size="small" title="发现问题">
              <ValidationReviewFindingsTable findings={findings} />
            </Card>

            {(record?.basis_comparison ?? []).length > 0 ? (
              <Card size="small" title="基准正文一致性核查">
                <Table
                  rowKey="entry_id"
                  size="small"
                  pagination={false}
                  dataSource={record?.basis_comparison ?? []}
                  columns={[
                    { title: '依据文件', dataIndex: 'name', ellipsis: true },
                    { title: '编号', dataIndex: 'code', width: 170 },
                    {
                      title: '入选理由',
                      dataIndex: 'reason',
                      ellipsis: true,
                      render: (value: string) => value || '—',
                    },
                    {
                      title: '比对结果',
                      dataIndex: 'mismatch_count',
                      width: 110,
                      render: (value: number) =>
                        value > 0 ? (
                          <Tag color="red">{value} 处不一致</Tag>
                        ) : (
                          <Tag color="green">一致</Tag>
                        ),
                    },
                  ]}
                />
              </Card>
            ) : null}

            {basisUsed.length > 0 ? (
              <Card size="small" title="引用文件核对明细">
                <Table
                  rowKey="code"
                  size="small"
                  pagination={{ pageSize: 10, showSizeChanger: false }}
                  dataSource={basisUsed}
                  columns={[
                    {
                      title: '引用编号',
                      dataIndex: 'code',
                      width: 180,
                      render: (value: string) => (
                        <Typography.Text code>{value}</Typography.Text>
                      ),
                    },
                    { title: '目录文件', dataIndex: 'entry_name', ellipsis: true },
                    { title: '目录编号', dataIndex: 'entry_code', width: 180 },
                    {
                      title: '核对结果',
                      dataIndex: 'issue',
                      width: 120,
                      render: (value: string) => {
                        const map: Record<string, { text: string; color: string }> = {
                          version_mismatch: { text: '版本不一致', color: 'red' },
                          missing: { text: '目录缺失', color: 'orange' },
                          none: { text: '一致', color: 'green' },
                        }
                        const item = map[value] ?? { text: value, color: 'default' }
                        return <Tag color={item.color}>{item.text}</Tag>
                      },
                    },
                  ]}
                />
              </Card>
            ) : null}
          </Space>
        ) : (
          <Empty description="审核记录不存在或已被删除" />
        )}
      </Drawer>
    </Space>
  )
}
