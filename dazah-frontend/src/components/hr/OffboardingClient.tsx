'use client'

import { useState, useCallback, useEffect } from 'react'
import { App, Button, Table, Space, Popconfirm, Input, Tag, Tooltip, Select, AutoComplete, DatePicker } from 'antd'
import { PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined, EyeOutlined, SyncOutlined, FileTextOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { OffboardingRecord } from '@/types/hr'
import { fetchOffboardingRecordsAction, deleteOffboardingRecord, syncOffboardingFromFeishuAction, updateOffboardingRecord, generateOffboardingCertificateAction } from '@/actions/hr'
import OffboardingForm from './OffboardingForm'
import OffboardingDetailDrawer from './OffboardingDetailDrawer'
import HrChatbot from './HrChatbot'
import { usePermission } from '@/hooks/usePermission'

interface OffboardingClientProps {
  initialRecords: OffboardingRecord[]
  initialTotal: number
}

export default function OffboardingClient({
  initialRecords,
  initialTotal }: OffboardingClientProps) {
  const { message } = App.useApp()
  // 编辑权限：仅人力资源部（hr:write）可新增/编辑/删除，其他部门只读
  const { has } = usePermission()
  const canEditHr = has('hr:write')
  const [records, setRecords] = useState<OffboardingRecord[]>(initialRecords)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [formOpen, setFormOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<OffboardingRecord | null>(null)
  const [viewingRecord, setViewingRecord] = useState<OffboardingRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [searchKeyword, setSearchKeyword] = useState('')
  const [editingCell, setEditingCell] = useState<{ recordId: string; field: string } | null>(null)
  const [editingReason, setEditingReason] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchOffboardingRecordsAction({
        keyword: searchKeyword || undefined,
        page,
        page_size: pageSize })
      setRecords(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [searchKeyword, page, pageSize, message])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleEdit = (record: OffboardingRecord) => {
    setEditingRecord(record)
    setFormOpen(true)
  }

  const handleView = (record: OffboardingRecord) => {
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
      await deleteOffboardingRecord(id)
      message.success('删除成功')
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }

  const handleGenerateCertificate = async (record: OffboardingRecord) => {
    const result = await generateOffboardingCertificateAction(record.id)
    if (!result.ok || !result.bytes) {
      message.error(result.message || '生成失败')
      return
    }
    try {
      const { bytes, filename } = result
      const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename || '解除劳动合同通知单.docx'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      message.success('离职证明已生成并下载')
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '生成失败')
    }
  }

  const handleSyncFeishu = async () => {
    setSyncing(true)
    try {
      const res = await syncOffboardingFromFeishuAction()
      message.success(res.message || '同步完成')
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '同步飞书失败')
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    queueMicrotask(loadData)
  }, [searchKeyword, page, pageSize, loadData])

  // 离职类型选项（与表单、后端一致）
  const offboardingTypeOptions = [
    { label: '辞职', value: '辞职' },
    { label: '正常离职', value: '正常离职' },
    { label: '补办手续', value: '补办手续' },
    { label: '辞退', value: '辞退' },
    { label: '合同到期', value: '合同到期' },
    { label: '退休', value: '退休' },
    { label: '其他', value: '其他' },
  ]

  // 在职状态选项（页面内联切换；选「离职」触发员工档案转抄）
  const statusOptions = [
    { label: '在职', value: '在职' },
    { label: '离职', value: '离职' },
  ]

  // 离职原因选项（可下拉选择或手动输入；HR 自动转离职的特殊原因不在此列）
  const offboardingReasonOptions = [
    { value: '薪资低' },
    { value: '与领导关系不融洽' },
    { value: '家庭原因' },
  ]

  // 行内编辑处理
  const handleCellEdit = (recordId: string, field: string) => {
    setEditingCell({ recordId, field })
  }

  const handleCellSave = async (recordId: string, field: string, value: string) => {
    try {
      await updateOffboardingRecord(recordId, { [field]: value })
      message.success('更新成功')
      setEditingCell(null)
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '更新失败')
      setEditingCell(null)
    }
  }

  const handleCellCancel = () => {
    setEditingCell(null)
  }

  const typeColorMap: Record<string, string> = {
    正常离职: 'default',
    补办手续: 'orange',
    辞退: 'red',
    合同到期: 'orange',
    退休: 'blue',
    其他: 'purple' }

  // 离职管理核心列（其余字段在详情查看）
  const columns = [
    {
      title: '工号',
      dataIndex: 'employee_number',
      key: 'employee_number',
      width: 110,
      fixed: 'left' as const,
      render: (_: unknown, record: OffboardingRecord) => record.employee_number || record.employee?.employee_number || '-' },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 90,
      fixed: 'left' as const,
      render: (_: unknown, record: OffboardingRecord) => (
        <a onClick={() => handleView(record)} className="text-blue-600 hover:text-blue-800 cursor-pointer">
          {record.name || record.employee?.name || '-'}
        </a>
      ) },
    {
      title: '域账户',
      dataIndex: 'domain_account',
      key: 'domain_account',
      width: 120,
      render: (_: unknown, record: OffboardingRecord) => record.domain_account || record.employee?.domain_account || '-' },
    {
      title: '性别',
      dataIndex: 'gender',
      key: 'gender',
      width: 70,
      render: (_: unknown, record: OffboardingRecord) => record.gender || record.employee?.gender || '-' },
    {
      title: '一级部门',
      dataIndex: 'department',
      key: 'department',
      width: 120,
      render: (_: unknown, record: OffboardingRecord) => record.department || record.employee?.department || '-' },
    {
      title: '二级部门',
      dataIndex: 'sub_department',
      key: 'sub_department',
      width: 120,
      render: (_: unknown, record: OffboardingRecord) => record.sub_department || '-' },
    {
      title: '离职类型',
      dataIndex: 'offboarding_type',
      key: 'offboarding_type',
      width: 100,
      render: (type: string, record: OffboardingRecord) => {
        if (editingCell?.recordId === record.id && editingCell?.field === 'offboarding_type') {
          return (
            <Select
              value={type}
              options={offboardingTypeOptions}
              onChange={(value) => handleCellSave(record.id, 'offboarding_type', value)}
              onBlur={handleCellCancel}
              autoFocus
              style={{ width: '100%' }}
              size="small"
            />
          )
        }
        return (
          <Tag
            color={typeColorMap[type] || 'default'}
            onClick={() => handleCellEdit(record.id, 'offboarding_type')}
            className="cursor-pointer hover:opacity-80"
          >
            {type || '-'}
          </Tag>
        )
      }
    },
    {
      title: '在职状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string, record: OffboardingRecord) => {
        const s = status || record.employee?.status || ''
        if (editingCell?.recordId === record.id && editingCell?.field === 'status') {
          return (
            <Select
              value={s}
              options={statusOptions}
              onChange={(value) => handleCellSave(record.id, 'status', value)}
              onBlur={handleCellCancel}
              autoFocus
              style={{ width: '100%' }}
              size="small"
            />
          )
        }
        return (
          <Tag
            color={s === '离职' ? 'red' : s === '在职' ? 'green' : 'default'}
            onClick={() => handleCellEdit(record.id, 'status')}
            className="cursor-pointer hover:opacity-80"
          >
            {s || '-'}
          </Tag>
        )
      }
    },
    {
      title: '最后工作日',
      dataIndex: 'offboarding_date',
      key: 'offboarding_date',
      width: 120,
      render: (date: string, record: OffboardingRecord) => {
        if (editingCell?.recordId === record.id && editingCell?.field === 'offboarding_date') {
          return (
            <DatePicker
              value={date ? dayjs(date) : null}
              onChange={(d) => handleCellSave(record.id, 'offboarding_date', d ? d.format('YYYY-MM-DD') : '')}
              onBlur={handleCellCancel}
              autoFocus
              style={{ width: '100%' }}
              size="small"
              format="YYYY-MM-DD"
            />
          )
        }
        return (
          <span
            onClick={() => handleCellEdit(record.id, 'offboarding_date')}
            className="cursor-pointer hover:opacity-80"
          >
            {date || '-'}
          </span>
        )
      }
    },
    {
      title: '离职原因',
      dataIndex: 'reason',
      key: 'reason',
      width: 200,
      render: (reason: string, record: OffboardingRecord) => {
        if (editingCell?.recordId === record.id && editingCell?.field === 'reason') {
          return (
            <AutoComplete
              value={editingReason}
              options={offboardingReasonOptions}
              onChange={(value) => setEditingReason(value)}
              onSelect={(value) => handleCellSave(record.id, 'reason', value)}
              onBlur={() => handleCellSave(record.id, 'reason', editingReason)}
              autoFocus
              style={{ width: '100%' }}
              size="small"
              allowClear
            />
          )
        }
        return (
          <Tooltip title={reason}>
            <span
              onClick={() => { handleCellEdit(record.id, 'reason'); setEditingReason(reason || '') }}
              className="cursor-pointer hover:opacity-80 inline-block w-full truncate"
            >
              {reason || '-'}
            </span>
          </Tooltip>
        )
      }
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right' as const,
      render: (_: unknown, record: OffboardingRecord) => (
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
              <Tooltip title="生成离职证明">
                <Button
                  type="text"
                  size="small"
                  icon={<FileTextOutlined />}
                  onClick={() => handleGenerateCertificate(record)}
                />
              </Tooltip>
              <Popconfirm
                title="确认删除"
                description="确定要删除该离职记录吗？"
                onConfirm={() => handleDelete(record.id)}
                okText="确定"
                cancelText="取消"
              >
                <Tooltip title="删除">
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                  />
                </Tooltip>
              </Popconfirm>
            </>
          ) : null}
        </Space>
      ) },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          离职管理
        </h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          新增离职记录
        </Button>
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
          onChange: handlePageChange }}
        scroll={{ x: 1600 }}
        size="small"
      />

      <OffboardingForm
        open={formOpen}
        record={editingRecord}
        onClose={() => setFormOpen(false)}
        onSuccess={handleFormSuccess}
      />

      <OffboardingDetailDrawer
        open={detailOpen}
        record={viewingRecord}
        onClose={() => setDetailOpen(false)}
      />

      <HrChatbot />
    </div>
  )
}
