'use client'

import { useState, useCallback, useEffect } from 'react'
import { App, Button, Table, Space, Popconfirm, Input, Tag, Tooltip, Select } from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
  DeleteOutlined,
  EyeOutlined,
  SyncOutlined,
  SendOutlined,
  FilePdfOutlined,
} from '@ant-design/icons'
import { PositionTransferRecord } from '@/types/hr'
import { fetchPositionTransfers } from '@/lib/api/client/hr'
import {
  deletePositionTransfer,
  syncPositionTransferFromFeishuAction,
  submitPositionTransferApproval,
} from '@/actions/hr'
import PositionTransferForm from './PositionTransferForm'
import PositionTransferDetailDrawer from './PositionTransferDetailDrawer'
import { usePermission } from '@/hooks/usePermission'

interface PositionTransferClientProps {
  initialRecords: PositionTransferRecord[]
  initialTotal: number
}

const approvalStatusColorMap: Record<string, string> = {
  草稿: 'default',
  待审批: 'processing',
  已通过: 'success',
  已拒绝: 'error',
}

export default function PositionTransferClient({
  initialRecords,
  initialTotal,
}: PositionTransferClientProps) {
  // 编辑权限：仅人力资源部（hr:write）可新增/编辑/删除/提交审批，其他部门只读
  const { has } = usePermission()
  const canEditHr = has('hr:write')
  const { message } = App.useApp()
  const [records, setRecords] = useState<PositionTransferRecord[]>(initialRecords)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [formOpen, setFormOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<PositionTransferRecord | null>(null)
  const [viewingRecord, setViewingRecord] = useState<PositionTransferRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [submitting, setSubmitting] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchPositionTransfers({
        keyword: searchKeyword || undefined,
        approval_status: filterStatus || undefined,
        page,
        page_size: pageSize,
      })
      setRecords(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [searchKeyword, filterStatus, page, pageSize, message])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleRefresh = () => {
    loadData()
  }

  const handleEdit = (record: PositionTransferRecord) => {
    setEditingRecord(record)
    setFormOpen(true)
  }

  const handleView = (record: PositionTransferRecord) => {
    setViewingRecord(record)
    setDetailOpen(true)
  }

  const handleAdd = () => {
    setEditingRecord(null)
    setFormOpen(true)
  }

  const handleFormSuccess = () => {
    loadData()
  }

  const handleDelete = async (id: string) => {
    try {
      await deletePositionTransfer(id)
      message.success('删除成功')
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }

  const handleExportPdf = async (record: PositionTransferRecord) => {
    try {
      const res = await fetch(`/api/v1/hr/position-transfers/${record.id}/export`)
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `内调申请表_${record.employee_name}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    }
  }

  const handleSyncFeishu = async () => {
    setSyncing(true)
    try {
      const res = await syncPositionTransferFromFeishuAction()
      const data = res.data || {}
      const total = data.total ?? 0
      const created = data.created ?? 0
      const updated = data.updated ?? 0
      const deleted = data.deleted ?? 0
      if (total === 0 && deleted === 0) {
        message.info('飞书多维表格暂无数据。新增记录会自动写入飞书。')
      } else {
        const parts = [`新增 ${created} 条`, `更新 ${updated} 条`]
        if (deleted > 0) parts.push(`删除 ${deleted} 条`)
        message.success(`同步完成：${parts.join('，')}`)
      }
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '同步飞书失败')
    } finally {
      setSyncing(false)
    }
  }

  // 根据原职位自动判断主管级别
  const isSupervisorLevel = (position: string | null | undefined): boolean => {
    if (!position) return false
    const supervisorKeywords = ['经理', '总监', '主管', '工程师']
    return supervisorKeywords.some(kw => position.includes(kw))
  }

  const handleSubmitApproval = async (record: PositionTransferRecord) => {
    setSubmitting(record.id)
    try {
      const supervisor = isSupervisorLevel(record.original_position)
      await submitPositionTransferApproval(record.id, supervisor)
      message.success(`审批已提交（${supervisor ? '主管级' : '非主管级'}流程）`)
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '提交审批失败')
    } finally {
      setSubmitting(null)
    }
  }

  useEffect(() => {
    queueMicrotask(loadData)
  }, [searchKeyword, filterStatus, page, pageSize, loadData])

  const getCurrentNodeLabel = (record: PositionTransferRecord): string => {
    const flow = record.approval_flow
    if (!flow?.steps || flow.current_step >= flow.steps.length) {
      return record.approval_status === '已通过' ? '(已完成)' : ''
    }
    const step = flow.steps[flow.current_step]
    return step.signer ? `(${step.label}-${step.signer})` : `(${step.label})`
  }

  const columns = [
    {
      title: '申请日期',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 90,
      render: (text: string) => text ? new Date(text).toLocaleDateString('zh-CN') : '-',
    },
    {
      title: '申请人',
      dataIndex: 'employee_name',
      key: 'employee_name',
      width: 70,
      fixed: 'left' as const,
      render: (text: string, record: PositionTransferRecord) => (
        <a
          onClick={() => handleView(record)}
          className="text-blue-600 hover:text-blue-800 cursor-pointer"
        >
          {text}
        </a>
      ),
    },
    {
      title: '原部门',
      dataIndex: 'department_before',
      key: 'department_before',
      width: 90,
    },
    {
      title: '原职位',
      dataIndex: 'original_position',
      key: 'original_position',
      width: 80,
    },
    {
      title: '生效日期',
      dataIndex: 'effective_date',
      key: 'effective_date',
      width: 90,
    },
    {
      title: '申请部门',
      dataIndex: 'apply_department',
      key: 'apply_department',
      width: 90,
    },
    {
      title: '申请职位',
      dataIndex: 'apply_position',
      key: 'apply_position',
      width: 80,
    },
    {
      title: '联系电话',
      dataIndex: 'contact_phone',
      key: 'contact_phone',
      width: 100,
    },
    {
      title: '申请人确认说明',
      dataIndex: 'applicant_confirmation_text',
      key: 'applicant_confirmation_text',
      width: 200,
      ellipsis: { showTitle: false },
      render: (text: string) => text ? <Tooltip title={text}>{text}</Tooltip> : '-',
    },
    {
      title: '申请人签名',
      dataIndex: 'applicant_signature',
      key: 'applicant_signature',
      width: 80,
    },
    {
      title: '确认日期',
      dataIndex: 'applicant_confirmation_date',
      key: 'applicant_confirmation_date',
      width: 90,
    },
    {
      title: '审批状态',
      dataIndex: 'approval_status',
      key: 'approval_status',
      width: 140,
      render: (status: string, record: PositionTransferRecord) => {
        const currentNode = getCurrentNodeLabel(record)
        return (
          <div className="flex items-center gap-1">
            <Tag color={approvalStatusColorMap[status] || 'default'}>{status}</Tag>
            {currentNode && (
              <span className="text-gray-500 text-xs">{currentNode}</span>
            )}
          </div>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      fixed: 'right' as const,
      render: (_: any, record: PositionTransferRecord) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => handleView(record)}
            />
          </Tooltip>
          {canEditHr ? (
            <>
              <Tooltip title="编辑">
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => handleEdit(record)}
                />
              </Tooltip>
              {record.approval_status === '草稿' && (
                <Tooltip title="提交审批">
                  <Button
                    type="text"
                    size="small"
                    icon={<SendOutlined />}
                    loading={submitting === record.id}
                    style={{ color: 'var(--color-primary)' }}
                    onClick={() => handleSubmitApproval(record)}
                  />
                </Tooltip>
              )}
              <Popconfirm
                title="确认删除"
                description="确定要删除该岗位调动记录吗？"
                onConfirm={() => handleDelete(record.id)}
                okText="确定"
                cancelText="取消"
              >
                <Tooltip title="删除">
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                </Tooltip>
              </Popconfirm>
            </>
          ) : null}
          <Tooltip title="导出审批">
            <Button
              type="text"
              size="small"
              icon={<FilePdfOutlined />}
              style={{ color: '#cc0000' }}
              onClick={() => handleExportPdf(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">岗位调动管理</h1>
        {canEditHr ? (
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新增调动记录
          </Button>
        ) : null}
        {canEditHr ? (
          <Button icon={<SyncOutlined spin={syncing} />} loading={syncing} onClick={handleSyncFeishu}>
            同步飞书
          </Button>
        ) : null}
      </div>

      <div className="flex flex-nowrap gap-2 items-center">
        <Input
          placeholder="姓名/工号"
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          prefix={<SearchOutlined />}
          style={{ width: 130 }}
          allowClear
        />
        <Select
          placeholder="审批状态"
          value={filterStatus || undefined}
          onChange={(value) => setFilterStatus(value || '')}
          allowClear
          style={{ width: 100 }}
          options={[
            { value: '草稿', label: '草稿' },
            { value: '待审批', label: '待审批' },
            { value: '已通过', label: '已通过' },
            { value: '已拒绝', label: '已拒绝' },
          ]}
        />
      </div>

      <Table
        columns={columns}
        dataSource={records}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: handlePageChange,
        }}
        scroll={{ x: 1400 }}
        size="small"
      />

      <PositionTransferForm
        open={formOpen}
        record={editingRecord}
        onClose={() => setFormOpen(false)}
        onSuccess={handleFormSuccess}
      />

      <PositionTransferDetailDrawer
        open={detailOpen}
        record={viewingRecord}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  )
}
