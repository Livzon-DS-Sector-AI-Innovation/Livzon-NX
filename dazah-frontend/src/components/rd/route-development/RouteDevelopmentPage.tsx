'use client'

import { useState, useCallback, useEffect } from 'react'
import { Button, Input, Table, Tag, Card, Upload, App, Alert, Progress, Tooltip, Space, Popconfirm } from 'antd'
import { PlayCircleOutlined, UploadOutlined, FilePdfOutlined, ReloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { RouteWorkflowPage } from './RouteWorkflowPage'
import { fetchRoutes, createRoute, deleteRoute } from '@/lib/api/rd'
import { RouteDevelopment, RouteStatus, WorkflowModule } from '@/types/rd'
import type { UploadFile } from 'antd/es/upload/interface'

interface RouteDevelopmentPageProps {
  initialRoutes: RouteDevelopment[]
  initialTotal: number
}

export function RouteDevelopmentPage({ initialRoutes, initialTotal }: RouteDevelopmentPageProps) {
  const { message } = App.useApp()
  const [routes, setRoutes] = useState<RouteDevelopment[]>(initialRoutes)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [workflowRoute, setWorkflowRoute] = useState<RouteDevelopment | null>(null)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [literatureFile, setLiteratureFile] = useState<File | null>(null)
  const [literatureInput, setLiteratureInput] = useState('')
  const [creating, setCreating] = useState(false)
  const [apiAvailable, setApiAvailable] = useState(true)
  const [savedWorkflows, setSavedWorkflows] = useState<Map<string, { updatedAt: string; step: number }>>(new Map())

  const loadRoutes = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchRoutes({ page, page_size: pageSize })
      setRoutes(result.items)
      setTotal(result.total)
      setApiAvailable(true)
    } catch {
      setApiAvailable(false)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => {
    loadRoutes()
  }, [loadRoutes])

  // 加载已保存的工作流状态
  useEffect(() => {
    const saved = new Map<string, { updatedAt: string; step: number }>()
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith('workflow-')) {
        try {
          const data = JSON.parse(localStorage.getItem(key) || '{}')
          const routeId = key.replace('workflow-', '')
          saved.set(routeId, {
            updatedAt: data.updatedAt,
            step: data.currentStep,
          })
        } catch {}
      }
    }
    setSavedWorkflows(saved)
  }, [])

  // 创建工作流
  const handleCreateWorkflow = async () => {
    if (fileList.length === 0 && !literatureInput) {
      message.warning('请上传文献PDF或输入文献信息')
      return
    }
    
    // 防止重复提交
    if (creating) {
      return
    }
    setCreating(true)
    
    // 保存第一个文件用于 AI 解析
    if (fileList.length > 0) {
      setLiteratureFile(fileList[0].originFileObj as File)
    }

    // 调用后端 API 创建路线
    try {
      const result = await createRoute({
        project_id: 'project-1',
        name: literatureInput || fileList[0]?.name || '新路线',
        source: fileList.length > 0 ? 'pdf' : 'manual',
        source_reference: literatureInput || undefined,
      })
      
      const newRoute: RouteDevelopment = {
        id: result.id,
        project_id: 'project-1',
        route_no: result.route_no,
        name: literatureInput || fileList[0]?.name || '新路线',
        source: fileList.length > 0 ? 'pdf' : 'manual',
        source_reference: literatureInput || null,
        description: '',
        status: 'in_progress',
        current_module: 'research',
        literature_sources: [],
        candidate_routes: [],
        selected_route_ids: [],
        experiment_plans: [],
        experiments: [],
        assessment: null,
        deliverables: [],
        start_date: new Date().toISOString().split('T')[0],
        end_date: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        created_by: null,
      }

      setWorkflowRoute(newRoute)
      message.success('工作流已创建，开始文献解析')
    } catch (error) {
      message.error('创建路线失败: ' + (error instanceof Error ? error.message : '未知错误'))
    } finally {
      setCreating(false)
    }
  }

  // 继续已有工作流
  const handleContinueWorkflow = (route: RouteDevelopment) => {
    setWorkflowRoute(route)
  }

  // 返回入口页
  const handleBackToList = () => {
    setWorkflowRoute(null)
    setFileList([])
    setLiteratureInput('')
    loadRoutes()
    // 刷新保存的工作流状态
    window.location.reload()
  }

  if (workflowRoute) {
    return (
      <RouteWorkflowPage
        routeId={workflowRoute.id}
        routeName={workflowRoute.name}
        literatureSource={workflowRoute.source_reference || ''}
        literatureFile={literatureFile}
        onComplete={handleBackToList}
        onBack={handleBackToList}
      />
    )
  }

  const moduleStepMap: Record<WorkflowModule, number> = {
    research: 0,
    trial: 1,
    assessment: 2,
    confirmation: 3,
  }

  const columns = [
    {
      title: '路线编号',
      dataIndex: 'route_no',
      key: 'route_no',
      width: 130,
      render: (route_no: string) => (
        <Tag color="purple" style={{ fontFamily: 'monospace' }}>{route_no}</Tag>
      ),
    },
    {
      title: '路线名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (name: string, record: RouteDevelopment) => (
        <div>
          <div style={{ fontWeight: 500 }}>{name}</div>
          {record.description && (
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{record.description}</div>
          )}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: RouteStatus) => {
        const map: Record<string, { color: string; label: string }> = {
          planning: { color: 'default', label: '计划中' },
          in_progress: { color: 'processing', label: '进行中' },
          completed: { color: 'success', label: '已完成' },
          failed: { color: 'error', label: '失败' },
        }
        return <Tag color={map[status]?.color}>{map[status]?.label}</Tag>
      },
    },
    {
      title: '进度',
      key: 'progress',
      width: 200,
      render: (_: unknown, record: RouteDevelopment) => {
        const saved = savedWorkflows.get(record.id)
        const step = saved?.step ?? moduleStepMap[record.current_module] ?? 0
        const percent = Math.round((step / 4) * 100)
        const stepNames = ['文献解析', '实验录入', '四维度评估', '路线确认']
        return (
          <Tooltip title={saved ? `上次保存: ${new Date(saved.updatedAt).toLocaleString('zh-CN')}` : ''}>
            <Progress 
              percent={percent} 
              size="small" 
              format={() => stepNames[step] || '未开始'}
              status={record.status === 'completed' ? 'success' : 'active'}
            />
          </Tooltip>
        )
      },
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      key: 'created_by',
      width: 100,
      render: (created_by: string) => created_by ? '研发人员' : '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (date: string) => date?.split('T')[0],
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: RouteDevelopment) => {
        const hasSaved = savedWorkflows.has(record.id)
        return (
          <Space>
            <Button 
              type="link" 
              size="small" 
              icon={<PlayCircleOutlined />} 
              onClick={() => handleContinueWorkflow(record)}
              disabled={record.status === 'completed'}
            >
              {hasSaved ? '继续' : '开始'}
            </Button>
            <Popconfirm
              title="确认删除"
              description="删除后无法恢复，确认删除？"
              onConfirm={async () => {
                try {
                  await deleteRoute(record.id)
                  localStorage.removeItem(`workflow-${record.id}`)
                  setSavedWorkflows(prev => {
                    const next = new Map(prev)
                    next.delete(record.id)
                    return next
                  })
                  loadRoutes()
                  message.success('已删除')
                } catch {
                  message.error('删除失败')
                }
              }}
              okText="确定"
              cancelText="取消"
            >
              <Button 
                type="link" 
                size="small" 
                danger
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
            {hasSaved && (
              <Tag color="orange" style={{ fontSize: 11 }}>有未完成的进度</Tag>
            )}
          </Space>
        )
      },
    },
  ]

  return (
    <div>
      {false && (
        <Alert
          title="后端服务不可用"
          description="API 服务器未启动，当前显示的是空数据。工作流功能仍可正常使用，数据保存在浏览器本地。"
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Card title="📎 创建新工作流" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 500, marginBottom: 8 }}>上传文献或输入文献信息</div>
          <Upload.Dragger
            multiple
            accept=".pdf,.txt,.doc,.docx,.md,.markdown,.rtf"
            fileList={fileList}
            beforeUpload={() => false}
            onChange={({ fileList: newFileList }) => {
              setFileList(newFileList)
              if (newFileList.length > 0 && !literatureInput) {
                setLiteratureInput(newFileList[0].name || '')
              }
            }}
            maxCount={10}
            style={{ marginBottom: 16 }}
          >
            <p className="ant-upload-drag-icon">
              <FilePdfOutlined style={{ fontSize: 48, color: '#1890ff' }} />
            </p>
            <p className="ant-upload-text">点击或拖拽文献PDF到此处</p>
            <p className="ant-upload-hint">
              支持格式：PDF、Word、TXT、Markdown、RTF（≤10篇）、DOI、PMID、文献标题
            </p>
          </Upload.Dragger>

          <Input.TextArea
            rows={2}
            placeholder="或输入文献信息（DOI、PMID、标题等）"
            value={literatureInput}
            onChange={(e) => setLiteratureInput(e.target.value)}
            style={{ marginBottom: 16, marginTop: 16 }}
          />

          {fileList.length > 0 && (
            <Alert
              title={`✓ 已选择 ${fileList.length} 个文件`}
              description={fileList.map(f => f.name).join('、')}
              type="success"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          <Button
            type="primary"
            icon={<UploadOutlined />}
            onClick={handleCreateWorkflow}
            size="large"
            loading={creating}
            disabled={creating || (fileList.length === 0 && !literatureInput)}
          >
            🚀 创建工作流并开始解析
          </Button>
        </div>
      </Card>

      <Card title="已有路线">
        <Table
          columns={columns}
          dataSource={routes}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1100 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, ps) => {
              setPage(p)
              if (ps) setPageSize(ps)
            },
          }}
        />
      </Card>
    </div>
  )
}
