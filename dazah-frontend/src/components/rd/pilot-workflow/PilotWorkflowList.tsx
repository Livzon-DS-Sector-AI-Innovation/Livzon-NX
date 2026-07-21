'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Table, Button, Tag, Space, Input, Select, App, Popconfirm } from 'antd'
import { PlusOutlined, SearchOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  PilotWorkflowListItem,
  PilotWorkflowListResponse,
  PilotWorkflowStatus,
} from '@/types/pilot-workflow'
import { fetchPilotWorkflows } from '@/lib/api/pilot-workflow'
import { deletePilotWorkflow } from '@/actions/rd'

const statusColors: Record<PilotWorkflowStatus, string> = {
  pending: 'default',
  waiting_approval: 'warning',
  running: 'processing',
  completed: 'success',
  failed: 'error',
}

const statusLabels: Record<PilotWorkflowStatus, string> = {
  pending: '待启动',
  waiting_approval: '等待确认',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
}

interface Props {
  initialData: PilotWorkflowListResponse
}

export function PilotWorkflowList({ initialData }: Props) {
  const router = useRouter()
  const { message } = App.useApp()
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [mounted, setMounted] = useState(false)
  const [data, setData] = useState(initialData.items)
  const [total, setTotal] = useState(initialData.total)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')

  useEffect(() => {
    setMounted(true)
  }, [])

  const loadData = async (p: number, kw?: string) => {
    setLoading(true)
    try {
      const result = await fetchPilotWorkflows({
        page: p,
        page_size: 20,
        keyword: kw,
      })
      setData(result.items)
      setTotal(result.total)
      setPage(p)
    } catch (err) {
      console.error('加载失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    setDeletingId(id)
    try {
      await deletePilotWorkflow(id)
      message.success('已删除')
      await loadData(page, keyword)
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeletingId(null)
    }
  }

  const columns: ColumnsType<PilotWorkflowListItem> = [
    {
      title: '产品名称',
      dataIndex: 'product_name',
      key: 'product_name',
      render: (text: string, record: PilotWorkflowListItem) => (
        <a onClick={() => router.push(`/rd/pilot-workflow/${record.id}`)}>
          {text}
        </a>
      ),
    },
    {
      title: '放大倍数',
      dataIndex: 'scale_up_ratio',
      key: 'scale_up_ratio',
      render: (v: number) => `${v}x`,
    },
    {
      title: '设备',
      key: 'equipment',
      render: (_: unknown, record: PilotWorkflowListItem) =>
        `${record.equipment_type} ${record.equipment_volume}L`,
    },
    {
      title: '进度',
      key: 'progress',
      render: (_: unknown, record: PilotWorkflowListItem) =>
        `${record.completed_step_count}/${record.step_count} 步`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: PilotWorkflowStatus) => (
        <Tag color={statusColors[status]}>{statusLabels[status]}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => mounted ? new Date(v).toLocaleString('zh-CN') : v,
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: PilotWorkflowListItem) => {
        return (
          <Popconfirm
            title="确认删除"
            description="删除后不可恢复，确认删除？"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="text"
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={deletingId === record.id}
            />
          </Popconfirm>
        )
      },
    },
  ]

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">中试研究</h1>
        <Space>
          <Input
            placeholder="搜索产品名称"
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={() => loadData(1, keyword)}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 120 }}
            onChange={(v) => loadData(1, undefined)}
            options={[
              { value: 'pending', label: '待启动' },
              { value: 'running', label: '执行中' },
              { value: 'waiting_approval', label: '等待确认' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
            ]}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => router.push('/rd/pilot-workflow/new')}
          >
            新建工作流
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => loadData(p, keyword),
        }}
      />
    </div>
  )
}
