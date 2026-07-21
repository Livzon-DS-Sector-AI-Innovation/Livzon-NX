'use client'

import { Table, Button, Space, Tag, Popconfirm, App } from 'antd'
import { EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useRouteDevelopmentStore } from '@/stores/rd'
import { deleteRouteAction } from '@/actions/rd'
import { RouteDevelopment, RouteStatus } from '@/types/rd'

interface RouteTableProps {
  routes: RouteDevelopment[]
  loading: boolean
  onEdit: (route: RouteDevelopment) => void
  onRefresh: () => void
}

export function RouteTable({ routes, loading, onEdit, onRefresh }: RouteTableProps) {
  const { message } = App.useApp()

  const handleDelete = async (id: string) => {
    const result = await deleteRouteAction(id)
    if (result.error) {
      message.error(result.error)
      return
    }
    message.success('删除成功')
    onRefresh()
  }

  const columns: ColumnsType<RouteDevelopment> = [
    {
      title: '路线编号',
      dataIndex: 'route_no',
      key: 'route_no',
      width: 120,
    },
    {
      title: '路线名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 100,
      render: (source: string) => {
        const map: Record<string, { color: string; label: string }> = {
          pdf: { color: 'blue', label: 'PDF文献' },
          doi: { color: 'cyan', label: 'DOI' },
          manual: { color: 'default', label: '手动输入' },
        }
        return <Tag color={map[source]?.color}>{map[source]?.label}</Tag>
      },
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
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (date: string) => date?.split('T')[0],
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: unknown, record: RouteDevelopment) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />}>
            查看
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这条路线吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Table
      columns={columns}
      dataSource={routes}
      rowKey="id"
      loading={loading}
      pagination={{
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 条`,
      }}
    />
  )
}
