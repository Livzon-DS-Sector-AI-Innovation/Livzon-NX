'use client'

import { TableEmptyState } from './TableEmptyState'

import { useCallback, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { App, Button, DatePicker, Descriptions, Form, Input, Modal, Select, Space, Table, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { DeleteOutlined, EditOutlined, ExportOutlined, EyeOutlined, FilterOutlined, ImportOutlined, PlusOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs, { Dayjs } from 'dayjs'
import { ChangeListItem } from '@/types/quality'
import { useChangeStore } from '@/stores/quality'
import { fetchChangeActionPlansByChange, fetchDepartmentContacts } from '@/lib/api/client/quality'

import { batchDeleteChanges, createChange, deleteChange, updateChange } from '@/actions/quality-change'
import { fetchNextChangeCode } from '@/lib/api/client/quality'
import { ChangeImportDrawer } from './ChangeImportDrawer'

interface ChangeTableProps {
  changes: ChangeListItem[]
  total: number
  loading?: boolean
  showPlans?: boolean
  changeType?: string
}

const changeLevelOptions = [
  { label: '一级', value: '一级' },
  { label: '二级', value: '二级' },
  { label: '三级', value: '三级' },
]

const defaultColumnWidths: Record<string, number> = {
  serial_number: 56,
  change_code: 100,
  applicant_department: 100,
  change_object: 260,
  change_content: 420,
  change_level: 100,
  action: 190,
}

function formatDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

/** 单行截短文本，悬停显示全文 */
function TruncatedCell({ text, maxLen = 40 }: { text: string | null | undefined; maxLen?: number }) {
  const display = text ?? '-'
  if (display.length <= maxLen) {
    return <span>{display}</span>
  }
  return (
    <Tooltip title={display}>
      <span>{display.slice(0, maxLen)}…</span>
    </Tooltip>
  )
}

function ChangeExpandedPlans({ record }: { record: ChangeListItem }) {
  const { data, isLoading } = useQuery({
    queryKey: ['quality-change-plan', 'by-change', record.id],
    queryFn: () => fetchChangeActionPlansByChange(record.id),
    enabled: !!record.id,
  })
  if (isLoading) return <div style={{ padding: 16 }}>加载中...</div>
  const plans = data ?? []
  if (plans.length === 0) return <div style={{ padding: 16, color: '#999' }}>暂无变更计划</div>
  const planCols = [
    { title: '项目名称', dataIndex: 'project_name', width: 200 },
    { title: '涉及工作', dataIndex: 'related_work', width: 280, render: (v: string | null) => v || '-' },
    { title: '总负责人', dataIndex: 'owner_name', width: 120, render: (v: string | null) => v || '-' },
    { title: '状态', dataIndex: 'status', width: 120, render: (v: string | null) => v || '-' },
    { title: '截止时间', dataIndex: 'deadline_date', width: 130, render: (v: string | null) => (v ? new Date(v).toLocaleDateString('zh-CN') : '-') },
  ]
  return (
    <Table
      rowKey="id"
      dataSource={plans}
      columns={planCols}
      size="small"
      pagination={false}
      style={{ margin: '8px 0' }}
    />
  )
}

export function ChangeTable({ changes, total, loading = false, showPlans = true, changeType = 'technical' }: ChangeTableProps) {
  const router = useRouter()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [importOpen, setImportOpen] = useState(false)
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [editingRecord, setEditingRecord] = useState<ChangeListItem | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [detailRecord, setDetailRecord] = useState<ChangeListItem | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [form] = Form.useForm()

  const {
    page,
    pageSize,
    changeCodeFilter,
    applicantDepartmentFilter,
    changeObjectFilter,
    changeLevelFilter,
    applicationDateFrom,
    applicationDateTo,
    plannedApprovalDateFrom,
    plannedApprovalDateTo,
    executionDateFrom,
    executionDateTo,
    closureDateFrom,
    closureDateTo,
    contentKeywordFilter,
    setPage,
    setPageSize,
    setChangeCodeFilter,
    setApplicantDepartmentFilter,
    setChangeObjectFilter,
    setChangeLevelFilter,
    setApplicationDateRange,
    setPlannedApprovalDateRange,
    setExecutionDateRange,
    setClosureDateRange,
    setContentKeywordFilter,
    resetFilters,
  } = useChangeStore()

  const nextSerialNumber = useMemo(() => {
    let maxSerialNumber = 0
    for (const change of changes) {
      const value =
        typeof change.serial_number === 'string'
          ? Number.parseInt(change.serial_number, 10)
          : Number.NaN
      if (!Number.isNaN(value)) {
        maxSerialNumber = Math.max(maxSerialNumber, value)
      }
    }
    return maxSerialNumber > 0 ? String(maxSerialNumber + 1) : '1'
  }, [changes])

  const { data: departmentContacts = [] } = useQuery({
    queryKey: ['quality-department-contacts'],
    queryFn: fetchDepartmentContacts,
  })

  const departmentOptions = useMemo(
    () =>
      Array.from(
        new Set(
          departmentContacts
            .map((contact) => contact.department?.trim())
            .filter((department): department is string => Boolean(department))
        )
      )
        .sort((left, right) => left.localeCompare(right, 'zh-CN'))
        .map((department) => ({ label: department, value: department })),
    [departmentContacts]
  )

  const applicationRangeValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!applicationDateFrom || !applicationDateTo) return null
    return [dayjs(applicationDateFrom), dayjs(applicationDateTo)]
  }, [applicationDateFrom, applicationDateTo])

  const plannedApprovalRangeValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!plannedApprovalDateFrom || !plannedApprovalDateTo) return null
    return [dayjs(plannedApprovalDateFrom), dayjs(plannedApprovalDateTo)]
  }, [plannedApprovalDateFrom, plannedApprovalDateTo])

  const executionRangeValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!executionDateFrom || !executionDateTo) return null
    return [dayjs(executionDateFrom), dayjs(executionDateTo)]
  }, [executionDateFrom, executionDateTo])

  const closureRangeValue = useMemo<[Dayjs, Dayjs] | null>(() => {
    if (!closureDateFrom || !closureDateTo) return null
    return [dayjs(closureDateFrom), dayjs(closureDateTo)]
  }, [closureDateFrom, closureDateTo])

  const handleDelete = useCallback((record: ChangeListItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除变更 "${record.change_code}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteChange(record.id)
          message.success('删除成功')
          queryClient.invalidateQueries({ queryKey: ['quality-change'] })
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }, [message, modal, queryClient])

  const handleBatchDelete = useCallback(() => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要删除的记录')
      return
    }
    modal.confirm({
      title: '确认批量删除',
      content: `确定要删除选中的 ${selectedRowKeys.length} 条变更记录吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const result = await batchDeleteChanges(selectedRowKeys)
          message.success(`已删除 ${result.deleted || 0} 条记录`)
          setSelectedRowKeys([])
          queryClient.invalidateQueries({ queryKey: ['quality-change'] })
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '批量删除失败'))
        }
      },
    })
  }, [message, modal, queryClient, selectedRowKeys])

  const handleExport = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (changeCodeFilter) params.set('change_code', changeCodeFilter)
      if (applicantDepartmentFilter) params.set('applicant_department', applicantDepartmentFilter)
      if (changeObjectFilter) params.set('change_object', changeObjectFilter)
      if (changeLevelFilter) params.set('change_level', changeLevelFilter)
      if (applicationDateFrom) params.set('application_date_from', applicationDateFrom)
      if (applicationDateTo) params.set('application_date_to', applicationDateTo)
      if (plannedApprovalDateFrom) params.set('planned_approval_date_from', plannedApprovalDateFrom)
      if (plannedApprovalDateTo) params.set('planned_approval_date_to', plannedApprovalDateTo)
      if (executionDateFrom) params.set('execution_date_from', executionDateFrom)
      if (executionDateTo) params.set('execution_date_to', executionDateTo)
      if (closureDateFrom) params.set('closure_date_from', closureDateFrom)
      if (closureDateTo) params.set('closure_date_to', closureDateTo)
      if (contentKeywordFilter) params.set('content_keyword', contentKeywordFilter)
      if (changeType) params.set('change_type', changeType)
      const res = await fetch(`/api/v1/quality/changes/export?${params.toString()}`)
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${changeType === 'file' ? '文件变更台账' : '技术变更台账'}_${new Date().toISOString().slice(0, 10)}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.success('导出成功')
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '导出失败'))
    }
  }, [
    changeCodeFilter,
    applicantDepartmentFilter,
    changeObjectFilter,
    changeLevelFilter,
    applicationDateFrom,
    applicationDateTo,
    plannedApprovalDateFrom,
    plannedApprovalDateTo,
    executionDateFrom,
    executionDateTo,
    closureDateFrom,
    closureDateTo,
    contentKeywordFilter,
    message,
    changeType,
  ])

  const goToChangePlan = useCallback((record: ChangeListItem) => {
    const params = new URLSearchParams()
    params.set('change_code', record.change_code)
    router.push(`/quality/change/action-plans?${params.toString()}`)
  }, [router])

  const handleExpandRow = useCallback((expanded: boolean, record: ChangeListItem) => {
    if (expanded) {
      setExpandedRowKeys((prev) => [...prev, record.id])
    } else {
      setExpandedRowKeys((prev) => prev.filter((k) => k !== record.id))
    }
  }, [])

  const openCreateModal = useCallback(async () => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ serial_number: nextSerialNumber })
    setEditorOpen(true)
    try {
      const nextChangeCode = await fetchNextChangeCode(changeType)
      form.setFieldsValue({ change_code: nextChangeCode })
    } catch {
      // 获取失败时用户可手动填写
    }
  }, [form, nextSerialNumber, changeType])

  const openEditModal = useCallback((record: ChangeListItem) => {
    setEditingRecord(record)
    form.setFieldsValue({
      serial_number: record.serial_number,
      change_code: record.change_code,
      applicant_department: record.applicant_department,
      change_object: record.change_object,
      change_content: record.change_content,
      impact_assessment: record.impact_assessment,
      change_level: record.change_level,
      application_date: record.application_date ? dayjs(record.application_date) : null,
      planned_approval_date: record.planned_approval_date ? dayjs(record.planned_approval_date) : null,
      execution_date: record.execution_date ? dayjs(record.execution_date) : null,
      closure_date: record.closure_date ? dayjs(record.closure_date) : null,
    })
    setEditorOpen(true)
  }, [form])

  const handleSave = useCallback(async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        ...values,
        change_type: changeType,
        application_date: values.application_date ? values.application_date.format('YYYY-MM-DD') : null,
        planned_approval_date: values.planned_approval_date ? values.planned_approval_date.format('YYYY-MM-DD') : null,
        execution_date: values.execution_date ? values.execution_date.format('YYYY-MM-DD') : null,
        closure_date: values.closure_date ? values.closure_date.format('YYYY-MM-DD') : null,
      }
      setSaving(true)
      if (editingRecord) {
        await updateChange(editingRecord.id, payload)
        message.success('更新成功')
      } else {
        await createChange(payload)
        message.success('创建成功')
      }
      setEditorOpen(false)
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['quality-change'] })
      queryClient.invalidateQueries({ queryKey: ['quality-file-change'] })
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(getErrorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }, [editingRecord, form, message, queryClient, changeType])

  const baseColumns = useMemo<TableColumnsType<ChangeListItem>>(
    () => [
      {
        title: '序号',
        dataIndex: 'serial_number',
        key: 'serial_number',
        width: defaultColumnWidths.serial_number,
        render: (_: unknown, __: unknown, index: number) => (page - 1) * pageSize + index + 1,
      },
      {
        title: '变更控制号',
        dataIndex: 'change_code',
        key: 'change_code',
        width: defaultColumnWidths.change_code,
        render: (value: string) => value,
      },
      ...(showPlans
        ? [{
            title: '计划数',
            dataIndex: 'action_plan_count',
            key: 'action_plan_count',
            width: 80,
            render: (value: number, record: ChangeListItem) => (
              <Button
                type="link"
                style={{ padding: 0 }}
                onClick={(event) => { event.stopPropagation(); goToChangePlan(record) }}
              >
                {value ?? 0}
              </Button>
            ),
          }]
        : []),
      { title: '变更申请部门', dataIndex: 'applicant_department', key: 'applicant_department', width: defaultColumnWidths.applicant_department, render: (v: string | null) => v || '-' },
      {
        title: '变更对象',
        dataIndex: 'change_object',
        key: 'change_object',
        width: defaultColumnWidths.change_object,
        render: (v: string | null) => <TruncatedCell text={v} />,
      },
      {
        title: '变更内容',
        dataIndex: 'change_content',
        key: 'change_content',
        width: defaultColumnWidths.change_content,
        render: (v: string | null) => <TruncatedCell text={v} maxLen={60} />,
      },
      { title: '变更等级', dataIndex: 'change_level', key: 'change_level', width: defaultColumnWidths.change_level, render: (v: string | null) => v || '-' },
      {
        title: '操作',
        key: 'action',
        width: defaultColumnWidths.action,
        fixed: 'right' as const,
        render: (_: unknown, record: ChangeListItem) => (
          <Space>
            <Button type="text" icon={<EyeOutlined />} onClick={(event) => { event.stopPropagation(); setDetailRecord(record); setDetailOpen(true) }}>
              详情
            </Button>
            <Button type="text" icon={<EditOutlined />} onClick={(event) => { event.stopPropagation(); openEditModal(record) }}>
              编辑
            </Button>
            <Button type="text" danger icon={<DeleteOutlined />} onClick={(event) => { event.stopPropagation(); handleDelete(record) }} />
          </Space>
        ),
      },
    ],
    [goToChangePlan, handleDelete, openEditModal, page, pageSize, showPlans]
  )

  // 固定列宽：表格横向滚动宽度 = 可见列宽总和（不含已移除的 4 个日期列）
  const scrollX = useMemo(() => {
    const HIDDEN_COLUMNS = ['application_date', 'planned_approval_date', 'execution_date', 'closure_date']
    let sum = showPlans ? 80 : 0 // 计划数列固定宽 80，隐藏时为 0
    for (const [key, width] of Object.entries(defaultColumnWidths)) {
      if (HIDDEN_COLUMNS.includes(key)) continue
      sum += width
    }
    return sum
  }, [showPlans])

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Input placeholder="变更控制号" style={{ width: 180 }} value={changeCodeFilter} onChange={(e) => setChangeCodeFilter(e.target.value)} allowClear />
        <Input placeholder="变更申请部门" style={{ width: 180 }} value={applicantDepartmentFilter} onChange={(e) => setApplicantDepartmentFilter(e.target.value)} allowClear />
        <Input placeholder="变更对象" style={{ width: 180 }} value={changeObjectFilter} onChange={(e) => setChangeObjectFilter(e.target.value)} allowClear />
        <Select placeholder="变更等级" style={{ width: 120 }} value={changeLevelFilter || undefined} onChange={(value) => setChangeLevelFilter(value ?? '')} allowClear options={changeLevelOptions} />
        <DatePicker.RangePicker
          placeholder={['申请日期开始', '申请日期结束']}
          value={applicationRangeValue}
          onChange={(dates) => setApplicationDateRange(dates?.[0] ? dates[0].format('YYYY-MM-DD') : '', dates?.[1] ? dates[1].format('YYYY-MM-DD') : '')}
        />
      </Space>

      <Space wrap style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>新增变更</Button>
        <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>导入</Button>
        <Button icon={<ExportOutlined />} onClick={handleExport}>导出</Button>
        <Button danger onClick={handleBatchDelete}>批量删除</Button>
        <Button icon={<FilterOutlined />} onClick={() => setShowAdvancedFilters((prev) => !prev)}>
          {showAdvancedFilters ? '收起筛选' : '更多筛选'}
        </Button>
        <Button onClick={resetFilters}>重置筛选</Button>
      </Space>

      {showAdvancedFilters ? (
        <Space wrap style={{ marginBottom: 12 }}>
          <Input placeholder="变更内容关键词" style={{ width: 220 }} value={contentKeywordFilter} onChange={(e) => setContentKeywordFilter(e.target.value)} allowClear />
          <DatePicker.RangePicker
            placeholder={['计划批准开始', '计划批准结束']}
            value={plannedApprovalRangeValue}
            onChange={(dates) => setPlannedApprovalDateRange(dates?.[0] ? dates[0].format('YYYY-MM-DD') : '', dates?.[1] ? dates[1].format('YYYY-MM-DD') : '')}
          />
          <DatePicker.RangePicker
            placeholder={['执行开始', '执行结束']}
            value={executionRangeValue}
            onChange={(dates) => setExecutionDateRange(dates?.[0] ? dates[0].format('YYYY-MM-DD') : '', dates?.[1] ? dates[1].format('YYYY-MM-DD') : '')}
          />
          <DatePicker.RangePicker
            placeholder={['关闭开始', '关闭结束']}
            value={closureRangeValue}
            onChange={(dates) => setClosureDateRange(dates?.[0] ? dates[0].format('YYYY-MM-DD') : '', dates?.[1] ? dates[1].format('YYYY-MM-DD') : '')}
          />
        </Space>
      ) : null}

      <Table
        rowKey="id"
        loading={loading}
        dataSource={changes}
        locale={{ emptyText: <TableEmptyState /> }}
        columns={baseColumns}
        rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
        expandable={
          showPlans
            ? {
                expandedRowKeys,
                onExpand: handleExpandRow,
                expandedRowRender: (record: ChangeListItem) => <ChangeExpandedPlans record={record} />,
              }
            : undefined
        }
        onRow={(record) => ({
          onClick: showPlans
            ? (event) => {
                const target = event.target as HTMLElement
                if (
                  target.closest('button') ||
                  target.closest('a') ||
                  target.closest('input') ||
                  target.closest('.ant-checkbox-wrapper') ||
                  target.closest('.ant-table-selection-column') ||
                  target.closest('.ant-table-expand-icon-col') ||
                  target.closest('.ant-table-row-expand-icon')
                ) {
                  return
                }
                goToChangePlan(record)
              }
            : undefined,
          style: { cursor: showPlans ? 'pointer' : undefined },
        })}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (nextPage, nextPageSize) => {
            if (nextPageSize !== pageSize) {
              setPageSize(nextPageSize)
              return
            }
            setPage(nextPage)
          },
        }}
        scroll={{ x: scrollX }}
      />

      <ChangeImportDrawer isOpen={importOpen} onClose={() => setImportOpen(false)} onSuccess={() => queryClient.invalidateQueries({ queryKey: ['quality-change'] })} changeType={changeType} />

      <Modal
        title={editingRecord ? '编辑变更' : '新增变更'}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        width={760}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="序号" name="serial_number">
            <Input />
          </Form.Item>
          <Form.Item label="变更控制号" name="change_code" rules={[{ required: true, message: '请输入变更控制号' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="变更申请部门" name="applicant_department">
            <Select showSearch allowClear placeholder="请选择申请部门" options={departmentOptions} optionFilterProp="label" />
          </Form.Item>
          <Form.Item label="变更对象" name="change_object">
            <Input />
          </Form.Item>
          <Form.Item label="变更内容" name="change_content">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="影响评估" name="impact_assessment">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="变更等级" name="change_level">
            <Select allowClear options={changeLevelOptions} />
          </Form.Item>
          <Form.Item label="变更申请日期" name="application_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="变更计划批准日期" name="planned_approval_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="变更正式执行日期" name="execution_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="变更关闭日期" name="closure_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情模态框 */}
      <Modal
        title="变更详情"
        open={detailOpen}
        onCancel={() => { setDetailOpen(false); setDetailRecord(null) }}
        footer={null}
        width={1000}
        styles={{ body: { maxHeight: '70vh', overflowY: 'auto' } }}
      >
        {detailRecord && (
          <Descriptions column={2} bordered size="middle">
            <Descriptions.Item label="序号">{detailRecord.serial_number || '-'}</Descriptions.Item>
            <Descriptions.Item label="变更控制号">{detailRecord.change_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="变更申请部门">{detailRecord.applicant_department || '-'}</Descriptions.Item>
            <Descriptions.Item label="变更等级">{detailRecord.change_level || '-'}</Descriptions.Item>
            <Descriptions.Item label="变更申请日期">{formatDate(detailRecord.application_date)}</Descriptions.Item>
            <Descriptions.Item label="变更计划批准日期">{formatDate(detailRecord.planned_approval_date)}</Descriptions.Item>
            <Descriptions.Item label="变更正式执行日期">{formatDate(detailRecord.execution_date)}</Descriptions.Item>
            <Descriptions.Item label="变更关闭日期">{formatDate(detailRecord.closure_date)}</Descriptions.Item>
            <Descriptions.Item label="变更对象" span={2}>
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{detailRecord.change_object || '-'}</div>
            </Descriptions.Item>
            <Descriptions.Item label="变更内容" span={2}>
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{detailRecord.change_content || '-'}</div>
            </Descriptions.Item>
            <Descriptions.Item label="影响评估" span={2}>
              <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{detailRecord.impact_assessment || '-'}</div>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  )
}
