'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { CloudUploadOutlined, ReloadOutlined, SaveOutlined, SearchOutlined } from '@ant-design/icons'
import {
  App,
  Avatar,
  Button,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

import {
  getSafetyPageTableRecords,
  getSafetyPageTableStats,
  updateSafetyPageTableRecord,
  uploadSafetyPageTableAttachment,
} from '@/actions/safety'
import { renderFeishuValue } from '@/components/quality/inspection/renderFeishuValue'
import PageFeishuStatsBar from '@/components/safety/PageFeishuStatsBar'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import {
  asAttachmentList,
  asPersonList,
  asUrlValue,
  columnOptions,
  displayFieldText,
  pickConditionSelectColumns,
  pickDefaultDateColumn,
  toPageTableStats,
  toRecordRows,
  type PageTableColumn,
  type PageTableRecordRow,
  type PageTableStats,
} from '@/lib/safety-page-tables'

const PAGE_SIZE_OPTIONS = ['20', '50', '100']

/** 表格最多展示的摘要列数；其余字段点击行后在详情抽屉里查看。 */
const MAX_SUMMARY_COLUMNS = 10
/** 文本列超过该长度视为长文本（措施说明等），只在详情中查看。 */
const LONG_TEXT_THRESHOLD = 80
/** 单选/多选列的选项超过该长度（防护、措施类长句）时按长文本换行渲染。 */
const LONG_OPTION_THRESHOLD = 20

/** 状态列（申请状态/巡查状态等）：始终保留在摘要列，方便一眼看到结果。 */
function isStatusColumn(column: PageTableColumn): boolean {
  return (
    (column.kind === 'select' || column.kind === 'multi_select') &&
    column.name.includes('状态')
  )
}

/** 计算表格摘要列：剔除勾选清单与长文本列后，状态列保底保留。 */
function buildSummaryColumns(
  columns: PageTableColumn[],
  rows: PageTableRecordRow[]
): PageTableColumn[] {
  const longTextNames = new Set(
    columns
      .filter((column) => column.kind === 'text')
      .map((column) => column.name)
      .filter((name) =>
        rows.some(
          (row) =>
            displayFieldText(row.fields[name]).length > LONG_TEXT_THRESHOLD
        )
      )
  )
  const eligible = columns.filter(
    (column) => column.kind !== 'checkbox' && !longTextNames.has(column.name)
  )
  const statusColumns = eligible.filter(isStatusColumn)
  const others = eligible.filter((column) => !isStatusColumn(column))
  return [
    ...others.slice(0, Math.max(0, MAX_SUMMARY_COLUMNS - statusColumns.length)),
    ...statusColumns,
  ]
}

function attachmentUrl(
  pageKey: string,
  recordId: string,
  fieldName: string,
  fileToken: string
): string {
  // 以 /content 结尾：共享渲染器会把 /content 重写为 /thumbnail 取小图
  return `/api/v1/safety/page-tables/${encodeURIComponent(pageKey)}/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fieldName)}/${encodeURIComponent(fileToken)}/content`
}

/** 附件/人员单元格与详情统一走 QC 验证的共享渲染器（缩略图、头像）。 */
function renderFeishuColumnValue(
  column: PageTableColumn,
  value: unknown,
  row: PageTableRecordRow,
  pageKey: string,
  message: ReturnType<typeof App.useApp>['message']
) {
  if (column.kind === 'attachment') {
    const items = asAttachmentList(value)
    if (!items.length) return <Typography.Text type="secondary">—</Typography.Text>
    return renderFeishuValue(items, { record_id: row.record_id }, undefined, message, {
      attachmentUrlBuilder: (_entity, recordId, fileToken) =>
        attachmentUrl(pageKey, recordId, column.name, fileToken),
    })
  }
  if (column.kind === 'person') {
    const people = asPersonList(value)
    if (!people.length) return <Typography.Text type="secondary">—</Typography.Text>
    return renderFeishuValue(people, { record_id: row.record_id }, undefined, message)
  }
  return undefined
}

/** 表格列里的只读展示（非附件/人员字段）。 */
function renderPlainCellValue(column: PageTableColumn, value: unknown) {
  if (column.kind === 'checkbox') {
    return value ? <Tag color="success">是</Tag> : <Tag>否</Tag>
  }
  if (column.kind === 'select' && value) {
    return <Tag color="processing">{String(value)}</Tag>
  }
  if (column.kind === 'url') {
    const url = asUrlValue(value)
    return url ? (
      <a href={url.link} target="_blank" rel="noreferrer">
        {url.text || '链接'}
      </a>
    ) : (
      <Typography.Text type="secondary">—</Typography.Text>
    )
  }
  const text = displayFieldText(value)
  if (!text) return <Typography.Text type="secondary">—</Typography.Text>
  return text
}

/** 内容较长的文本类列：单元格自动换行（保留换行符），不做省略号截断。 */
function isWrappableColumn(column: PageTableColumn): boolean {
  if (column.kind === 'text' || column.kind === 'readonly') return true
  if (column.kind === 'select' || column.kind === 'multi_select') {
    // 防护/措施类字段的选项本身是长句，按长文本换行渲染而不是 Tag 截断
    return columnOptions(column).some(
      (option) => option.length > LONG_OPTION_THRESHOLD
    )
  }
  return false
}

/** 查询表单的多条件（字段间 AND）。 */
type RecordCondition = { field: string; value: string }

/** 由筛选状态构造查询条件（仅主要列模式使用）。 */
function buildConditions(
  summarize: boolean,
  dateColumn: PageTableColumn | null,
  date: dayjs.Dayjs | null,
  selects: Record<string, string>
): RecordCondition[] {
  if (!summarize) return []
  const conditions: RecordCondition[] = []
  if (dateColumn && date) {
    conditions.push({ field: dateColumn.name, value: date.format('YYYY-MM-DD') })
  }
  for (const [field, value] of Object.entries(selects)) {
    if (value) conditions.push({ field, value })
  }
  return conditions
}

export default function PageFeishuTable({
  pageKey,
  pageName,
  initialData = null,
  initialStats = null,
  initialError = null,
  showStats = true,
  summarizeColumns = false,
  initialDateFilter = null,
}: {
  pageKey: string
  pageName: string
  initialData?: {
    columns: PageTableColumn[]
    records: PageTableRecordRow[]
    total: number
    page: number
    page_size: number
    truncated: boolean
  } | null
  initialStats?: PageTableStats | null
  initialError?: string | null
  /** 是否展示顶部统计仪表盘（下钻筛选依赖它；仅仪表盘所属页面开启）。 */
  showStats?: boolean
  /**
   * 表格是否只显示主要列（勾选清单/长文本收进详情，最多 10 列）。
   * 仅作业安全镜像页启用；不传保持全列展示的原有行为。
   */
  summarizeColumns?: boolean
  /** 服务端首屏已应用的日期条件（默认当天），客户端以此初始化日期筛选。 */
  initialDateFilter?: RecordCondition | null
}) {
  const { message } = App.useApp()
  const { canOperate } = usePagePermissions(pageKey)
  const [columns, setColumns] = useState<PageTableColumn[]>(initialData?.columns ?? [])
  const [rows, setRows] = useState<PageTableRecordRow[]>(initialData?.records ?? [])
  const [total, setTotal] = useState(initialData?.total ?? 0)
  const [page, setPage] = useState(initialData?.page ?? 1)
  const [pageSize, setPageSize] = useState(initialData?.page_size ?? 20)
  const [stats, setStats] = useState<PageTableStats | null>(initialStats)
  const [keyword, setKeyword] = useState('')
  const [sortField, setSortField] = useState<string | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [loading, setLoading] = useState(false)
  const [truncated, setTruncated] = useState(initialData?.truncated ?? false)
  const [loadError, setLoadError] = useState<string | null>(initialError)
  const [dimensionFilter, setDimensionFilter] = useState<{
    field: string
    value: string
  } | null>(null)
  const [detail, setDetail] = useState<PageTableRecordRow | null>(null)
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [uploadingField, setUploadingField] = useState<string | null>(null)
  const requestSeq = useRef(0)

  const editableColumns = useMemo(
    () => columns.filter((column) => column.editable),
    [columns]
  )
  const attachmentColumns = useMemo(
    () => columns.filter((column) => column.kind === 'attachment'),
    [columns]
  )
  // 主要列模式（仅作业安全镜像页开启）：勾选清单与长文本收进详情，截前 N 列
  const summaryColumns = useMemo(
    () =>
      summarizeColumns ? buildSummaryColumns(columns, rows) : columns,
    [summarizeColumns, columns, rows]
  )
  const detailOnlyCount = summarizeColumns
    ? Math.max(0, columns.length - summaryColumns.length)
    : 0
  const dateColumn = useMemo(
    () => pickDefaultDateColumn(columns),
    [columns]
  )
  const conditionSelects = useMemo(
    () =>
      summarizeColumns ? pickConditionSelectColumns(summaryColumns) : [],
    [summarizeColumns, summaryColumns]
  )
  const [dateFilter, setDateFilter] = useState<dayjs.Dayjs | null>(() =>
    initialDateFilter ? dayjs(initialDateFilter.value) : null
  )
  const [selectFilters, setSelectFilters] = useState<Record<string, string>>({})

  /**
   * 人员字段的候选项来自当前表格已出现过的人员（含 open_id 与头像）。
   * 这样无需引入飞书通讯录接口即可维护值班人员；新增人员仍在飞书端完成。
   */
  const personOptions = useMemo(() => {
    const byId = new Map<string, { label: string; avatar?: string | null }>()
    for (const column of columns) {
      if (column.kind !== 'person') continue
      for (const row of rows) {
        for (const person of asPersonList(row.fields[column.name])) {
          if (person.id) {
            byId.set(person.id, { label: person.name || person.id, avatar: person.avatar_url })
          }
        }
      }
    }
    return [...byId.entries()].map(([value, meta]) => ({ value, ...meta }))
  }, [columns, rows])

  const load = useCallback(
    async (override?: {
      page?: number
      pageSize?: number
      keyword?: string
      sortField?: string | null
      sortDirection?: 'asc' | 'desc'
      filter?: { field: string; value: string } | null
      conditions?: RecordCondition[]
    }) => {
      const next = {
        page: override?.page ?? page,
        pageSize: override?.pageSize ?? pageSize,
        keyword: override?.keyword ?? keyword,
        sortField: override?.sortField !== undefined ? override.sortField : sortField,
        sortDirection: override?.sortDirection ?? sortDirection,
        filter:
          override?.filter !== undefined ? override.filter : dimensionFilter,
        conditions:
          override?.conditions !== undefined
            ? override.conditions
            : buildConditions(
                summarizeColumns,
                dateColumn,
                dateFilter,
                selectFilters
              ),
      }
      const seq = requestSeq.current + 1
      requestSeq.current = seq
      setLoading(true)
      const [res, statsRes] = await Promise.all([
        getSafetyPageTableRecords({
          pageKey,
          page: next.page,
          pageSize: next.pageSize,
          keyword: next.keyword || undefined,
          sortField: next.sortField || undefined,
          sortDirection: next.sortDirection,
          filterField: next.filter?.field || undefined,
          filterValue: next.filter?.value || undefined,
          conditions: next.conditions.length ? next.conditions : undefined,
        }),
        showStats
          ? getSafetyPageTableStats({ pageKey })
          : Promise.resolve({ code: 200 as const, data: null }),
      ])
      if (seq !== requestSeq.current) return
      setLoading(false)
      if (showStats && statsRes.code === 200) {
        setStats(toPageTableStats(statsRes.data))
      }
      if (res.code === 200 && res.data) {
        setColumns(res.data.columns ?? [])
        setRows(toRecordRows(res.data.records))
        setTotal(res.data.total)
        setPage(res.data.page)
        setPageSize(res.data.page_size)
        setTruncated(res.data.truncated)
        setLoadError(null)
      } else {
        setLoadError(res.message || '读取多维表格数据失败')
      }
    },
    [dateColumn, dateFilter, dimensionFilter, keyword, page, pageSize, pageKey, selectFilters, showStats, sortDirection, sortField, summarizeColumns]
  )

  const openDetail = useCallback(
    (row: PageTableRecordRow) => {
      setDetail(row)
      const initial: Record<string, unknown> = {}
      for (const column of editableColumns) {
        const value = row.fields[column.name]
        if (column.kind === 'date') {
          initial[column.name] = value ? dayjs(String(value)) : null
        } else if (column.kind === 'person') {
          initial[column.name] = asPersonList(value).map((person) => person.id)
        } else if (column.kind === 'attachment') {
          continue
        } else {
          initial[column.name] = value ?? undefined
        }
      }
      form.setFieldsValue(initial)
    },
    [editableColumns, form]
  )

  const handleSave = useCallback(async () => {
    if (!detail) return
    const values = (await form.validateFields()) as Record<string, unknown>
    const payload: Record<string, unknown> = {}
    for (const column of editableColumns) {
      if (column.kind === 'attachment') continue
      const current = values[column.name]
      if (column.kind === 'date') {
        payload[column.name] = current ? dayjs(current as never).format('YYYY-MM-DD') : null
      } else if (column.kind === 'person') {
        payload[column.name] = ((current as string[]) ?? []).map((id) => ({ id }))
      } else {
        payload[column.name] = current ?? null
      }
    }
    setSaving(true)
    const res = await updateSafetyPageTableRecord({
      pageKey,
      recordId: detail.record_id,
      fields: payload,
    })
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('已保存到飞书多维表格')
      const updated = res.data as PageTableRecordRow
      setRows((prev) =>
        prev.map((row) => (row.record_id === updated.record_id ? updated : row))
      )
      setDetail(updated)
      openDetail(updated)
    } else {
      message.error(res.message || '保存失败')
    }
  }, [detail, editableColumns, form, message, openDetail, pageKey])

  const handleUpload = useCallback(
    async (column: PageTableColumn, file: File) => {
      if (!detail) return
      setUploadingField(column.name)
      const res = await uploadSafetyPageTableAttachment({
        pageKey,
        recordId: detail.record_id,
        fieldName: column.name,
        file,
      })
      setUploadingField(null)
      if (res.code === 200 && res.data) {
        message.success('附件已上传到飞书多维表格')
        const attachments = res.data.attachments
        setRows((prev) =>
          prev.map((row) =>
            row.record_id === detail.record_id
              ? { ...row, fields: { ...row.fields, [column.name]: attachments } }
              : row
          )
        )
        setDetail((prev) =>
          prev
            ? { ...prev, fields: { ...prev.fields, [column.name]: attachments } }
            : prev
        )
      } else {
        message.error(res.message || '附件上传失败')
      }
    },
    [detail, message, pageKey]
  )

  /** 图表下钻：再次点击同一分类取消筛选。 */
  const handleSelectDimension = useCallback(
    (field: string, value: string) => {
      const next =
        dimensionFilter?.field === field && dimensionFilter?.value === value
          ? null
          : { field, value }
      setDimensionFilter(next)
      setPage(1)
      void load({ page: 1, filter: next })
    },
    [dimensionFilter, load]
  )

  useEffect(() => {
    // 首屏数据由服务端注入；仅在缺失时兜底拉取
    if (!initialData) void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const tableColumns: ColumnsType<PageTableRecordRow> = summaryColumns.map((column) => {
    const wrappable = summarizeColumns && isWrappableColumn(column)
    return {
      title: column.name,
      dataIndex: ['fields', column.name],
      key: column.field_id || column.name,
      ellipsis: column.kind !== 'attachment' && !wrappable,
      width: column.kind === 'attachment' ? 220 : undefined,
      sorter: true,
      render: (_: unknown, row: PageTableRecordRow) => {
        if (column.kind === 'attachment') {
          // 图片点击是放大预览，不能冒泡到行上误开详情抽屉
          return (
            <div onClick={(event) => event.stopPropagation()}>
              {renderFeishuColumnValue(
                column,
                row.fields[column.name],
                row,
                pageKey,
                message
              )}
            </div>
          )
        }
        const rendered = renderFeishuColumnValue(
          column,
          row.fields[column.name],
          row,
          pageKey,
          message
        )
        if (rendered !== undefined) return rendered
        if (wrappable) {
          // td 的 max-width 在表格布局里不可靠，用单元格内 div 限宽自动换行
          const text = displayFieldText(row.fields[column.name])
          if (!text) return <Typography.Text type="secondary">—</Typography.Text>
          return (
            <div
              style={{
                maxWidth: 320,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {text}
            </div>
          )
        }
        return renderPlainCellValue(column, row.fields[column.name])
      },
    }
  })

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {showStats ? (
        <PageFeishuStatsBar stats={stats} onSelect={handleSelectDimension} />
      ) : null}
      {dimensionFilter ? (
        <Space size={8} wrap>
          <Typography.Text type="secondary">当前筛选：</Typography.Text>
          <Tag
            closable
            color="processing"
            onClose={() => {
              setDimensionFilter(null)
              setPage(1)
              void load({ page: 1, filter: null })
            }}
          >
            {dimensionFilter.field} = {dimensionFilter.value}
          </Tag>
        </Space>
      ) : null}
      {loadError ? (
        <PlatformNotice
          type="warning"
          title="无法读取多维表格数据"
          description={`${loadError}（若提示未配置，请到 安全管理 → 系统配置 → 飞书设置 的「页面数据表映射」中绑定表格）`}
        />
      ) : null}
      {truncated ? (
        <PlatformNotice
          type="info"
          title="记录较多，仅加载最近 2000 条"
          description="列表按日期优先加载最新记录，更早的历史记录请到飞书多维表格中查看。"
        />
      ) : null}
      {summarizeColumns ? (
        <Space size={12} wrap>
          {dateColumn ? (
            <DatePicker
              allowClear
              value={dateFilter}
              placeholder={
                initialDateFilter
                  ? `${dateColumn.name}（默认当天，清空看全部）`
                  : `${dateColumn.name}（可选）`
              }
              onChange={(value) => {
                setDateFilter(value)
                void load({
                  page: 1,
                  conditions: buildConditions(
                    summarizeColumns,
                    dateColumn,
                    value,
                    selectFilters
                  ),
                })
              }}
            />
          ) : null}
          {conditionSelects.map((column) => (
            <Select
              key={column.name}
              allowClear
              placeholder={column.name}
              style={{ minWidth: 150 }}
              value={selectFilters[column.name] || undefined}
              options={columnOptions(column).map((option) => ({
                value: option,
                label: option,
              }))}
              onChange={(value) => {
                const next = { ...selectFilters, [column.name]: value ?? '' }
                setSelectFilters(next)
                void load({
                  page: 1,
                  conditions: buildConditions(
                    summarizeColumns,
                    dateColumn,
                    dateFilter,
                    next
                  ),
                })
              }}
            />
          ))}
          <Button
            onClick={() => {
              const resetDate = initialDateFilter
                ? dayjs(initialDateFilter.value)
                : null
              setDateFilter(resetDate)
              setSelectFilters({})
              void load({
                page: 1,
                conditions: buildConditions(
                  summarizeColumns,
                  dateColumn,
                  resetDate,
                  {}
                ),
              })
            }}
          >
            重置
          </Button>
        </Space>
      ) : null}
      <Space size={12} wrap>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="按关键字筛选"
          style={{ width: 260 }}
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onPressEnter={() => void load({ page: 1, keyword })}
        />
        <Button onClick={() => void load({ page: 1, keyword })} loading={loading}>
          查询
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
        <Typography.Text type="secondary">
          共 {total} 条；列与数据来自飞书多维表格，修改会直接写回飞书。
          {detailOnlyCount > 0
            ? ` 表格仅显示主要列，其余 ${detailOnlyCount} 个字段点击行后在详情中查看。`
            : ''}
        </Typography.Text>
      </Space>
      <Table<PageTableRecordRow>
        rowKey="record_id"
        size="middle"
        loading={loading}
        columns={tableColumns}
        dataSource={rows}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showTotal: (count) => `共 ${count} 条`,
        }}
        onChange={(pagination, _filters, sorter) => {
          const single = Array.isArray(sorter) ? sorter[0] : sorter
          const nextField =
            single?.order && typeof single.field === 'string' ? single.field : null
          const nextDirection: 'asc' | 'desc' = single?.order === 'descend' ? 'desc' : 'asc'
          setSortField(nextField)
          setSortDirection(nextDirection)
          void load({
            page: pagination.current ?? 1,
            pageSize: pagination.pageSize ?? pageSize,
            sortField: nextField,
            sortDirection: nextDirection,
          })
        }}
        onRow={(row) => ({
          onClick: () => openDetail(row),
          style: { cursor: 'pointer' },
        })}
      />
      <Drawer
        title={`${pageName} · 记录详情`}
        width={720}
        open={detail !== null}
        onClose={() => setDetail(null)}
        destroyOnHidden
        extra={
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!canOperate}
            onClick={() => void handleSave()}
          >
            保存
          </Button>
        }
      >
        {detail ? (
          <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
            {!canOperate ? (
              <PlatformNotice
                type="info"
                title="当前账号只有查看权限"
                description="保存与上传附件需要该页面的操作权限。"
              />
            ) : null}
            <Form form={form} layout="vertical" disabled={!canOperate}>
              {editableColumns
                .filter((column) => column.kind !== 'attachment')
                .map((column) => (
                  <Form.Item key={column.name} name={column.name} label={column.name}>
                    {column.kind === 'number' ? (
                      <InputNumber style={{ width: '100%' }} />
                    ) : column.kind === 'select' ? (
                      <Select
                        allowClear
                        options={columnOptions(column).map((option) => ({
                          value: option,
                          label: option,
                        }))}
                      />
                    ) : column.kind === 'multi_select' ? (
                      <Select
                        allowClear
                        mode="multiple"
                        options={columnOptions(column).map((option) => ({
                          value: option,
                          label: option,
                        }))}
                      />
                    ) : column.kind === 'date' ? (
                      <DatePicker style={{ width: '100%' }} />
                    ) : column.kind === 'checkbox' ? (
                      <Switch />
                    ) : column.kind === 'person' ? (
                      <Select
                        allowClear
                        mode="multiple"
                        options={personOptions.map((option) => ({
                          value: option.value,
                          label: (
                            <span
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                            >
                              <Avatar size={20} src={option.avatar || undefined}>
                                {option.label.slice(0, 1) || '?'}
                              </Avatar>
                              {option.label}
                            </span>
                          ),
                        }))}
                        placeholder={
                          personOptions.length
                            ? '从当前表格出现过的值班人员中选择'
                            : '当前表格还没有可选的飞书用户'
                        }
                      />
                    ) : (
                      <Input.TextArea autoSize={{ minRows: 1, maxRows: 6 }} />
                    )}
                  </Form.Item>
                ))}
            </Form>

            {attachmentColumns.map((column) => {
              const items = asAttachmentList(detail.fields[column.name])
              return (
                <div key={column.name}>
                  <Typography.Text strong>{column.name}</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    {items.length ? (
                      renderFeishuValue(
                        items,
                        { record_id: detail.record_id },
                        undefined,
                        message,
                        {
                          attachmentUrlBuilder: (_entity, recordId, fileToken) =>
                            attachmentUrl(pageKey, recordId, column.name, fileToken),
                        }
                      )
                    ) : (
                      <Typography.Text type="secondary">暂无附件</Typography.Text>
                    )}
                  </div>
                  <Upload
                    showUploadList={false}
                    disabled={!canOperate}
                    beforeUpload={(file) => {
                      void handleUpload(column, file as File)
                      return false
                    }}
                  >
                    <Button
                      size="small"
                      icon={<CloudUploadOutlined />}
                      loading={uploadingField === column.name}
                      disabled={!canOperate}
                      style={{ marginTop: 8 }}
                    >
                      上传附件
                    </Button>
                  </Upload>
                </div>
              )
            })}
          </Space>
        ) : null}
      </Drawer>
    </Space>
  )
}
