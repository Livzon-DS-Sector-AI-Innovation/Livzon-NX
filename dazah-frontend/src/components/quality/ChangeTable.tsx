'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { App, Button, DatePicker, Dropdown, Form, Input, Modal, Select, Space, Table, Tooltip } from 'antd'
import type { MenuProps, TableColumnsType } from 'antd'
import { CloudDownloadOutlined, DeleteOutlined, EditOutlined, ExportOutlined, FilterOutlined } from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import type { ChangeListItem, DepartmentContact } from '@/types/quality'
import { useChangeStore } from '@/stores/quality'
import {
  batchDeleteChanges,
  createChange,
  deleteChange,
  updateChange,
} from '@/actions/quality'
import {
  exportChangeLedger,
  fetchDepartmentContacts,
  fetchNextChangeCode,
} from '@/lib/api/quality'
import { ResizableHeaderCell } from './resizable-table-header'

interface ChangeTableProps {
  loading?: boolean
  onRefresh?: () => void
  onPullFromFeishu?: () => void
  editorOpen?: boolean
  onCloseEditor?: () => void
}

const changeLevelOptions = [
  { label: '轻微变更', value: '轻微变更' },
  { label: '中度变更', value: '中度变更' },
  { label: '重大变更', value: '重大变更' },
]

const COLUMN_WIDTH_STORAGE_KEY = 'quality-change-table-column-widths-v1'

const defaultColumnWidths: Record<string, number> = {
  serial_number: 80,
  change_code: 150,
  applicant_department: 140,
  change_object: 150,
  change_content: 420,
  change_level: 100,
  application_date: 130,
  planned_approval_date: 150,
  execution_date: 150,
  closure_date: 130,
  action: 210,
}

const minColumnWidths: Record<string, number> = {
  serial_number: 60,
  change_code: 120,
  applicant_department: 120,
  change_object: 120,
  change_content: 240,
  change_level: 90,
  application_date: 110,
  planned_approval_date: 120,
  execution_date: 120,
  closure_date: 110,
  action: 180,
}

function formatDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function getStoredColumnWidths(): Record<string, number> {
  if (typeof window === 'undefined') {
    return defaultColumnWidths
  }
  try {
    const raw = window.localStorage.getItem(COLUMN_WIDTH_STORAGE_KEY)
    if (!raw) return defaultColumnWidths
    const saved = JSON.parse(raw) as Record<string, number>
    return { ...defaultColumnWidths, ...saved }
  } catch {
    return defaultColumnWidths
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function ChangeTable({ loading = false, onRefresh, onPullFromFeishu, editorOpen: editorOpenProp, onCloseEditor }: ChangeTableProps) {
  const router = useRouter()
  const { message, modal } = App.useApp()
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(defaultColumnWidths)
  const [columnWidthsReady, setColumnWidthsReady] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ChangeListItem | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [departmentContacts, setDepartmentContacts] = useState<DepartmentContact[]>([])
  const [form] = Form.useForm()

  const {
    changes,
    total,
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

  const openCreateModal = useCallback(async () => {
    setEditingRecord(null)
    form.resetFields()
    form.setFieldsValue({ serial_number: nextSerialNumber })
    try {
      const nextChangeCode = await fetchNextChangeCode()
      form.setFieldsValue({
        serial_number: nextSerialNumber,
        change_code: nextChangeCode,
      })
    } catch (error: unknown) {
      message.warning(getErrorMessage(error, '变更控制号自动编号获取失败，请手动填写'))
    }
  }, [form, message, nextSerialNumber])

  // When parent (ChangePage) opens the create modal, reset the form
  useEffect(() => {
    if (editorOpenProp) {
      void openCreateModal()
    }
  }, [editorOpenProp, openCreateModal])

  useEffect(() => {
    setColumnWidths(getStoredColumnWidths())
    setColumnWidthsReady(true)
  }, [])

  useEffect(() => {
    fetchDepartmentContacts().then(setDepartmentContacts).catch(() => setDepartmentContacts([]))
  }, [])

  useEffect(() => {
    if (!columnWidthsReady) return
    window.localStorage.setItem(COLUMN_WIDTH_STORAGE_KEY, JSON.stringify(columnWidths))
  }, [columnWidths, columnWidthsReady])

  const handleResizeStart = useCallback((columnKey: string, event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidth = columnWidths[columnKey] ?? defaultColumnWidths[columnKey] ?? 120

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX
      const nextWidth = Math.max(minColumnWidths[columnKey] ?? 80, startWidth + delta)
      setColumnWidths((prev) => ({ ...prev, [columnKey]: nextWidth }))
    }

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [columnWidths])

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

  const resetColumnWidths = useCallback(() => {
    setColumnWidths(defaultColumnWidths)
    window.localStorage.removeItem(COLUMN_WIDTH_STORAGE_KEY)
    message.success('已恢复默认列宽')
  }, [message])

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
          onRefresh?.()
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }, [message, modal, onRefresh])

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
          onRefresh?.()
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '批量删除失败'))
        }
      },
    })
  }, [message, modal, onRefresh, selectedRowKeys])

  const buildCurrentFilterParams = useCallback(() => {
    return {
      change_code: changeCodeFilter || undefined,
      applicant_department: applicantDepartmentFilter || undefined,
      change_object: changeObjectFilter || undefined,
      change_level: changeLevelFilter || undefined,
      application_date_from: applicationDateFrom || undefined,
      application_date_to: applicationDateTo || undefined,
      planned_approval_date_from: plannedApprovalDateFrom || undefined,
      planned_approval_date_to: plannedApprovalDateTo || undefined,
      execution_date_from: executionDateFrom || undefined,
      execution_date_to: executionDateTo || undefined,
      closure_date_from: closureDateFrom || undefined,
      closure_date_to: closureDateTo || undefined,
      content_keyword: contentKeywordFilter || undefined,
    }
  }, [
    applicantDepartmentFilter,
    applicationDateFrom,
    applicationDateTo,
    changeCodeFilter,
    changeLevelFilter,
    changeObjectFilter,
    closureDateFrom,
    closureDateTo,
    contentKeywordFilter,
    executionDateFrom,
    executionDateTo,
    plannedApprovalDateFrom,
    plannedApprovalDateTo,
  ])

  const handleExportAll = useCallback(async () => {
    try {
      const { blob, filename } = await exportChangeLedger({
        scope: 'filtered',
        ...buildCurrentFilterParams(),
      })
      downloadBlob(blob, filename)
      message.success('全导出成功')
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '全导出失败'))
    }
  }, [buildCurrentFilterParams, message])

  const handleBatchExport = useCallback(async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择要导出的记录')
      return
    }
    try {
      const { blob, filename } = await exportChangeLedger({
        scope: 'selected',
        change_ids: selectedRowKeys,
      })
      downloadBlob(blob, filename)
      message.success(`已导出 ${selectedRowKeys.length} 条记录`)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '批量导出失败'))
    }
  }, [message, selectedRowKeys])

  const handleSingleExport = useCallback(async (record: ChangeListItem) => {
    try {
      const { blob, filename } = await exportChangeLedger({
        scope: 'single',
        change_id: record.id,
      })
      downloadBlob(blob, filename)
      message.success(`已导出 ${record.change_code}`)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '单条导出失败'))
    }
  }, [message])

  const goToChangePlan = useCallback((record: ChangeListItem) => {
    const params = new URLSearchParams()
    params.set('change_code', record.change_code)
    router.push(`/quality/change/action-plans?${params.toString()}`)
  }, [router])

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
      onCloseEditor?.()
      form.resetFields()
      onRefresh?.()
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(getErrorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }, [editingRecord, form, message, onRefresh])

  const exportMenuItems = useMemo<MenuProps['items']>(
    () => [
      { key: 'batch', label: '批量导出' },
      { key: 'all', label: '全导出' },
    ],
    []
  )

  const handleExportMenuClick = useCallback<NonNullable<MenuProps['onClick']>>(
    ({ key }) => {
      if (key === 'batch') {
        void handleBatchExport()
        return
      }
      void handleExportAll()
    },
    [handleBatchExport, handleExportAll]
  )

  const baseColumns = useMemo<TableColumnsType<ChangeListItem>>(
    () => [
      { title: '序号', dataIndex: 'serial_number', key: 'serial_number', width: defaultColumnWidths.serial_number, render: (v: string | null) => v || '-' },
      {
        title: '变更控制号',
        dataIndex: 'change_code',
        key: 'change_code',
        width: defaultColumnWidths.change_code,
        render: (value: string) => value,
      },
      {
        title: '变更申请部门', dataIndex: 'applicant_department', key: 'applicant_department', width: defaultColumnWidths.applicant_department, render: (v: string | null) => v || '-' },
      { title: '变更对象', dataIndex: 'change_object', key: 'change_object', width: defaultColumnWidths.change_object, render: (v: string | null) => v || '-' },
      {
        title: '变更内容',
        dataIndex: 'change_content',
        key: 'change_content',
        width: defaultColumnWidths.change_content,
        render: (text: string | null) => (
          <Tooltip title={text || '-'}>
            <div style={{ whiteSpace: 'normal', wordBreak: 'break-all', lineHeight: 1.5 }}>{text || '-'}</div>
          </Tooltip>
        ),
      },
      { title: '变更等级', dataIndex: 'change_level', key: 'change_level', width: defaultColumnWidths.change_level, render: (v: string | null) => v || '-' },
      { title: '变更申请日期', dataIndex: 'application_date', key: 'application_date', width: defaultColumnWidths.application_date, render: formatDate },
      { title: '变更计划批准日期', dataIndex: 'planned_approval_date', key: 'planned_approval_date', width: defaultColumnWidths.planned_approval_date, render: formatDate },
      { title: '变更正式执行日期', dataIndex: 'execution_date', key: 'execution_date', width: defaultColumnWidths.execution_date, render: formatDate },
      { title: '变更关闭日期', dataIndex: 'closure_date', key: 'closure_date', width: defaultColumnWidths.closure_date, render: formatDate },
      {
        title: '操作',
        key: 'action',
        width: 210,
        fixed: 'right' as const,
        render: (_: unknown, record: ChangeListItem) => (
          <Space>
            <Button type="text" onClick={(event) => { event.stopPropagation(); goToChangePlan(record) }}>
              变更计划
            </Button>
            <Button type="text" onClick={(event) => { event.stopPropagation(); void handleSingleExport(record) }}>
              导出
            </Button>
            <Button type="text" icon={<EditOutlined />} onClick={(event) => { event.stopPropagation(); openEditModal(record) }} />
            <Button type="text" danger icon={<DeleteOutlined />} onClick={(event) => { event.stopPropagation(); handleDelete(record) }} />
          </Space>
        ),
      },
    ],
    [goToChangePlan, handleDelete, handleSingleExport, openEditModal]
  )

  const columns = useMemo<TableColumnsType<ChangeListItem>>(
    () =>
      baseColumns.map((column) => {
        const dataIndex = 'dataIndex' in column ? column.dataIndex : undefined
        const normalizedDataIndex = Array.isArray(dataIndex) ? dataIndex.join('.') : dataIndex
        const columnKey = String(column.key ?? normalizedDataIndex ?? '')
        const width = columnKey
          ? columnWidths[columnKey] ?? (typeof column.width === 'number' ? column.width : undefined)
          : column.width
        const minWidth = columnKey ? minColumnWidths[columnKey] : undefined
        const canResize = Boolean(columnKey && width)

        return {
          ...column,
          width,
          onHeaderCell: () => ({
            width,
            minWidth,
            resizable: canResize,
            onResizeStart: canResize
              ? (event: React.MouseEvent<HTMLDivElement>) => handleResizeStart(columnKey, event)
              : undefined,
          }),
        }
      }),
    [baseColumns, columnWidths, handleResizeStart]
  )

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Input placeholder="变更控制号" style={{ width: 180 }} value={changeCodeFilter} onChange={(e) => setChangeCodeFilter(e.target.value)} allowClear />
        <Select
          placeholder="变更申请部门"
          style={{ width: 180 }}
          value={applicantDepartmentFilter || undefined}
          onChange={(value) => setApplicantDepartmentFilter(value ?? '')}
          allowClear
          showSearch
          optionFilterProp="label"
          options={departmentOptions}
        />
        <Input placeholder="变更对象" style={{ width: 180 }} value={changeObjectFilter} onChange={(e) => setChangeObjectFilter(e.target.value)} allowClear />
        <Select placeholder="变更等级" style={{ width: 120 }} value={changeLevelFilter || undefined} onChange={(value) => setChangeLevelFilter(value ?? '')} allowClear options={changeLevelOptions} />
        <DatePicker.RangePicker
          placeholder={['申请日期开始', '申请日期结束']}
          value={applicationRangeValue}
          onChange={(dates) => setApplicationDateRange(dates?.[0] ? dates[0].format('YYYY-MM-DD') : '', dates?.[1] ? dates[1].format('YYYY-MM-DD') : '')}
        />
      </Space>

      <div style={{ marginBottom: 12, overflowX: 'auto' }}>
        <Space wrap={false} size={8} style={{ whiteSpace: 'nowrap' }}>
        <Button icon={<CloudDownloadOutlined />} onClick={onPullFromFeishu}>拉取飞书</Button>
        <Dropdown menu={{ items: exportMenuItems, onClick: handleExportMenuClick }}>
          <Button icon={<ExportOutlined />}>导出</Button>
        </Dropdown>
        <Button danger onClick={handleBatchDelete}>批量删除</Button>
        <Button icon={<FilterOutlined />} onClick={() => setShowAdvancedFilters((prev) => !prev)}>
          {showAdvancedFilters ? '收起筛选' : '更多筛选'}
        </Button>
        <Button onClick={resetColumnWidths}>恢复默认列宽</Button>
        <Button onClick={resetFilters}>重置筛选</Button>
        </Space>
      </div>

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
        columns={columns}
        components={{ header: { cell: ResizableHeaderCell } }}
        rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
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
        scroll={{ x: 1800 }}
      />

      <Modal
        title={editingRecord ? '编辑变更' : '新增变更'}
        open={editorOpenProp !== undefined ? editorOpenProp : editorOpen}
        onCancel={() => {
          onCloseEditor?.()
          setEditorOpen(false)
        }}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnHidden
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
            <Select allowClear showSearch optionFilterProp="label" options={departmentOptions} />
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
    </div>
  )
}
