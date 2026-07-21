'use client'

import { SettingOutlined } from '@ant-design/icons'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Drawer,
  Dropdown,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType as AntColumnsType } from 'antd/es/table'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

import {
  fetchMappedPageData,
  fetchMappedPageDataset,
  mappedAttachmentUrl,
} from '@/lib/api/mapped-feishu'
import type {
  WarehouseDatasetRecord,
  WarehouseFeishuField,
  WarehouseFeishuPageBinding,
  WarehouseFeishuPageData,
} from '@/types/warehouse'

interface MappedDatasetPageProps {
  moduleCode?: string
  pageKey: string
  title: string
  description?: string
  enableAdvancedQuery?: boolean
  initialPageData?: WarehouseFeishuPageData
}

type DetailValue = {
  title: string
  value: unknown
  fieldId: string
  recordId: string
} | null

function attachmentItems(value: unknown): Array<{ token: string; name: string }> {
  const found: Array<{ token: string; name: string }> = []
  const visit = (item: unknown) => {
    if (Array.isArray(item)) {
      item.forEach(visit)
      return
    }
    if (!item || typeof item !== 'object') return
    const object = item as Record<string, unknown>
    const token = object.file_token || object.attachment_token
    if (typeof token === 'string') {
      found.push({ token, name: String(object.name || object.file_name || '下载附件') })
    }
    Object.values(object).forEach(visit)
  }
  visit(value)
  return found
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') {
    if (/^\d{13}$/.test(value)) {
      const date = new Date(Number(value))
      if (!Number.isNaN(date.getTime())) return date.toLocaleString('zh-CN')
    }
    return value
  }
  if (Array.isArray(value)) return value.map(formatValue).join('、') || '-'
  if (typeof value === 'object') {
    const object = value as Record<string, unknown>
    for (const key of ['text', 'name', 'title', 'display_name', 'value', 'url']) {
      if (object[key] !== undefined) return formatValue(object[key])
    }
    return '查看详情'
  }
  return String(value)
}

function sourcePath(binding: WarehouseFeishuPageBinding) {
  const path = binding.table.source_path || []
  return path.map((item) => item.title).filter(Boolean).join(' / ')
}

function MappedDatasetPageContent({
  pageKey,
  moduleCode = pageKey.split('.')[0],
  title,
  description,
  enableAdvancedQuery = true,
  initialPageData,
}: MappedDatasetPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const requestedBinding = searchParams.get('dataset') || undefined
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '')
  const [page, setPage] = useState(Number(searchParams.get('page') || 1))
  const [pageSize, setPageSize] = useState(Number(searchParams.get('page_size') || 50))
  const [visibleFieldsByBinding, setVisibleFieldsByBinding] = useState<Record<string, string[]>>({})
  const [detail, setDetail] = useState<DetailValue>(null)
  const [filterFieldId, setFilterFieldId] = useState<string>()
  const [filterOperator, setFilterOperator] = useState('contains')
  const [filterValue, setFilterValue] = useState('')
  const [sortFieldId, setSortFieldId] = useState<string>()
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

  const pageQuery = useQuery({
    queryKey: ['mapped-page-data', moduleCode, pageKey],
    queryFn: () => fetchMappedPageData(moduleCode, pageKey),
    initialData: initialPageData,
  })
  const bindings = pageQuery.data?.bindings || []
  const defaultBinding = bindings.find((item) => item.is_default) || bindings[0]
  const activeBinding =
    bindings.find((item) => item.id === requestedBinding) || defaultBinding

  const datasetQuery = useQuery({
    queryKey: [
      'mapped-page-dataset',
      moduleCode,
      pageKey,
      activeBinding?.id,
      keyword,
      page,
      pageSize,
      filterFieldId,
      filterOperator,
      filterValue,
      sortFieldId,
      sortDirection,
    ],
    enabled: Boolean(activeBinding?.id),
    queryFn: () =>
      fetchMappedPageDataset(moduleCode, pageKey, activeBinding!.id, {
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
        filters: filterFieldId && filterValue ? [{ field_id: filterFieldId, operator: filterOperator, value: filterValue }] : undefined,
        sort_field: sortFieldId,
        sort_direction: sortDirection,
      }),
  })

  const fields = useMemo(() => datasetQuery.data?.fields || [], [datasetQuery.data?.fields])
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

  const columns = useMemo<AntColumnsType<WarehouseDatasetRecord>>(
    () =>
      fields
        .filter((field) => visibleFieldIds.includes(field.field_id))
        .map((field: WarehouseFeishuField) => ({
          title: field.field_name,
          key: field.field_id,
          width: 180,
          ellipsis: true,
          render: (_: unknown, record: WarehouseDatasetRecord) => {
            const value = record.fields[field.field_name]
            const complex = Array.isArray(value) || (value !== null && typeof value === 'object')
            if (complex) {
              return (
                <Button
                  type="link"
                  size="small"
                  onClick={() => setDetail({
                    title: field.field_name,
                    value,
                    fieldId: field.field_id,
                    recordId: record.record_id,
                  })}
                >
                  {formatValue(value)}
                </Button>
              )
            }
            return <span>{formatValue(value)}</span>
          },
        })),
    [fields, visibleFieldIds],
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
    router.replace(`?${next.toString()}`)
  }

  if (pageQuery.isError) {
    return <Alert type="error" showIcon message={(pageQuery.error as Error).message} />
  }

  return (
    <main className="mx-auto max-w-[1600px] px-6 py-7">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Typography.Title level={3} className="!mb-1">{title}</Typography.Title>
          <Typography.Text type="secondary">
            {description || '展示已映射飞书数据表的最后一次完整本地镜像'}
          </Typography.Text>
        </div>
        <Space wrap>
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
          {enableAdvancedQuery ? <Select
            allowClear
            placeholder="筛选字段"
            value={filterFieldId}
            options={fields.map((item) => ({ label: item.field_name, value: item.field_id }))}
            onChange={(value) => { setFilterFieldId(value); setPage(1) }}
            style={{ width: 150 }}
          /> : null}
          {enableAdvancedQuery ? <Select
            value={filterOperator}
            onChange={(value) => { setFilterOperator(value); setPage(1) }}
            options={[
              { label: '包含', value: 'contains' },
              { label: '等于', value: 'eq' },
              { label: '不等于', value: 'ne' },
              { label: '大于', value: 'gt' },
              { label: '大于等于', value: 'gte' },
              { label: '小于', value: 'lt' },
              { label: '小于等于', value: 'lte' },
            ]}
            style={{ width: 110 }}
          /> : null}
          {enableAdvancedQuery ? <Input
            allowClear
            placeholder="筛选值"
            value={filterValue}
            onChange={(event) => { setFilterValue(event.target.value); setPage(1) }}
            style={{ width: 150 }}
          /> : null}
          {enableAdvancedQuery ? <Select
            allowClear
            placeholder="排序字段"
            value={sortFieldId}
            options={fields.map((item) => ({ label: item.field_name, value: item.field_id }))}
            onChange={(value) => { setSortFieldId(value); setPage(1) }}
            style={{ width: 150 }}
          /> : null}
          {enableAdvancedQuery ? <Select
            value={sortDirection}
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
          <Button onClick={() => datasetQuery.refetch()} loading={datasetQuery.isFetching}>
            刷新本地数据
          </Button>
        </Space>
      </div>

      {!pageQuery.isLoading && !bindings.length ? (
        <Card><Empty description="此页面尚未映射飞书数据表，请在飞书配置中添加映射" /></Card>
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

          {activeBinding ? (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-[13px]">
              <Tag color={activeBinding.table.sync_status === 'success' ? 'green' : 'orange'}>
                {activeBinding.table.sync_status || '未同步'}
              </Tag>
              <Typography.Text type="secondary">
                {sourcePath(activeBinding) || activeBinding.table.app_token}
              </Typography.Text>
              <Typography.Text type="secondary">
                数据截至：{activeBinding.table.last_synced_at
                  ? new Date(activeBinding.table.last_synced_at).toLocaleString('zh-CN')
                  : '尚未同步'}
              </Typography.Text>
            </div>
          ) : null}

          {activeBinding?.table.sync_error ? (
            <Alert className="mb-4" type="warning" showIcon message={activeBinding.table.sync_error} />
          ) : null}
          {datasetQuery.isError ? (
            <Alert type="error" showIcon message={(datasetQuery.error as Error).message} />
          ) : (
            <Table<WarehouseDatasetRecord>
              virtual
              sticky
              rowKey="record_id"
              loading={datasetQuery.isLoading}
              columns={columns}
              dataSource={datasetQuery.data?.records || []}
              scroll={{ x: Math.max(columns.length * 180, 900), y: 620 }}
              pagination={{
                current: page,
                pageSize,
                total: datasetQuery.data?.pagination.total || 0,
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
        width={720}
        onClose={() => setDetail(null)}
      >
        {detail && activeBinding ? (
          <Space direction="vertical" className="mb-4">
            {attachmentItems(detail.value).map((item) => (
              <a
                key={item.token}
                href={mappedAttachmentUrl(moduleCode, pageKey, activeBinding.id, detail.recordId, detail.fieldId, item.token)}
                target="_blank"
                rel="noreferrer"
              >
                {item.name}
              </a>
            ))}
          </Space>
        ) : null}
        <pre className="max-h-[75vh] overflow-auto whitespace-pre-wrap rounded-[8px] bg-[var(--color-surface)] p-4 text-[12px]">
          {JSON.stringify(detail?.value, null, 2)}
        </pre>
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
