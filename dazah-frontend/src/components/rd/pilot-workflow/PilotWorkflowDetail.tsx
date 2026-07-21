'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Card,
  Button,
  Tag,
  Collapse,
  Spin,
  Typography,
  Space,
  App,
  Popconfirm,
  Upload,
} from 'antd'
import {
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  AuditOutlined,
  ArrowLeftOutlined,
  DeleteOutlined,
} from '@ant-design/icons'
import {
  PilotWorkflow,
  PilotWorkflowStep,
  PilotWorkflowStatus,
  PilotWorkflowStepStatus,
} from '@/types/pilot-workflow'
import { fetchPilotWorkflow } from '@/lib/api/pilot-workflow'
import { startPilotWorkflow, approvePilotWorkflowStep, uploadPilotWorkflowDocument, deletePilotWorkflow } from '@/actions/rd'

const { Text } = Typography

const statusColors: Record<PilotWorkflowStatus, string> = {
  pending: 'default',
  running: 'processing',
  waiting_approval: 'warning',
  completed: 'success',
  failed: 'error',
}

const statusLabels: Record<PilotWorkflowStatus, string> = {
  pending: '待启动',
  running: '执行中',
  waiting_approval: '等待确认',
  completed: '已完成',
  failed: '失败',
}

const stepStatusIcons: Record<PilotWorkflowStepStatus, React.ReactNode> = {
  pending: <ClockCircleOutlined style={{ color: '#999' }} />,
  running: <LoadingOutlined style={{ color: '#1890ff' }} />,
  waiting_approval: <AuditOutlined style={{ color: '#faad14' }} />,
  completed: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  failed: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
  skipped: <ClockCircleOutlined style={{ color: '#d9d9d9' }} />,
}

interface Props {
  workflowId: string
  initialWorkflow: PilotWorkflow | null
}

export function PilotWorkflowDetail({ workflowId, initialWorkflow }: Props) {
  const router = useRouter()
  const { message } = App.useApp()
  const [workflow, setWorkflow] = useState<PilotWorkflow | null>(initialWorkflow)
  const [starting, setStarting] = useState(false)
  const [approving, setApproving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const loadWorkflow = useCallback(async () => {
    try {
      const data = await fetchPilotWorkflow(workflowId)
      setWorkflow(data)
    } catch (err) {
      console.error('加载失败:', err)
    }
  }, [workflowId])

  // Poll when running or waiting_approval
  useEffect(() => {
    if (workflow?.status !== 'running' && workflow?.status !== 'waiting_approval') return
    const interval = setInterval(loadWorkflow, 3000)
    return () => clearInterval(interval)
  }, [workflow?.status, loadWorkflow])

  const handleStart = async () => {
    setStarting(true)
    try {
      await startPilotWorkflow(workflowId)
      message.success('工作流已启动')
      await loadWorkflow()
    } catch {
      message.error('启动失败')
    } finally {
      setStarting(false)
    }
  }

  const handleApprove = async () => {
    setApproving(true)
    try {
      const result = await approvePilotWorkflowStep(workflowId)
      if (result && typeof result === 'object' && 'status' in result) {
        const r = result as { status: string; message?: string }
        if (r.status === 'completed') {
          message.success('工作流已完成')
        } else if (r.status === 'waiting_approval') {
          message.success(r.message || '步骤已确认，下一步已执行')
        } else if (r.status === 'failed') {
          message.error('步骤执行失败')
        }
      } else {
        message.success('步骤已确认')
      }
      await loadWorkflow()
    } catch {
      message.error('确认失败')
    } finally {
      setApproving(false)
    }
  }



  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      await uploadPilotWorkflowDocument(workflowId, file)
      message.success('文档上传成功')
      await loadWorkflow()
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败')
    } finally {
      setUploading(false)
    }
    return false // Prevent default upload
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deletePilotWorkflow(workflowId)
      message.success('已删除')
      router.push('/rd/pilot-workflow')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeleting(false)
    }
  }

  if (!workflow) {
    return (
      <div className="flex items-center justify-center p-12">
        <Spin size="large" />
      </div>
    )
  }

  const steps = workflow.steps || []
  const hasWaitingStep = steps.some((s) => s.status === 'waiting_approval')

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => router.push('/rd/pilot-workflow')}
            className="mb-2"
          >
            返回列表
          </Button>
          <h1 className="text-xl font-semibold">{workflow.product_name}</h1>
          <Text type="secondary">
            {workflow.equipment_type} {workflow.equipment_volume}L ·{' '}
            {workflow.scale_up_ratio}x 放大
          </Text>
        </div>
        <Space>
          <Tag color={statusColors[workflow.status]}>
            {statusLabels[workflow.status]}
          </Tag>
          <Popconfirm
              title="确认删除"
              description="删除后不可恢复，确认删除？"
              onConfirm={handleDelete}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                loading={deleting}
              >
                删除
              </Button>
            </Popconfirm>

          {workflow.status === 'pending' && (
            <Upload
              accept=".pdf,.doc,.docx,.txt"
              showUploadList={false}
              beforeUpload={handleUpload}
              disabled={uploading}
            >
              <Button loading={uploading}>
                上传工艺文档
              </Button>
            </Upload>
          )}
          {workflow.status === 'pending' && (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={starting}
              onClick={handleStart}
            >
              启动执行
            </Button>
          )}
          {(workflow.status === 'running' || workflow.status === 'waiting_approval') && hasWaitingStep && (
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={approving}
              onClick={handleApprove}
            >
              确认并继续
            </Button>
          )}
        </Space>
      </div>


      {workflow.input_document_path && (
        <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
          <Text type="secondary">已上传文档: </Text>
          <Text>{workflow.input_document_path.split('/').pop()}</Text>
        </div>
      )}

      {/* Pipeline Visualization */}
      <Card title="工作流进度" className="mb-6">
        <div className="flex items-start gap-2 overflow-x-auto py-4">
          {steps.map((step, idx) => (
            <div key={step.id} className="flex items-center">
              <StepCard step={step} />
              {idx < steps.length - 1 && (
                <div className="mx-2 text-2xl text-gray-300">→</div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Step Details */}
      <Card title="步骤详情" className="mb-6">
        <Collapse
          items={steps.map((step) => ({
            key: step.id,
            label: (
              <div className="flex items-center gap-2">
                {stepStatusIcons[step.status]}
                <span className="font-medium">
                  {step.step_order}. {step.step_name}
                </span>
                <Tag>{step.status === 'waiting_approval' ? '等待确认' : step.status}</Tag>
                {step.started_at && step.completed_at && (
                  <Text type="secondary" className="text-xs">
                    耗时: {calcDuration(step.started_at, step.completed_at)}
                  </Text>
                )}
              </div>
            ),
            children: <StepDetail step={step} />,
          }))}
        />
      </Card>

      {/* Final Report */}
      {workflow.final_report && (
        <Card title="最终报告">
          <ReportView report={workflow.final_report} />
        </Card>
      )}
    </div>
  )
}

function StepCard({ step }: { step: PilotWorkflowStep }) {
  const bgColors: Record<PilotWorkflowStepStatus, string> = {
    pending: 'bg-gray-50 border-gray-200',
    running: 'bg-blue-50 border-blue-300',
    waiting_approval: 'bg-yellow-50 border-yellow-300',
    completed: 'bg-green-50 border-green-300',
    failed: 'bg-red-50 border-red-300',
    skipped: 'bg-gray-50 border-gray-200',
  }

  return (
    <div
      className={`min-w-[160px] rounded-lg border p-3 ${bgColors[step.status]}`}
    >
      <div className="mb-1 flex items-center gap-1">
        {stepStatusIcons[step.status]}
        <Text className="text-xs font-medium">{step.step_name}</Text>
      </div>
      <Text type="secondary" className="text-xs">
        {step.status === 'running' && '执行中...'}
        {step.status === 'waiting_approval' && '⏳ 等待确认'}
        {step.status === 'completed' && '✓ 完成'}
        {step.status === 'failed' && '✗ 失败'}
        {step.status === 'pending' && '等待中'}
      </Text>
    </div>
  )
}

function StepDetail({ step }: { step: PilotWorkflowStep }) {
  return (
    <div className="space-y-4">
      {step.error_message && (
        <div className="rounded bg-red-50 p-3 text-red-600">
          <Text strong>错误：</Text> {step.error_message}
        </div>
      )}

      {step.output_data && (
        <Collapse
          size="small"
          items={[
            {
              key: 'output',
              label: '输出数据',
              children: (
                <pre className="max-h-96 overflow-auto rounded bg-gray-50 p-3 text-xs">
                  {JSON.stringify(step.output_data, null, 2)}
                </pre>
              ),
            },
          ]}
        />
      )}
    </div>
  )
}

function ReportView({ report }: { report: Record<string, unknown> }) {
  const sections =
    (report.sections as Array<{ title: string; content: string }>) || []
  const conclusion = report.conclusion as string

  return (
    <div className="space-y-4">
      {conclusion && (
        <div className="rounded-lg bg-blue-50 p-4">
          <Text strong>结论：</Text>
          <p className="mt-1">{conclusion}</p>
        </div>
      )}
      {sections.map((section, idx) => (
        <div key={idx}>
          <Text strong>{section.title}</Text>
          <p className="mt-1 whitespace-pre-wrap text-sm">{section.content}</p>
        </div>
      ))}
    </div>
  )
}

function calcDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 1000) return '<1s'
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}
