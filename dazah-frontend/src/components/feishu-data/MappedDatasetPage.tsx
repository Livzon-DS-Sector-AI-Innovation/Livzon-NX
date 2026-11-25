'use client'

import { UserOutlined, SettingOutlined } from '@ant-design/icons'
import { PlusOutlined } from '@ant-design/icons'
import { Avatar, Button, Card, Checkbox, Drawer, Dropdown, Empty, Image, Input, Select, Space, Table, Tabs, Typography, message } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import type { ColumnsType as AntColumnsType } from 'antd/es/table'
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import {
  fetchMappedPageData,
  fetchMappedPageDataset,
  fetchMappedPageExport,
  fetchPersonAvatars,
  mappedAttachmentUrl,
} from '@/lib/api/mapped-feishu'
import { getUserErrorMessage } from '@/lib/user-error'
import type {
  WarehouseDataset,
  WarehouseDatasetRecord,
  WarehouseFeishuField,
  WarehouseFeishuPageData,
} from '@/types/warehouse'

interface MappedDatasetPageProps {
  moduleCode?: string
  pageKey: string
  title: string
  description?: string
  enableAdvancedQuery?: boolean
  initialPageData?: WarehouseFeishuPageData
  /** 开启镜像人员头像解析（按企业邮箱，需模块提供 person-avatars 端点）。 */
  enablePersonAvatars?: boolean
  /** 按字段名在表格中隐藏（详情抽屉仍完整展示）。 */
  hiddenFieldNames?: string[]
  /** 开启台账导出（Excel/PDF，按当前筛选/排序导出全量，含图片与头像）。 */
  enableExport?: boolean
  /**
   * 指定页签的默认排序（用户未手动选排序时生效）。表格无日期字段时
   * 平台不会自动排序，用这个 prop 指定按业务字段（如房间编号）升序。
   */
  defaultSort?: { tabName: string; fieldName: string; direction: 'asc' | 'desc' }
  /** 按页签联动的新增入口：激活匹配页签时显示对应按钮（新窗口打开表单）。 */
  createForms?: Array<{ tabLabel: string; label: string; url: string }>
}

interface PersonItem {
  id?: string
  name?: string
  email?: string
}

interface AttachmentItem {
  name?: string
  type?: string
  file_token?: string
  attachment_token?: string
}

type DetailValue = {
  title: string
  value: unknown
  fieldId: string
  recordId: string
} | null

const IMAGE_EXTENSION_PATTERN = /\.(jpe?g|png|gif|webp|bmp)$/i

/** 飞书字段类型 ID：5=日期，1001/1002=创建/修改时间。 */
const DATE_FIELD_TYPES = new Set([5, 1001, 1002])

function fieldTypeId(field: WarehouseFeishuField): number {
  return Number(field.type ?? field.field_type ?? NaN)
}

function isEmptyFieldValue(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    value === '' ||
    (Array.isArray(value) && value.length === 0)
  )
}

function isImageAttachment(item: AttachmentItem): boolean {
  const name = item.name || ''
  const type = item.type || ''
  return type.startsWith('image/') || IMAGE_EXTENSION_PATTERN.test(name)
}

function attachmentItems(value: unknown): Array<{ token: string; name: string; type: string }> {
  const found: Array<{ token: string; name: string; type: string }> = []
  const visit = (item: unknown) => {
    if (Array.isArray(item)) {
      item.forEach(visit)
      return
    }
    if (!item || typeof item !== 'object') return
    const object = item as Record<string, unknown>
    const token = object.file_token || object.attachment_token
    if (typeof token === 'string') {
      found.push({
        token,
        name: String(object.name || object.file_name || '下载附件'),
        type: typeof object.type === 'string' ? object.type : '',
      })
    }
    Object.values(object).forEach(visit)
  }
  visit(value)
  return found
}

/** 飞书人员字段：[{id: "ou_…", name, email}]（附件项没有 email/id）。 */
function isPersonItems(value: unknown): value is PersonItem[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (item) =>
        item !== null && typeof item === 'object' && !Array.isArray(item) &&
        typeof (item as PersonItem).name === 'string' &&
        (typeof (item as PersonItem).email === 'string' ||
          String((item as PersonItem).id || '').startsWith('ou_')),
    )
  )
}

function personNames(value: unknown): string[] {
  if (!isPersonItems(value)) return []
  return value.map((item) => (item.name || '').trim()).filter(Boolean)
}

function collectPersonEmails(records: WarehouseDatasetRecord[]): string[] {
  const emails = new Set<string>()
  for (const record of records) {
    for (const value of Object.values(record.fields || {})) {
      if (isPersonItems(value)) {
        for (const item of value) {
          if (item.email) emails.add(item.email)
        }
      }
    }
  }
  return [...emails]
}

/** 固定东八区：飞书日期是本地零点时间戳，SSR（UTC 容器）与浏览器输出必须一致。
 * 零点时间戳只显示日期部分。 */
function formatDateTime(value: number): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const full = date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
  return full.endsWith(' 00:00:00') ? full.slice(0, -' 00:00:00'.length) : full
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  // 飞书日期字段是毫秒时间戳（数值或数字串），按东八区展示
  if (typeof value === 'number' && value >= 1e12 && value < 1e14) return formatDateTime(value)
  if (typeof value === 'string') {
    if (/^\d{13}$/.test(value) && Number(value) >= 1e12 && Number(value) < 1e14) {
      return formatDateTime(Number(value))
    }
    return value
  }
  if (Array.isArray(value)) {
    if (isPersonItems(value)) return personNames(value).join('、') || '-'
    return value.map(formatValue).join('、') || '-'
  }
  if (typeof value === 'object') {
    const object = value as Record<string, unknown>
    for (const key of ['text', 'name', 'title', 'display_name', 'value', 'url']) {
      if (object[key] !== undefined) return formatValue(object[key])
    }
    return '查看详情'
  }
  return String(value)
}

/** 表格单元格内的图片缩略图条：点击弹大图预览（阻断行点击冒泡）。 */
function AttachmentThumbStrip({
  images,
  moduleCode,
  pageKey,
  bindingId,
  recordId,
  fieldId,
}: {
  images: Array<{ token: string; name: string }>
  moduleCode: string
  pageKey: string
  bindingId: string
  recordId: string
  fieldId: string
}) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1" onClick={(event) => event.stopPropagation()}>
      <Image.PreviewGroup>
        {images.slice(0, 3).map((item) => (
          <Image
            key={item.token}
            src={mappedAttachmentUrl(moduleCode, pageKey, bindingId, recordId, fieldId, item.token)}
            alt={item.name}
            width={36}
            height={36}
            style={{ objectFit: 'cover', borderRadius: 4 }}
          />
        ))}
      </Image.PreviewGroup>
      {images.length > 3 ? (
        <span className="text-[12px]" style={{ color: 'var(--color-slate)' }}>
          +{images.length - 3}
        </span>
      ) : null}
    </span>
  )
}

function PersonName({
  value,
  avatarByEmail,
  size = 22,
}: {
  value: unknown
  avatarByEmail: Record<string, string>
  size?: number
}) {
  if (!isPersonItems(value)) return <span>{formatValue(value)}</span>
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {value.map((item, index) => {
        const name = (item.name || '').trim() || '未知成员'
        const avatar = item.email ? avatarByEmail[item.email] : undefined
        return (
          <span key={`${item.id || item.email || index}-${index}`} className="inline-flex items-center gap-1">
            <Avatar src={avatar} size={size} icon={<UserOutlined />}>
              {name.slice(0, 1)}
            </Avatar>
            <span>{name}</span>
          </span>
        )
      })}
    </span>
  )
}

function RecordFieldValue({
  value,
  recordId,
  fieldId,
  moduleCode,
  pageKey,
  bindingId,
  avatarByEmail,
}: {
  value: unknown
  recordId: string
  fieldId: string
  moduleCode: string
  pageKey: string
  bindingId: string
  avatarByEmail: Record<string, string>
}) {
  const attachments = attachmentItems(value)
  if (attachments.length) {
    return (
      <div className="flex flex-col gap-2">
        {attachments.some(isImageAttachment) ? (
          <Image.PreviewGroup>
            <div className="flex flex-wrap gap-2">
              {attachments.filter(isImageAttachment).map((item) => (
                <Image
                  key={item.token}
                  src={mappedAttachmentUrl(moduleCode, pageKey, bindingId, recordId, fieldId, item.token)}
                  alt={item.name}
                  width={96}
                  height={96}
                  style={{ objectFit: 'cover', borderRadius: 8 }}
                />
              ))}
            </div>
          </Image.PreviewGroup>
        ) : null}
        <div className="flex flex-col gap-1">
          {attachments.map((item) => (
            <a
              key={item.token}
              href={mappedAttachmentUrl(moduleCode, pageKey, bindingId, recordId, fieldId, item.token)}
              target="_blank"
              rel="noreferrer"
            >
              {item.name}
            </a>
          ))}
        </div>
      </div>
    )
  }
  if (isPersonItems(value)) return <PersonName value={value} avatarByEmail={avatarByEmail} size={28} />
  const text = formatValue(value)
  if (text === '查看详情') {
    return (
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-[8px] bg-[var(--color-surface)] p-3 text-[12px]">
        {JSON.stringify(value, null, 2)}
      </pre>
    )
  }
  return <span>{text}</span>
}

function MappedDatasetPageContent({
  pageKey,
  moduleCode = pageKey.split('.')[0],
  title,
  description,
  enableAdvancedQuery = true,
  initialPageData,
  enablePersonAvatars = false,
  hiddenFieldNames,
  enableExport = false,
  defaultSort,
  createForms,
}: MappedDatasetPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const requestedBinding = searchParams.get('dataset') || undefined
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '')
  const [page, setPage] = useState(Number(searchParams.get('page') || 1))
  const [pageSize, setPageSize] = useState(Number(searchParams.get('page_size') || 50))
  const [visibleFieldsByBinding, setVisibleFieldsByBinding] = useState<Record<string, string[]>>({})
  const [detail, setDetail] = useState<DetailValue>(null)
  const [filters, setFilters] = useState<
    Array<{ field_id: string; operator: string; value: string }>
  >([])
  const [sortFieldId, setSortFieldId] = useState<string>()
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')
  const [exporting, setExporting] = useState<'xlsx' | 'pdf' | null>(null)

  const activeFilters = useMemo(
    () =>
      filters.filter(
        (item) => item.field_id && item.value.trim(),
      ) as Array<{ field_id: string; operator: string; value: string }>,
    [filters],
  )
  const filtersKey = activeFilters
    .map((item) => `${item.field_id}:${item.operator}:${item.value}`)
    .join('|')

  const initialBindingVersion = (initialPageData?.bindings || [])
    .map((item) => item.id)
    .join(',')
  const pageQuery = useQuery({
    queryKey: ['mapped-page-data', moduleCode, pageKey, initialBindingVersion],
    queryFn: () => fetchMappedPageData(moduleCode, pageKey),
    initialData: initialPageData,
  })
  const bindings = pageQuery.data?.bindings || []
  const defaultBinding = bindings.find((item) => item.is_default) || bindings[0]
  // 页签切换由本组件 state 直接驱动：router.replace 后 useSearchParams 不保证
  // 立即重渲染（URL 仍同步写入，供刷新/分享直达），避免点击页签后界面不切换。
  const [activeBindingOverride, setActiveBindingOverride] = useState<string | null>(null)
  const activeBinding =
    bindings.find(
      (item) => item.id === (activeBindingOverride ?? requestedBinding),
    ) || defaultBinding

  const activeBindingId = activeBinding?.id
  const bindingTabName = activeBinding?.tab_label
  /** 默认排序只在指定页签、且用户未手动选排序时生效（按字段名传给后端）。 */
  const defaultSortActive = Boolean(
    defaultSort && bindingTabName === defaultSort.tabName && !sortFieldId,
  )
  const effectiveSortFieldId = sortFieldId || (defaultSortActive && defaultSort ? defaultSort.fieldName : undefined)
  const effectiveSortDirection: 'asc' | 'desc' = sortFieldId
    ? sortDirection
    : defaultSortActive && defaultSort
      ? defaultSort.direction
      : 'desc'

  // 显式类型注解：queryKey 依赖下方派生的 autoSortField（来自本 query 的字段快照），
  // 会形成推断循环，注解后即为两段式（先取字段再按日期倒序重取）。
  const datasetQuery: UseQueryResult<WarehouseDataset, Error> = useQuery({
    queryKey: [
      'mapped-page-dataset',
      moduleCode,
      pageKey,
      activeBinding?.id,
      keyword,
      page,
      pageSize,
      filtersKey,
      sortFieldId,
      sortDirection,
      defaultSortActive,
    ],
    enabled: Boolean(activeBinding?.id),
    queryFn: () =>
      fetchMappedPageDataset(moduleCode, pageKey, activeBinding!.id, {
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
        filters: activeFilters.length ? activeFilters : undefined,
        sort_field: effectiveSortFieldId || undefined,
        sort_direction: effectiveSortFieldId ? effectiveSortDirection : 'desc',
      }),
  })

  const fields = useMemo(() => datasetQuery.data?.fields || [], [datasetQuery.data?.fields])
  const dateField = useMemo(
    () => fields.find((field) => DATE_FIELD_TYPES.has(fieldTypeId(field))),
    [fields],
  )
  // 排序控件展示用：默认排序按字段名下发，控件需要映射回字段 id 才能显示为选中态。
  const sortSelectValue = useMemo(() => {
    if (sortFieldId) return sortFieldId
    if (defaultSortActive && defaultSort) {
      return (
        fields.find((field) => field.field_name === defaultSort.fieldName)?.field_id ??
        defaultSort.fieldName
      )
    }
    return undefined
  }, [sortFieldId, defaultSortActive, defaultSort, fields])
  // 未手动选排序且无默认排序时按日期字段倒序（最新在最上面）。字段快照来自主查询，
  // 排序结果由第二个查询补取：结果就绪则优先展示，未就绪回退主查询数据。
  const needsDateSort = Boolean(
    !sortFieldId && !defaultSortActive && activeBindingId && dateField,
  )
  const sortedQuery: UseQueryResult<WarehouseDataset, Error> = useQuery({
    queryKey: [
      'mapped-page-dataset-sorted',
      moduleCode,
      pageKey,
      activeBinding?.id,
      keyword,
      page,
      pageSize,
      filtersKey,
      dateField?.field_id,
    ],
    enabled: needsDateSort,
    queryFn: () =>
      fetchMappedPageDataset(moduleCode, pageKey, activeBinding!.id, {
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
        filters: activeFilters.length ? activeFilters : undefined,
        sort_field: dateField!.field_id,
        sort_direction: 'desc',
      }),
  })
  const activeQuery = needsDateSort ? sortedQuery : datasetQuery
  const data = (needsDateSort ? sortedQuery.data : undefined) ?? datasetQuery.data

  const records = useMemo(() => data?.records || [], [data?.records])
  const personEmails = useMemo(
    () => (enablePersonAvatars ? collectPersonEmails(records) : []),
    [records, enablePersonAvatars],
  )
  const personEmailsKey = personEmails.join(',')
  const avatarQuery = useQuery({
    queryKey: ['mapped-person-avatars', moduleCode, personEmailsKey],
    enabled: enablePersonAvatars && personEmails.length > 0,
    queryFn: () => fetchPersonAvatars(moduleCode, personEmails),
    staleTime: 60 * 60 * 1000,
    retry: false,
  })
  const avatarByEmail = useMemo(() => avatarQuery.data || {}, [avatarQuery.data])

  const visibleFieldIds = useMemo(() => {
    if (!activeBinding) return []
    const configured = activeBinding.visible_field_ids || []
    return (
      visibleFieldsByBinding[activeBinding.id] ||
      (configured.length ? configured : fields.map((item) => item.field_id))
    )
  }, [activeBinding, fields, visibleFieldsByBinding])

  useEffect(() => {
    if (!activeBinding || requestedBinding === activeBinding.id) return
    const next = new URLSearchParams(searchParams.toString())
    next.set('dataset', activeBinding.id)
    router.replace(`?${next.toString()}`)
  }, [activeBinding, requestedBinding, router, searchParams])

  const displayFields = useMemo(() => {
    const ordered = dateField
      ? [dateField, ...fields.filter((field) => field.field_id !== dateField.field_id)]
      : [...fields]
    // 隐藏序号列（用户不需要）与调用方指定隐藏的字段；整列为空的字段同样隐藏
    // （公式/自动编号等飞书不回值的列）。指定隐藏的字段在详情抽屉仍完整展示。
    return ordered.filter((field) => {
      if (field.field_name === '序号') return false
      if (hiddenFieldNames?.includes(field.field_name)) return false
      if (field.field_id === dateField?.field_id) return true
      return records.some((record) => !isEmptyFieldValue(record.fields[field.field_name]))
    })
  }, [fields, records, dateField, hiddenFieldNames])

  const columns = useMemo<AntColumnsType<WarehouseDatasetRecord>>(
    () => {
      const dateColumnId = dateField?.field_id
      const fieldColumns: AntColumnsType<WarehouseDatasetRecord> =
        displayFields
          .filter((field) => visibleFieldIds.includes(field.field_id))
          .map((field: WarehouseFeishuField) => {
            const valueLengths = records.map((record) =>
              formatValue(record.fields[field.field_name]).length,
            )
            const maxLen = valueLengths.length ? Math.max(...valueLengths) : 0
            const typeId = fieldTypeId(field)
            // 按内容类型定宽：窄内容列收紧；长文本列加宽并自动换行不截断
            let width: number
            let ellipsis = true
            if (field.field_id === dateColumnId) width = 100
            else if (typeId === 17) width = 160
            else if (typeId === 7) width = 80
            else if (typeId === 11) width = 120
            else if (maxLen > 24) {
              width = 280
              ellipsis = false
            } else width = 110
            return {
              title: field.field_name,
              key: field.field_id,
              width,
              fixed: field.field_id === dateColumnId ? ('left' as const) : undefined,
              ellipsis,
              render: (_: unknown, record: WarehouseDatasetRecord) => {
                const value = record.fields[field.field_name]
                if (isPersonItems(value)) {
                  return <PersonName value={value} avatarByEmail={avatarByEmail} />
                }
                const images = attachmentItems(value).filter(isImageAttachment)
                if (images.length && activeBindingId) {
                  return (
                    <AttachmentThumbStrip
                      images={images}
                      moduleCode={moduleCode}
                      pageKey={pageKey}
                      bindingId={activeBindingId}
                      recordId={record.record_id}
                      fieldId={field.field_id}
                    />
                  )
                }
                return <span>{formatValue(value)}</span>
              },
            }
          })
      const dateColumn = fieldColumns.filter((column) => column.key === dateColumnId)
      const restColumns = fieldColumns.filter((column) => column.key !== dateColumnId)
      return [...dateColumn, ...restColumns]
    },
    [
      displayFields,
      visibleFieldIds,
      records,
      avatarByEmail,
      dateField,
      activeBindingId,
      moduleCode,
      pageKey,
    ],
  )

  const activeIsOverflow = bindings.findIndex((item) => item.id === activeBinding?.id) >= 6
  const visibleBindings = activeIsOverflow && activeBinding
    ? [...bindings.slice(0, 5), activeBinding]
    : bindings.slice(0, 6)
  const visibleIds = new Set(visibleBindings.map((item) => item.id))
  const overflowBindings = bindings.filter((item) => !visibleIds.has(item.id))

  const selectBinding = (bindingId: string) => {
    const next = new URLSearchParams(searchParams.toString())
    next.set('dataset', bindingId)
    next.delete('page')
    setPage(1)
    setFilters([])
    setActiveBindingOverride(bindingId)
    router.replace(`?${next.toString()}`)
  }

  const runExport = (format: 'xlsx' | 'pdf') => {
    if (!activeBinding) return
    setExporting(format)
    fetchMappedPageExport(moduleCode, pageKey, activeBinding.id, {
      format,
      columns: displayFields.map((field) => field.field_id),
      filters: activeFilters,
      sort_field: effectiveSortFieldId || dateField?.field_id,
      sort_direction: effectiveSortFieldId ? effectiveSortDirection : 'desc',
    })
      .then(async (blob) => {
        const url = URL.createObjectURL(blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = `${title}-${new Date().toISOString().slice(0, 10)}.${format}`
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        URL.revokeObjectURL(url)
      })
      .catch((error: unknown) => {
        message.error(getUserErrorMessage(error, '导出失败，请稍后重试'))
      })
      .finally(() => setExporting(null))
  }

  if (pageQuery.isError) {
    return <Alert type="error" showIcon title={(pageQuery.error as Error).message} />
  }

  return (
    <main className="mx-auto max-w-[1600px] px-6 py-7">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Typography.Title level={3} className="!mb-1">{title}</Typography.Title>
          {description ? (
            <Typography.Text type="secondary">{description}</Typography.Text>
          ) : null}
        </div>
        {bindings.length ? <Space wrap>
          <Input.Search
            allowClear
            placeholder="搜索全部字段"
            defaultValue={keyword}
            onSearch={(value) => {
              setKeyword(value.trim())
              setPage(1)
            }}
            style={{ width: 280 }}
          />
          {enableAdvancedQuery ? <Dropdown
            trigger={['click']}
            dropdownRender={() => (
              <Card size="small" title="多条件筛选（同时满足）" className="w-[560px]">
                <div className="flex flex-col gap-2">
                  {filters.map((filter, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <Select
                        placeholder="筛选字段"
                        value={filter.field_id || undefined}
                        options={fields.map((item) => ({ label: item.field_name, value: item.field_id }))}
                        onChange={(value) => {
                          setFilters((current) => current.map((item, i) => (i === index ? { ...item, field_id: String(value) } : item)))
                          setPage(1)
                        }}
                        style={{ width: 170 }}
                      />
                      <Select
                        value={filter.operator}
                        options={[
                          { label: '包含', value: 'contains' },
                          { label: '等于', value: 'eq' },
                          { label: '不等于', value: 'ne' },
                          { label: '大于', value: 'gt' },
                          { label: '大于等于', value: 'gte' },
                          { label: '小于', value: 'lt' },
                          { label: '小于等于', value: 'lte' },
                        ]}
                        onChange={(value) => {
                          setFilters((current) => current.map((item, i) => (i === index ? { ...item, operator: String(value) } : item)))
                          setPage(1)
                        }}
                        style={{ width: 104 }}
                      />
                      <Input
                        allowClear
                        placeholder="筛选值"
                        value={filter.value}
                        onChange={(event) => {
                          setFilters((current) => current.map((item, i) => (i === index ? { ...item, value: event.target.value } : item)))
                          setPage(1)
                        }}
                        style={{ width: 150 }}
                      />
                      <Button
                        type="text"
                        danger
                        onClick={() => {
                          setFilters((current) => current.filter((_, i) => i !== index))
                          setPage(1)
                        }}
                      >
                        删除
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="dashed"
                    onClick={() => setFilters((current) => [...current, { field_id: '', operator: 'contains', value: '' }])}
                  >
                    添加条件
                  </Button>
                </div>
              </Card>
            )}
          >
            <Button>
              筛选{activeFilters.length ? `（${activeFilters.length}）` : ''}
            </Button>
          </Dropdown> : null}
          {enableAdvancedQuery ? <Select
            allowClear
            placeholder="排序字段"
            value={sortSelectValue}
            options={fields.map((item) => ({ label: item.field_name, value: item.field_id }))}
            onChange={(value) => { setSortFieldId(value); setPage(1) }}
            style={{ width: 150 }}
          /> : null}
          {enableAdvancedQuery ? <Select
            value={effectiveSortDirection}
            onChange={(value) => { setSortDirection(value); setPage(1) }}
            options={[{ label: '升序', value: 'asc' }, { label: '降序', value: 'desc' }]}
            style={{ width: 90 }}
          /> : null}
          <Dropdown
            trigger={['click']}
            dropdownRender={() => (
              <Card size="small" title="显示字段" className="max-h-[520px] w-[320px] overflow-auto">
                <Checkbox.Group
                  className="flex flex-col gap-2"
                  value={visibleFieldIds}
                  options={fields.map((field) => ({
                    label: field.field_name,
                    value: field.field_id,
                  }))}
                  onChange={(values) => {
                    if (!activeBinding) return
                    setVisibleFieldsByBinding((current) => ({
                      ...current,
                      [activeBinding.id]: values.map(String),
                    }))
                  }}
                />
              </Card>
            )}
          >
            <Button icon={<SettingOutlined />}>列设置</Button>
          </Dropdown>
          {(createForms || [])
            .filter((item) => item.tabLabel === (activeBinding?.tab_label || ''))
            .map((item) => (
              <Button
                key={item.url}
                type="primary"
                icon={<PlusOutlined />}
                href={item.url}
                target="_blank"
                rel="noreferrer"
              >
                {item.label}
              </Button>
            ))}
          <Button onClick={() => activeQuery.refetch()} loading={activeQuery.isFetching}>
            刷新本地数据
          </Button>
          {enableExport && activeBinding ? <>
            <Button
              loading={exporting === 'xlsx'}
              onClick={() => runExport('xlsx')}
            >
              导出 Excel
            </Button>
            <Button
              loading={exporting === 'pdf'}
              onClick={() => runExport('pdf')}
            >
              导出 PDF
            </Button>
          </> : null}
        </Space> : null}
      </div>

      {!pageQuery.isLoading && !bindings.length ? (
        <Card><Empty description="暂无数据：此页面尚未发布数据表映射，请在飞书配置中添加映射" /></Card>
      ) : (
        <Card>
          <div className="flex items-center gap-3">
            <Tabs
              className="min-w-0 flex-1"
              activeKey={activeBinding?.id}
              items={visibleBindings.map((binding) => ({
                key: binding.id,
                label: binding.tab_label,
              }))}
              onChange={selectBinding}
            />
            {overflowBindings.length ? (
              <Dropdown
                menu={{
                  items: overflowBindings.map((binding) => ({
                    key: binding.id,
                    label: binding.tab_label,
                  })),
                  onClick: ({ key }) => selectBinding(key),
                }}
              >
                <Button>更多（{overflowBindings.length}）</Button>
              </Dropdown>
            ) : null}
          </div>

          {activeBinding?.table.sync_error ? (
            <Alert className="mb-4" type="warning" showIcon title={activeBinding.table.sync_error} />
          ) : null}
          {activeQuery.isError ? (
            <Alert type="error" showIcon title={(activeQuery.error as Error).message} />
          ) : (
            <Table<WarehouseDatasetRecord>
              virtual
              sticky
              size="small"
              rowKey="record_id"
              loading={activeQuery.isLoading}
              columns={columns}
              dataSource={records}
              scroll={{
                x: columns.reduce((sum, column) => sum + (Number(column.width) || 110), 48),
                y: 620,
              }}
              onRow={(record) => ({
                onClick: () => setDetail({
                  title: '记录详情',
                  value: record.fields,
                  fieldId: '',
                  recordId: record.record_id,
                }),
                style: { cursor: 'pointer' },
              })}
              pagination={{
                current: page,
                pageSize,
                total: data?.pagination.total || 0,
                pageSizeOptions: [20, 50, 100],
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
                onChange: (nextPage, nextPageSize) => {
                  setPage(nextPageSize === pageSize ? nextPage : 1)
                  setPageSize(nextPageSize)
                },
              }}
            />
          )}
        </Card>
      )}

      <Drawer
        open={Boolean(detail)}
        title={detail?.title}
        size={720}
        onClose={() => setDetail(null)}
      >
        {detail && activeBinding ? (
          <div className="flex flex-col gap-4">
            {fields.map((field: WarehouseFeishuField) => {
              const value = (detail.value as Record<string, unknown>)?.[field.field_name]
              if (value === undefined || value === null || value === '' ) return null
              return (
                <div key={field.field_id}>
                  <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>
                    {field.field_name}
                  </Typography.Text>
                  <RecordFieldValue
                    value={value}
                    recordId={detail.recordId}
                    fieldId={field.field_id}
                    moduleCode={moduleCode}
                    pageKey={pageKey}
                    bindingId={activeBinding.id}
                    avatarByEmail={avatarByEmail}
                  />
                </div>
              )
            })}
          </div>
        ) : null}
      </Drawer>
    </main>
  )
}

export function MappedDatasetPage(props: MappedDatasetPageProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1 },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      <MappedDatasetPageContent {...props} />
    </QueryClientProvider>
  )
}
