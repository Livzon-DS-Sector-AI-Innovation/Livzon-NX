'use client'

import { useState, useCallback, useEffect } from 'react'
import { Button, Input, Table, Tag, Card, App, Alert, Space, Popconfirm, Select } from 'antd'
import { PlayCircleOutlined, ReloadOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { ProcessOptimizationWorkflowPage } from './ProcessOptimizationWorkflowPage'
import { fetchOptimizations, createOptimization, deleteOptimization } from '@/lib/api/rd'
import { fetchRoutes } from '@/lib/api/rd'
import { ProcessOptimization, OptimizationStatus, OptimizationModule, RouteDevelopment } from '@/types/rd'

interface ProcessOptimizationPageProps {
  initialOptimizations: ProcessOptimization[]
  initialTotal: number
}

const statusMap: Record<string, { color: string; label: string }> = {
  planning: { color: 'default', label: '计划中' },
  in_progress: { color: 'processing', label: '进行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

const moduleMap: Record<string, string> = {
  doe: 'DOE实验设计',
  impurity: '杂质研究',
  crystal: '晶型研究',
  quality: '质量标准',
  scaleup: '公斤级放大',
  report: '报告生成',
}

export function ProcessOptimizationPage({ initialOptimizations, initialTotal }: ProcessOptimizationPageProps) {
  const { message } = App.useApp()
  const [optimizations, setOptimizations] = useState<ProcessOptimization[]>(initialOptimizations)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [workflowOptimization, setWorkflowOptimization] = useState<ProcessOptimization | null>(null)
  const [creating, setCreating] = useState(false)
  const [apiAvailable, setApiAvailable] = useState(true)
  const [savedWorkflows, setSavedWorkflows] = useState<Map<string, { updatedAt: string; step: number }>>(new Map())

  // 创建表单状态
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [selectedRouteId, setSelectedRouteId] = useState<string | undefined>()
  const [availableRoutes, setAvailableRoutes] = useState<RouteDevelopment[]>([])
  const [loadingRoutes, setLoadingRoutes] = useState(false)

  const loadOptimizations = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchOptimizations({ page, page_size: pageSize })
      setOptimizations(result.items)
      setTotal(result.total)
      setApiAvailable(true)
    } catch {
      setApiAvailable(false)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => {
    loadOptimizations()
  }, [loadOptimizations])

  // 加载已保存的工作流状态
  useEffect(() => {
    const saved = new Map<string, { updatedAt: string; step: number }>()
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith('optimization-workflow-')) {
        try {
          const data = JSON.parse(localStorage.getItem(key) || '{}')
          const optId = key.replace('optimization-workflow-', '')
          saved.set(optId, {
            updatedAt: data.updatedAt,
            step: data.currentStep,
          })
        } catch {}
      }
    }
    setSavedWorkflows(saved)
  }, [])

  // 加载可用的打通路线记录
  const loadAvailableRoutes = async () => {
    setLoadingRoutes(true)
    try {
      const result = await fetchRoutes({ status: 'completed', page_size: 100 })
      setAvailableRoutes(result.items)
    } catch {
      setAvailableRoutes([])
    } finally {
      setLoadingRoutes(false)
    }
  }

  // 创建优化任务
  const handleCreateOptimization = async () => {
    if (!newName.trim()) {
      message.warning('请输入优化任务名称')
      return
    }
    if (creating) return
    setCreating(true)

    try {
      const selectedRoute = availableRoutes.find(r => r.id === selectedRouteId)
      const result = await createOptimization({
        project_id: 'project-1',
        name: newName.trim(),
        source_route_id: selectedRouteId,
        source_route_name: selectedRoute?.name,
        description: newDescription.trim(),
      })

      const newOptimization: ProcessOptimization = {
        id: result.id,
        project_id: 'project-1',
        optimization_no: result.optimization_no || `OPT-${Date.now()}`,
        name: newName.trim(),
        source_route_id: selectedRouteId,
        source_route_name: selectedRoute?.name,
        description: newDescription.trim(),
        status: 'in_progress',
        current_module: 'doe',
        start_date: new Date().toISOString().split('T')[0],
        end_date: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        created_by: null,
      }

      setWorkflowOptimization(newOptimization)
      setShowCreateForm(false)
      setNewName('')
      setNewDescription('')
      setSelectedRouteId(undefined)
      message.success('优化任务已创建，开始DOE实验设计')
    } catch (error) {
      message.error('创建失败: ' + (error instanceof Error ? error.message : '未知错误'))
    } finally {
      setCreating(false)
    }
  }

  // 继续已有工作流
  const handleContinueWorkflow = (optimization: ProcessOptimization) => {
    setWorkflowOptimization(optimization)
  }

  // 返回入口页
  const handleBackToList = () => {
    setWorkflowOptimization(null)
    loadOptimizations()
    window.location.reload()
  }

  if (workflowOptimization) {
    return (
      <ProcessOptimizationWorkflowPage
        optimizationId={workflowOptimization.id}
        optimizationName={workflowOptimization.name}
        sourceRouteId={workflowOptimization.source_route_id}
        sourceRouteName={workflowOptimization.source_route_name}
        onComplete={handleBackToList}
        onBack={handleBackToList}
      />
    )
  }

  const columns = [
    {
      title: '编号',
      dataIndex: 'optimization_no',
      key: 'optimization_no',
      width: 140,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '关联路线',
      dataIndex: 'source_route_name',
      key: 'source_route_name',
      width: 150,
      render: (name: string) => name || <span style={{ color: '#999' }}>未关联</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: OptimizationStatus) => {
        const item = statusMap[status]
        return item ? <Tag color={item.color}>{item.label}</Tag> : <Tag>{status}</Tag>
      },
    },
    {
      title: '当前阶段',
      dataIndex: 'current_module',
      key: 'current_module',
      width: 120,
      render: (module: OptimizationModule) => (
        <Tag color="blue">{moduleMap[module] || module}</Tag>
      ),
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
      render: (_: unknown, record: ProcessOptimization) => {
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
                  await deleteOptimization(record.id)
                  localStorage.removeItem(`optimization-workflow-${record.id}`)
                  setSavedWorkflows(prev => {
                    const next = new Map(prev)
                    next.delete(record.id)
                    return next
                  })
                  loadOptimizations()
                  message.success('已删除')
                } catch (error) {
                  // If record is already deleted (404), just refresh and show success
                  if (error instanceof Error && error.message.includes('404')) {
                    loadOptimizations()
                    message.success('记录已删除')
                  } else {
                    message.error('删除失败')
                  }
                }
              }}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
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
      {!apiAvailable && (
        <Alert
          title="后端服务不可用"
          description="API 服务器未启动，当前显示的是空数据。工作流功能仍可正常使用，数据保存在浏览器本地。"
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Card title="🔬 创建新优化任务" style={{ marginBottom: 16 }}>
        {!showCreateForm ? (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            size="large"
            onClick={() => {
              setShowCreateForm(true)
              loadAvailableRoutes()
            }}
          >
            🚀 创建优化任务
          </Button>
        ) : (
          <div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 500, marginBottom: 8 }}>关联上游打通路线（可选）</div>
              <Select
                style={{ width: '100%' }}
                placeholder="选择已完成的打通路线记录"
                allowClear
                loading={loadingRoutes}
                value={selectedRouteId}
                onChange={setSelectedRouteId}
                options={availableRoutes.map(r => ({
                  value: r.id,
                  label: `${r.route_no} - ${r.name}`,
                }))}
                notFoundContent={loadingRoutes ? '加载中...' : '暂无已完成的路线记录'}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 500, marginBottom: 8 }}>优化任务名称 *</div>
              <Input
                placeholder="如：布洛芬工艺优化"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 500, marginBottom: 8 }}>描述</div>
              <Input.TextArea
                rows={2}
                placeholder="优化任务描述（可选）"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </div>

            <Space>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleCreateOptimization}
                loading={creating}
                disabled={creating || !newName.trim()}
              >
                🚀 创建并开始
              </Button>
              <Button onClick={() => {
                setShowCreateForm(false)
                setNewName('')
                setNewDescription('')
                setSelectedRouteId(undefined)
              }}>
                取消
              </Button>
            </Space>
          </div>
        )}
      </Card>

      <Card title="已有优化任务">
        <Table
          columns={columns}
          dataSource={optimizations}
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
