'use client'

import { useRouter } from 'next/navigation'
import { TableEmptyState } from '../TableEmptyState'
import { qualityTokens } from '../themeTokens'

import { useState, useEffect, useMemo, useRef } from 'react'
import { Table, Card, Button, Input, Space, Typography, Alert, Select, App, Popconfirm, Tag } from 'antd'
import { SyncOutlined, SearchOutlined, FilterOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import type { TablePaginationConfig } from 'antd'
import type { ColumnsType, ColumnType } from 'antd/es/table'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteInspectionFeishuRecord, pullInspectionFeishuRecords } from '@/actions/quality-inspection'
import { fetchInspectionFeishuFields, fetchInspectionFeishuRecordDetail } from '@/lib/api/client/quality'
import type { InspectionFeishuFieldMeta } from '@/types/quality'
import { InspectionFeishuRecordModal } from './InspectionFeishuRecordModal'
import { InspectionFeishuRecordDetailDrawer } from './InspectionFeishuRecordDetailDrawer'
import { InstrumentProfileDrawer } from './InstrumentProfileDrawer'
import {
  InspectionCreateByMaterialModal,
  type InspectionMaterialCreated,
} from './InspectionCreateByMaterialModal'
import { FeishuAttachmentPreviewModal } from '../FeishuAttachmentPreviewModal'
import { renderFeishuValue } from './renderFeishuValue'
import type { FeishuAttachmentPreviewContext, FeishuFieldTypeMap } from './renderFeishuValue'

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
  createLabel?: string
  /** 开启后附件（报告单等文档）点击弹窗在线预览（office 由后端转 PDF） */
  enableAttachmentPreview?: boolean
  /** 开启后工具栏展示镜像最近同步时间（成品页） */
  showLastSyncTime?: boolean
  /** 开启后新增/编辑弹窗里人员字段可搜索选人（写飞书时后端换发 union_id） */
  editablePersonFields?: boolean
  /** 开启后操作列增加「档案」：按设备编号查看维保/维修/校验/合同（仪器台账） */
  enableEquipmentProfile?: boolean
  /** 开启后「新增」改按物料名称/代码选料（固体/液体原辅料） */
  createWithMaterialPicker?: boolean
  /** 选料弹窗的物料范围：固体页只列固体、液体页只列液体 */
  materialPickerModule?: 'solid' | 'liquid'
  /** 跳转携带的新建记录 ID：加载后自动打开该记录详情抽屉 */
  highlightRecordId?: string | null
  /** 跳转携带的物料 entity_code（用于与当前列表实体一致后才打开详情） */
  highlightEntityCode?: string | null
  /** 不展示的列（如无业务含义的关联列「父记录」） */
  hiddenFields?: string[]
  /** 关闭「新增」入口（如库存台账：库存由入库/出库联动，无需手工新增） */
  disableCreate?: boolean
  /** 紧凑换行模式：无横向滚动、列内自动换行、超过 3 行截断（全文看详情） */
  wrapColumns?: boolean
  /** 指定列宽（字段名 -> 宽度，支持 px / 百分比），未指定的列平分剩余空间 */
  columnWidths?: Record<string, number | string>
  /** 表头文字居中 */
  centerHeaders?: boolean
  /** 列显示名覆盖（字段名 -> 表头文字，如 长公式列改短名） */
  columnLabels?: Record<string, string>
  /** 单元格值标记：字段名 -> 值 -> Tag 颜色（如 是否完成 是/否 亮色突出） */
  valueTags?: Record<string, Record<string, { color: string; text?: string }>>
  /** 月份过滤（YYYY-MM，后端按「生成日期」落月）；空串/不传 = 不过滤看全部 */
  monthFilter?: string
  /** 按行动态高亮：字段名 -> (整行) => Tag 配置；返回 null/undefined 正常渲染 */
  cellHighlights?: Record<
    string,
    (record: Record<string, unknown>) => { color: string; text?: string } | null | undefined
  >
}

interface FetchResult {
  data: Record<string, unknown>[]
  total: number
  configured: boolean
  serverFields: string[]
  displayFields: string[]
  fieldMeta: Record<string, string>
  lastSyncTime?: string | null
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
  createLabel = '新增',
  enableAttachmentPreview = false,
  showLastSyncTime = false,
  editablePersonFields = false,
  enableEquipmentProfile = false,
  createWithMaterialPicker = false,
  materialPickerModule,
  highlightRecordId = null,
  highlightEntityCode = null,
  hiddenFields = [],
  disableCreate = false,
  wrapColumns = false,
  columnWidths,
  centerHeaders = false,
  columnLabels,
  valueTags,
  cellHighlights,
  monthFilter = '',
}: Props) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const router = useRouter()
  const [syncing, setSyncing] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [filterValues, setFilterValues] = useState<Record<string, string>>({})
  const [showFilters, setShowFilters] = useState(false)
  const [pagination, setPagination] = useState({ page: 1, pageSize: 20 })
  const [modalOpen, setModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create')
  const [editingRecord, setEditingRecord] = useState<Record<string, unknown>>()
  const [attachmentPreview, setAttachmentPreview] = useState<{
    fileName: string
    previewSrc: string
    downloadSrc: string
  } | null>(null)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const handledHighlightRef = useRef<string | null>(null)

  const openAttachmentPreview = (context: FeishuAttachmentPreviewContext) => {
    const recordId = String(context.record.record_id ?? '')
    const fileToken = String(context.attachment.file_token ?? '')
    const base = `/api/v1/quality/inspection/feishu/${encodeURIComponent(context.entityCode ?? '')}/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fileToken)}`
    setAttachmentPreview({
      fileName: context.attachment.name || '附件',
      previewSrc: `${base}/preview`,
      downloadSrc: `${base}/content`,
    })
  }

  // 字段元数据：供新增/编辑弹窗判断可写入、列按类型渲染（含公式日期序列号换算）
  // 与筛选下拉选项；因此只要有 entityCode 就取，不再限定 editable。
  const { data: fieldsData } = useQuery<{ fields: InspectionFeishuFieldMeta[]; can_push: boolean; form_url?: string | null } | null>({
    queryKey: ['quality-inspection', 'fields', entityCode],
    queryFn: () => fetchInspectionFeishuFields(entityCode as string),
    enabled: Boolean(entityCode),
  })
  const canPush = fieldsData?.can_push ?? false
  const formUrl = fieldsData?.form_url ?? null
  const fieldMetaMap = useMemo<FeishuFieldTypeMap>(() => {
    const map: FeishuFieldTypeMap = {}
    for (const field of fieldsData?.fields ?? []) {
      map[field.field_name] = {
        uiType: field.ui_type,
        resultUiType: field.result_ui_type ?? undefined,
      }
    }
    return map
  }, [fieldsData])
  // 单选/多选字段的可选项（筛选下拉用；公式派生列没有选项时回退文本筛选）
  const fieldOptionsMap = useMemo(() => {
    const map: Record<string, { label: string; value: string }[]> = {}
    for (const field of fieldsData?.fields ?? []) {
      if (field.options && field.options.length > 0) {
        map[field.field_name] = field.options.map(option => ({
          label: option.name,
          value: option.name,
        }))
      }
    }
    return map
  }, [fieldsData])

  const { data: queryData, isFetching: loading, error } = useQuery<FetchResult>({
    queryKey: ['quality-inspection', 'list', listApi, { page: pagination.page, pageSize: pagination.pageSize, keyword, filterValues, entityCode, monthFilter }],
    queryFn: async () => {
      const params = new URLSearchParams({ page: String(pagination.page), page_size: String(pagination.pageSize) })
      if (keyword) params.set('keyword', keyword)
      if (entityCode) params.set('entity_code', entityCode)
      if (monthFilter) params.set('month', monthFilter)
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
        fieldMeta: (json.meta?.fieldMeta && typeof json.meta.fieldMeta === 'object'
          ? json.meta.fieldMeta as Record<string, string>
          : {}),
        lastSyncTime: typeof json.meta?.last_sync_time === 'string' ? json.meta.last_sync_time : null,
      }
    },
    placeholderData: (prev) => prev,
  })

  const data = queryData?.data ?? []
  const total = queryData?.total ?? 0
  const configured = queryData?.configured ?? true
  const serverFields = queryData?.serverFields ?? []
  const displayFields = queryData?.displayFields ?? []
  const fieldMeta = queryData?.fieldMeta ?? {}
  const lastSyncTime = queryData?.lastSyncTime ?? null

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

  // 切换月份（含清空=全部）回到第一页：渲染期同步调整状态，避免副作用级联
  const [lastMonthFilter, setLastMonthFilter] = useState(monthFilter)
  if (lastMonthFilter !== monthFilter) {
    setLastMonthFilter(monthFilter)
    setPagination(prev => (prev.page === 1 ? prev : { ...prev, page: 1 }))
  }

  const handlePull = async () => {
    if (!entityCode) return
    setSyncing(true)
    try {
      let synced = 0
      if (pullApi) {
        const res = await fetch(pullApi, { method: 'POST' })
        const json = await res.json()
        synced = json?.data?.synced ?? 0
      } else {
        const result = await pullInspectionFeishuRecords(entityCode)
        synced = result?.synced ?? 0
      }
      message.success(`已同步 ${synced} 条记录`)
      queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', listApi] })
    } catch {
      message.error('同步失败，请检查飞书设置')
    } finally {
      setSyncing(false)
    }
  }

  /** 刷新：仅重新加载当前列表（读本地镜像最新数据），不回拉飞书。 */
  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', listApi] })
  }

  const openCreate = () => {
    if (createWithMaterialPicker) {
      setCreateModalOpen(true)
      return
    }
    if (formUrl) {
      window.open(formUrl, '_blank', 'noopener,noreferrer')
      return
    }
    setModalMode('create')
    setEditingRecord(undefined)
    setModalOpen(true)
  }

  const handleMaterialCreated = (result: InspectionMaterialCreated) => {
    router.push(
      `/quality/inspection/${result.module}?recordId=${encodeURIComponent(result.recordId)}&entityCode=${encodeURIComponent(result.entityCode)}`
    )
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
  // 仪器档案（enableEquipmentProfile 时操作列「档案」按钮）
  const [profileRecord, setProfileRecord] = useState<Record<string, unknown> | null>(null)
  const openDetail = (record: Record<string, unknown>) => {
    setDetailRecord(record)
    setDetailOpen(true)
  }
  // 详情字段：列表行优先取列表列（保持既有顺序）；直读飞书的记录展示其全部业务字段
  const detailFields = useMemo(() => {
    if (!detailRecord) return serverFields
    const recordKeys = Object.keys(detailRecord).filter(
      key => key !== 'record_id' && key !== 'created_at' && key !== 'updated_at',
    )
    const listed = recordKeys.filter(key => serverFields.includes(key))
    return listed.length > 0 ? listed : recordKeys
  }, [detailRecord, serverFields])

  // 跳转「列表并弹详情」：按 record_id 打开详情抽屉；列表镜像未刷新时直读飞书详情。
  // handledHighlightRef 防重复触发（数据 refetch 不会再次打开）。
  useEffect(() => {
    if (!highlightRecordId) return
    if (handledHighlightRef.current === highlightRecordId) return
    if (highlightEntityCode && highlightEntityCode !== entityCode) return
    const target = data.find((row) => String(row.record_id) === String(highlightRecordId))
    if (target) {
      handledHighlightRef.current = highlightRecordId
      openDetail(target)
      return
    }
    // 列表仍在加载时先等待数据到位，避免对新记录出现前就直读详情
    if (loading) return
    if (!entityCode) return
    let cancelled = false
    fetchInspectionFeishuRecordDetail(entityCode, String(highlightRecordId))
      .then((record) => {
        if (cancelled || !record) return
        handledHighlightRef.current = highlightRecordId
        openDetail(record)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [highlightRecordId, highlightEntityCode, data, entityCode, loading])

  const buildAutoColumn = (field: string): ColumnType<Record<string, unknown>> => {
    const isFinishedPreset = autoColumnPreset === 'finished'
    const width =
      columnWidths?.[field] ??
      (isFinishedPreset ? getFinishedColumnWidth(field) : undefined)

    return {
      title: (
        <div
          style={{
            whiteSpace: 'normal',
            wordBreak: 'break-word',
            lineHeight: 1.35,
            textAlign: centerHeaders || isFinishedPreset ? 'center' : 'left',
          }}
        >
          {columnLabels?.[field] ?? field}
        </div>
      ),
      dataIndex: field,
      key: field,
      width,
      align: isFinishedPreset ? 'center' : undefined,
      render: (value: unknown, record: Record<string, unknown>) => {
        const valueKey = typeof value === 'string' ? value.trim() : ''
        // 按行动态高亮（如 剩余天数 ≤3 红 / ≤7 橙，且仅在未完成时）
        const dynamicTag = cellHighlights?.[field]?.(record)
        if (dynamicTag) {
          return (
            <div
              style={{
                lineHeight: 1.35,
                textAlign: isFinishedPreset ? 'center' : 'left',
                width: '100%',
              }}
            >
              <Tag color={dynamicTag.color}>
                {dynamicTag.text ?? (valueKey || String(value ?? ''))}
              </Tag>
            </div>
          )
        }
        // 值标记（如 是否完成 是=绿 / 否=红）：命中映射时用 Tag 突出
        const tagMap = valueTags?.[field]
        const tag = tagMap?.[valueKey]
        if (tag) {
          return (
            <div
              style={{
                lineHeight: 1.35,
                textAlign: isFinishedPreset ? 'center' : 'left',
                width: '100%',
              }}
            >
              <Tag color={tag.color}>{tag.text ?? valueKey}</Tag>
            </div>
          )
        }
        return (
          <div
            style={
              wrapColumns
                ? {
                    // 紧凑换行模式：单元格内自动换行，超过 3 行截断（全文看详情）
                    display: '-webkit-box',
                    WebkitBoxOrient: 'vertical',
                    WebkitLineClamp: 3,
                    overflow: 'hidden',
                    wordBreak: 'break-word',
                    lineHeight: 1.35,
                    width: '100%',
                  }
                : {
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                    lineHeight: 1.35,
                    textAlign: isFinishedPreset ? 'center' : 'left',
                    width: '100%',
                  }
            }
          >
            {renderFeishuValue(value, record, entityCode, message, {
              fieldName: field,
              uiType: fieldMetaMap[field]?.uiType,
              resultUiType: fieldMetaMap[field]?.resultUiType,
              onAttachmentPreview:
                enableAttachmentPreview ? openAttachmentPreview : undefined,
            })}
          </div>
        )
      },
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

  const operationWidth = editable
    ? enableEquipmentProfile
      ? 200
      : 160
    : enableEquipmentProfile
      ? 120
      : 80
  const operationColumn: ColumnType<Record<string, unknown>> = {
    title: '操作',
    key: '__operation',
    width: operationWidth,
    fixed: 'right',
    render: (_, record) => (
      <Space>
        <Button type="link" size="small" onClick={() => openDetail(record)}>详情</Button>
        {enableEquipmentProfile && (
          <Button type="link" size="small" onClick={() => setProfileRecord(record)}>
            档案
          </Button>
        )}
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

  const fieldNames = displayFields.length > 0 ? displayFields : serverFields
  // 不展示：指定隐藏列（如「父记录」）+ 飞书「按钮」列（无回读值，操作列已有「详情」）
  const columnFields = fieldNames.filter(
    (field) => !hiddenFields.includes(field) && fieldMetaMap[field]?.uiType !== 'Button',
  )
  const baseColumns: ColumnsType<Record<string, unknown>> = (columns && columns.length > 0)
    ? columns
    : columnFields.map(buildAutoColumn)
  const tableColumns: ColumnsType<Record<string, unknown>> = [...baseColumns, operationColumn]

  const tableScrollX = wrapColumns
    ? undefined // 紧凑换行模式：不设横向滚动，列宽平分、内容换行
    : tableColumns.every((column) => typeof column.width === 'number')
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
          {editable && !disableCreate && (canPush || formUrl) && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {createLabel}
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            刷新
          </Button>
          {pullApi && entityCode && (
            <Button type="primary" icon={<SyncOutlined />} onClick={handlePull} loading={syncing}>
              同步飞书数据
            </Button>
          )}
          {showLastSyncTime && lastSyncTime && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              最近同步：{new Date(lastSyncTime).toLocaleString('zh-CN', { hour12: false })}
            </Typography.Text>
          )}
        </Space>
      </div>
      {showFilters && filters.length > 0 && (
        <Card size="small" style={{ marginBottom: 16, background: qualityTokens.bgSoft }}>
          <Space wrap>
            {filters.map(f => {
              // 配置给了选项就用配置；否则取字段元数据的单选选项
              //（设备状态/维修状态/是否知晓等）；都没有则回退文本精确筛选
              const options = f.options ?? fieldOptionsMap[f.key]
              return (
                <Space key={f.key} size={4}>
                  <span style={{ fontSize: 13 }}>{f.label}:</span>
                  {options ? (
                    <Select
                      allowClear
                      showSearch
                      optionFilterProp="label"
                      placeholder={f.label}
                      value={filterValues[f.key] || undefined}
                      onChange={val => handleFilter(f.key, val ?? '')}
                      style={{ width: 150 }}
                      options={options}
                    />
                  ) : (
                    <Input
                      allowClear
                      placeholder={f.label}
                      value={filterValues[f.key] || ''}
                      onChange={e => handleFilter(f.key, e.target.value)}
                      style={{ width: 150 }}
                    />
                  )}
                </Space>
              )
            })}
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
                hasFilters={Boolean(keyword || monthFilter || Object.keys(filterValues).length)}
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
          scroll={wrapColumns ? undefined : { x: tableScrollX }}
          tableLayout={
            wrapColumns || autoColumnPreset === 'finished' ? 'fixed' : undefined
          }
        />
      </Card>
      {editable && entityCode && (
              <InspectionFeishuRecordModal
          open={modalOpen}
          entityCode={entityCode}
          mode={modalMode}
          initialValues={editingRecord}
          editablePersonFields={editablePersonFields}
          onClose={() => setModalOpen(false)}
          onSuccess={() =>
            queryClient.invalidateQueries({ queryKey: ['quality-inspection', 'list', listApi] })
          }
        />
      )}
      {editable && createWithMaterialPicker && (
        <InspectionCreateByMaterialModal
          open={createModalOpen}
          onClose={() => setCreateModalOpen(false)}
          onCreated={handleMaterialCreated}
          module={materialPickerModule}
        />
      )}
      <InspectionFeishuRecordDetailDrawer
        open={detailOpen}
        entityCode={entityCode}
        record={detailRecord}
        allFields={detailFields}
        fieldMeta={fieldMetaMap}
        onAttachmentPreview={
          enableAttachmentPreview ? openAttachmentPreview : undefined
        }
        onClose={() => setDetailOpen(false)}
      />
      {enableEquipmentProfile && (
        <InstrumentProfileDrawer
          open={profileRecord !== null}
          record={profileRecord}
          onClose={() => setProfileRecord(null)}
        />
      )}
      <FeishuAttachmentPreviewModal
        open={attachmentPreview !== null}
        fileName={attachmentPreview?.fileName ?? ''}
        previewSrc={attachmentPreview?.previewSrc ?? ''}
        downloadSrc={attachmentPreview?.downloadSrc ?? ''}
        onClose={() => setAttachmentPreview(null)}
      />
    </div>
  )
}
