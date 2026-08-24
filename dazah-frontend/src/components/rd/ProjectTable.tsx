'use client'

import { useCallback } from 'react'
import { App, Table, Tag, Space, Button, Input, Select, Modal } from 'antd'
import { EditOutlined, DeleteOutlined, SearchOutlined } from '@ant-design/icons'
import { ResearchProject, ResearchProjectStage, ResearchProjectStatus } from '@/types/rd'
import { useResearchStore } from '@/stores/rd'
import { deleteResearchProject } from '@/actions/rd'

const stageConfig: Record<ResearchProjectStage, { color: string; bgColor: string }> = {
  '立项': { color: '#1677ff', bgColor: '#e6f4ff' },
  '研发中试': { color: '#7b3ff2', bgColor: '#e6e0f5' },
  '验证': { color: '#dd5b00', bgColor: '#fff7e6' },
  '注册': { color: '#13c2c2', bgColor: '#e6fffb' },
  '商业化': { color: '#1aae39', bgColor: '#e6f7e6' }
}

const statusConfig: Record<ResearchProjectStatus, { color: string; bgColor: string }> = {
  '进行中': { color: '#1aae39', bgColor: '#e6f7e6' },
  '已暂停': { color: '#dd5b00', bgColor: '#fff7e6' },
  '已完成': { color: '#787671', bgColor: '#f0eeec' },
  '已终止': { color: '#e03131', bgColor: '#fff1f0' }
}

const stageOptions = Object.keys(stageConfig).map((value) => ({
  label: value,
  value
}))

const statusOptions = Object.keys(statusConfig).map((value) => ({
  label: value,
  value
}))

interface ProjectTableProps {
  loading?: boolean
  onRefresh?: () => void
}

export function ProjectTable({ loading = false, onRefresh }: ProjectTableProps) {
  const { message, modal } = App.useApp()

  const {
    projects,
    total,
    page,
    pageSize,
    stageFilter,
    statusFilter,
    keyword,
    setPage,
    setPageSize,
    setStageFilter,
    setStatusFilter,
    setKeyword,
    openDrawer
  } = useResearchStore()

  const handleDelete = useCallback((record: ResearchProject) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除项目 "${record.name}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteResearchProject(record.id)
          message.success('删除成功')
          onRefresh?.()
        } catch (error) {
          message.error(error?.message || '删除失败')
        }
      }
    })
  }, [message, onRefresh])

  const columns = [
    {
      title: '项目编号',
      dataIndex: 'project_no',
      key: 'project_no',
      width: 130,
      fixed: 'start' as const
    },
    {
      title: '项目名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      fixed: 'start' as const
    },
    {
      title: '项目类型',
      dataIndex: 'project_type',
      key: 'project_type',
      width: 120,
      render: (v: string | null) => v || '-'
    },
    {
      title: '项目阶段',
      dataIndex: 'stage',
      key: 'stage',
      width: 100,
      render: (stage: ResearchProjectStage) => {
        const config = stageConfig[stage] || { color: '#787671', bgColor: '#f0eeec' }
        return (
          <Tag style={{ color: config.color, background: config.bgColor, border: 'none', borderRadius: 4, fontWeight: 500 }}>
            {stage}
          </Tag>
        )
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: ResearchProjectStatus) => {
        const config = statusConfig[status] || { color: '#787671', bgColor: '#f0eeec' }
        return (
          <Tag style={{ color: config.color, background: config.bgColor, border: 'none', borderRadius: 4, fontWeight: 500 }}>
            {status}
          </Tag>
        )
      }
    },
    {
      title: '负责人',
      dataIndex: 'leader',
      key: 'leader',
      width: 100,
      render: (v: string | null) => v || '-'
    },
    {
      title: '开始日期',
      dataIndex: 'start_date',
      key: 'start_date',
      width: 110,
      render: (v: string | null) => v || '-'
    },
    {
      title: '结束日期',
      dataIndex: 'end_date',
      key: 'end_date',
      width: 110,
      render: (v: string | null) => v || '-'
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
      fixed: 'end' as const,
      render: (_: unknown, record: ResearchProject) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => openDrawer(record)} style={{ padding: 0 }}>
            编辑
          </Button>
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} style={{ padding: 0 }}>
            删除
          </Button>
        </Space>
      )
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
        <Select
          placeholder="项目阶段"
          allowClear
          style={{ width: 120 }}
          value={stageFilter || undefined}
          onChange={(value) => setStageFilter(value || '')}
          options={stageOptions}
        />
        <Select
          placeholder="项目状态"
          allowClear
          style={{ width: 120 }}
          value={statusFilter || undefined}
          onChange={(value) => setStatusFilter(value || '')}
          options={statusOptions}
        />
        <Input
          placeholder="搜索编号或名称"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 240 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          allowClear
        />
      </div>
      <Table
        columns={columns}
        dataSource={projects}
        rowKey="id"
        size="small"
        loading={loading}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize: pageSize,
          total: total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (newPage, newPageSize) => {
            setPage(newPage)
            setPageSize(newPageSize)
          }
        }}
      />
    </div>
  )
}
