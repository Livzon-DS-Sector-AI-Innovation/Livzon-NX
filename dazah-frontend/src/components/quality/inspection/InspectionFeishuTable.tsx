'use client'

import { TableEmptyState } from '../TableEmptyState'
import { qualityTokens } from '../themeTokens'

import { useState, useEffect } from 'react'
import { Table, Card, Button, Input, Space, Typography, Alert, Select, App, Popconfirm } from 'antd'
import { SyncOutlined, SearchOutlined, FilterOutlined, PlusOutlined } from '@ant-design/icons'
import type { TablePaginationConfig } from 'antd'
import type { ColumnsType, ColumnType } from 'antd/es/table'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteInspectionFeishuRecord, pullInspectionFeishuRecords } from '@/actions/quality-inspection'
import { fetchInspectionFeishuFields } from '@/lib/api/client/quality'
import type { InspectionFeishuFieldMeta } from '@/types/quality'
import { InspectionFeishuRecordModal } from './InspectionFeishuRecordModal'
import { InspectionFeishuRecordDetailDrawer } from './InspectionFeishuRecordDetailDrawer'
import { renderFeishuValue } from './renderFeishuValue'

export interface FilterConfig {
  key: string
  label: string
  type?: 'text' | 'select'
  options?: { label: string; value: string }[]
}

interface Props {
  title: string
  listApi: string
  pullApi?: string
  entityCode?: string
  toolbarContent?: React.ReactNode
  toolbarContainer?: Element | null
  autoColumnPreset?: 'default' | 'finished'
  columns?: ColumnsType<Record<string, unknown>>
  filters?: FilterConfig[]
  editable?: boolean
}

interface FetchResult {
  data: Record<string, unknown>[]
  total: number
  configured: boolean
  serverFields: string[]
  displayFields: string[]
}

export function InspectionFeishuTable({
  title,
  listApi,
  pullApi,
  entityCode,
  toolbarContent,
  toolbarContainer,
  autoColumnPreset = 'default',
  columns,
  filters = [],
  editable = false,
}: Props) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [syncing, setSyncing] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [filterValues, setFilterValues] = useState<Record<string, string>>({})
  const [showFilters, setShowFilters] = useState(false)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 20 })
  const [modalOpen, setModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create')
  const [editingRecord, setEditingRecord] = useState<Record<string, unknown>>()

  const { data: fieldsData } = useQuery<{ fields: InspectionFeishuFieldMeta[]; can_push: boolean } | null>({
    queryKey: ['quality-inspection', 'fields', entityCode],
    queryFn: () => fetchInspectionFeishuFields(entityCode as string),
    enabled: editable && Boolean(entityCode),
  })
  const canPush = fieldsData?.can_push ?? false

  const { data: queryData, isFetching: loading, error } = useQuery<FetchResult>({
    queryKey: ['quality-inspection', 'list', listApi, { page: pagination.page, pageSize: pagination.pageSize, keyword, filterValues, entityCode }],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(pagination.page), page_size: String(pagination.pageSize) })
      if (keyword) params.set('keyword', keyword)
      if (entityCode) params.set('entity_code', entityCode)
      for (const [k, v] of Object.entries(filterValues)) {
        if (v) params.append('filter_' + k, v)
      }
      const res = await fetch(`${listApi}?${params}`)
      const json = await res.json()
      return {
        data: Array.isArray(json.data) ? json.data as Record<string, unknown>[] : [],
        total: json.meta?.total ?? 0,
        configured: json.meta?.configured !== false,
        serverFields: Array.isArray(json.meta?.fields) ? json.meta.fields as string[] : [],
        displayFields: Array.isArray(json.meta?.display_fields) ? json.meta.display_fields as string[] : [],
      }
    },
    placeholderData: (prev) => prev,
  })

  const data = queryData?.data ?? []
  const total = queryData?.total ?? 0
  const configured = queryData?.configured ?? true
  const serverFields = queryData?.serverFields ?? []
  const displayFields = queryData?.displayFields ?? []

  useEffect(() => {
    if (error) {
      message.error('加载数据失败')
    }
  }, [error, message])

  useEffect(() => {
    setKeyword('')
    setFilterValues({})
    setShowFilters(false)
    setPagination({ page: 1, pageSize: 20 })
  }, [entityCode, listApi])

  const handlePull = async () => {
    if (!entityCode) return
    setSyncing(true)
    try {
      const result = await pullInspectionFeishuRecords(entityCode)
      message.success(`已同步 ${result?.synced ?? 0} 条记录`)
      queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', listApi] })
    } catch {
      message.error('同步失败，请检查飞书设置')
    } finally {
      setSyncing(false)
    }
  }

  const openCreate = () => {
    setModalMode('create')
    setEditingRecord(undefined)
    setModalOpen(true)
  }

  const openEdit = (record: Record<string, unknown>) => {
    setModalMode('edit')
    setEditingRecord(record)
    setModalOpen(true)
  }

  const handleDelete = async (record: Record<string, unknown>) => {
    if (!entityCode) return
    try {
      await deleteInspectionFeishuRecord(entityCode, String(record.record_id ?? ''))
      message.success('删除成功，已同步飞书')
      queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', listApi] })
    } catch {
      message.error('删除失败，请检查飞书设置')
    }
  }

  const handleSearch = () => {
    setPagination(prev => ({ ...prev, page: 1 }))
  }

  const handleFilter = (key: string, value: string) => {
    setFilterValues(prev => ({ ...prev, [key]: value }))
    setPagination(prev => ({ ...prev, page: 1 }))
  }

  const handleTableChange = (pag: TablePaginationConfig) => {
    const newPage = pag.current ?? 1
    const newSize = pag.pageSize ?? 20
    setPagination({ page: newPage, pageSize: newSize })
  }

  const getFinishedColumnWidth = (field: string) => {
    const normalized = field.trim()

    if (/^(年|月|日)$/.test(normalized)) return 72
    if (/批号|报告单号/.test(normalized)) return 120
    if (/报告日期|有效期|复验期/.test(normalized)) return 110
    if (/^(kg|桶|Drum|BOU|十亿|kg\/桶|十亿\/桶|kg\/Drum|\+kg\/Drum|BOU\/Drum|X Drum)$/.test(normalized)) return 96
    if (/HPLC|IR|溶液澄清度与颜色|色谱图|图谱|氯化物反应|结晶性|本品为|供试品溶液|对照品溶液/.test(normalized)) return 240
    if (normalized.length >= 28) return 240
    if (normalized.length >= 18) return 200
    if (/杂质|含量|水分|残渣|内毒素|丙酮|甲醇|乙醇|甲苯|仲辛醇|酸度|PH值|阿维菌素|林可霉素/.test(normalized)) return 148
    if (normalized.length <= 4) return 108
    return 136
  }

  const [detailRecord, setDetailRecord] = useState<Record<string, unknown>>()
  const [detailOpen, setDetailOpen] = useState(false)
  const openDetail = (record: Record<string, unknown>) => {
    setDetailRecord(record)
    setDetailOpen(true)
  }

  const buildAutoColumn = (field: string): ColumnType<Record<string, unknown>> => {
    const width = autoColumnPreset === 'finished' ? getFinishedColumnWidth(field) : undefined
    const isFinishedPreset = autoColumnPreset === 'finished'

    return {
      title: (
        <div
          style={{
            whiteSpace: 'normal',
            wordBreak: 'break-word',
            lineHeight: 1.35,
            textAlign: isFinishedPreset ? 'center' : 'left',
          }}
        >
          {field}
        </div>
      ),
      dataIndex: field,
      key: field,
      width,
      align: isFinishedPreset ? 'center' : undefined,
      render: (value: unknown, record: Record<string, unknown>) => (
        <div
          style={{
            whiteSpace: 'normal',
            wordBreak: 'break-word',
            lineHeight: 1.35,
            textAlign: isFinishedPreset ? 'center' : 'left',
            width: '100%',
          }}
        >
          {renderFeishuValue(value, record, entityCode, message)}
        </div>
      ),
      onCell: () => ({
        style: {
          whiteSpace: 'normal',
          wordBreak: 'break-word',
          lineHeight: 1.35,
          verticalAlign: 'top',
          textAlign: isFinishedPreset ? 'center' : 'left',
        },
      }),
    }
  }

  const operationColumn: ColumnType<Record<string, unknown>> = {
    title: '操作',
    key: '__operation',
    width: editable ? 160 : 80,
    fixed: 'right',
    render: (_, record) => (
      <Space>
        <Button type="link" size="small" onClick={() => openDetail(record)}>详情</Button>
        {editable && (
          <>
            <Button type="link" size="small" onClick={() => openEdit(record)}>编辑</Button>
            <Popconfirm
              title="删除后无法恢复，确定删除并同步飞书？"
              onConfirm={() => handleDelete(record)}
              okText="删除"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>删除</Button>
            </Popconfirm>
          </>
        )}
      </Space>
    ),
  }

  const columnFields = displayFields.length > 0 ? displayFields : serverFields
  const baseColumns: ColumnsType<Record<string, unknown>> = (columns && columns.length > 0)
    ? columns
    : columnFields.map(buildAutoColumn)
  const tableColumns: ColumnsType<Record<string, unknown>> = [...baseColumns, operationColumn]

  const tableScrollX = tableColumns.every((column) => typeof column.width === 'number')
    ? tableColumns.reduce((sum, column) => sum + Number(column.width), 0)
    : 'max-content'

  const toolbarNode = (
    <>
      <div style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="搜索..."
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 200 }}
          />
          {toolbarContent}
          {filters.length > 0 && (
            <Button
              icon={<FilterOutlined />}
              onClick={() => setShowFilters(!showFilters)}
              type={showFilters ? 'primary' : 'default'}
            >
              筛选
            </Button>
          )}
          {editable && canPush && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新增
            </Button>
          )}
          {pullApi && entityCode && (
            <Button type="primary" icon={<SyncOutlined />} onClick={handlePull} loading={syncing}>
              同步飞书数据
            </Button>
          )}
        </Space>
      </div>
      {showFilters && filters.length > 0 && (
        <Card size="small" style={{ marginBottom: 16, background: qualityTokens.bgSoft }}>
          <Space wrap>
            {filters.map(f => (
              <Space key={f.key} size={4}>
                <span style={{ fontSize: 13 }}>{f.label}:</span>
                {f.type === 'select' && f.options ? (
                  <Select
                    allowClear
                    placeholder={f.label}
                    value={filterValues[f.key] || undefined}
                    onChange={val => handleFilter(f.key, val ?? '')}
                    style={{ width: 140 }}
                    options={f.options}
                  />
                ) : (
                  <Input
                    allowClear
                    placeholder={f.label}
                    value={filterValues[f.key] || ''}
                    onChange={e => handleFilter(f.key, e.target.value)}
                    style={{ width: 140 }}
                  />
                )}
              </Space>
            ))}
            <Button onClick={() => { setFilterValues({}); setPagination(prev => ({ ...prev, page: 1 })) }}>
              清除筛选
            </Button>
          </Space>
        </Card>
      )}
    </>
  )

  return (
    <div style={{ padding: 24 }}>
      {toolbarContainer ? null : toolbarNode}
      {toolbarContainer ? createPortal(toolbarNode, toolbarContainer) : null}
      <Card title={<Typography.Title level={5} style={{ margin: 0 }}>{title}</Typography.Title>}>
        {!configured && (
          <Alert
            title="飞书数据源未配置"
            description="请在左侧导航栏「质量管理 -> 飞书设置」中配置飞书应用凭证和实体映射。"
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        <Table
          rowKey="record_id"
          dataSource={data}
          locale={{
            emptyText: (
              <TableEmptyState
                hasFilters={Boolean(keyword || Object.keys(filterValues).length)}
                hasError={!configured}
                errorMessage="飞书数据源未配置，请在「质量管理 -> 飞书设置」完成配置后查看数据"
              />
            ),
          }}
          columns={tableColumns}
          loading={loading}
          size={autoColumnPreset === 'finished' ? 'small' : 'middle'}
          pagination={{
            current: pagination.page,
            pageSize: pagination.pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={handleTableChange}
          scroll={{ x: tableScrollX }}
          tableLayout={autoColumnPreset === 'finished' ? 'fixed' : undefined}
        />
      </Card>
      {editable && entityCode && (
        <InspectionFeishuRecordModal
          open={modalOpen}
          entityCode={entityCode}
          mode={modalMode}
          initialValues={editingRecord}
          onClose={() => setModalOpen(false)}
          onSuccess={() =>
            queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', listApi] })
          }
        />
      )}
      <InspectionFeishuRecordDetailDrawer
        open={detailOpen}
        entityCode={entityCode}
        record={detailRecord}
        allFields={serverFields}
        onClose={() => setDetailOpen(false)}
      />
    </div>
  )
}
