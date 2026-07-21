'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { App, Button, Input, Select, Space, Tag } from 'antd'
import {
  CloseCircleOutlined,
  FilterOutlined,
  ReloadOutlined,
  SearchOutlined,
  SyncOutlined,
} from '@ant-design/icons'

import {
  refreshWarehouseFeishuTables,
  syncWarehouseFeishuTable,
} from '@/actions/warehouse'
import type {
  WarehouseFeishuBusinessDomain,
  WarehouseFeishuRawRecordData,
  WarehouseFeishuTable,
} from '@/types/warehouse'

import { FeishuRawRecordTable } from './FeishuRawRecordTable'

interface FeishuDomainMonitorClientProps {
  businessDomain: WarehouseFeishuBusinessDomain
  title: string
  description: string
  tables: WarehouseFeishuTable[]
  data: WarehouseFeishuRawRecordData | null
  error?: string | null
  selectedTableId?: string
  keyword?: string
  field?: string
  fieldOperator?: string
  fieldValue?: string
  page: number
  pageSize: number
}

const fieldOperatorOptions = [
  { label: '包含', value: 'contains' },
  { label: '等于', value: 'eq' },
  { label: '不等于', value: 'ne' },
  { label: '大于', value: 'gt' },
  { label: '大于等于', value: 'gte' },
  { label: '小于', value: 'lt' },
  { label: '小于等于', value: 'lte' },
]

const numericFieldOperators = new Set(['gt', 'gte', 'lt', 'lte'])

function clean(value?: string | null) {
  const normalized = value?.trim()
  return normalized || undefined
}

function isNumericValue(value: string): boolean {
  return /^-?\d+(\.\d+)?$/.test(value.trim())
}

export function FeishuDomainMonitorClient({
  businessDomain,
  title,
  description,
  tables,
  data,
  error,
  selectedTableId,
  keyword,
  field,
  fieldOperator,
  fieldValue,
  page,
  pageSize,
}: FeishuDomainMonitorClientProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [searchValue, setSearchValue] = useState(keyword || '')
  const [selectedField, setSelectedField] = useState<string | undefined>(field)
  const [selectedOperator, setSelectedOperator] = useState(fieldOperator || 'contains')
  const [filterValue, setFilterValue] = useState(fieldValue || '')
  const [syncing, setSyncing] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const activeTableId = selectedTableId || data?.table?.id || tables[0]?.id || undefined
  const activeTable = tables.find((table) => table.id === activeTableId) || data?.table
  const fieldOptions = useMemo(
    () =>
      (data?.fields || []).map((item) => ({
        label: item.field_name,
        value: item.field_name,
      })),
    [data?.fields],
  )

  const navigate = (next: {
    tableId?: string
    keyword?: string | null
    field?: string | null
    fieldOperator?: string | null
    fieldValue?: string | null
    page?: number
    pageSize?: number
  }) => {
    const params = new URLSearchParams()
    const nextTableId = next.tableId ?? activeTableId
    const nextKeyword = clean(next.keyword ?? searchValue)
    const nextField = clean(next.field === undefined ? selectedField : next.field)
    const nextFieldOperator = clean(
      next.fieldOperator === undefined ? selectedOperator : next.fieldOperator,
    )
    const nextFieldValue = clean(
      next.fieldValue === undefined ? filterValue : next.fieldValue,
    )
    const nextPage = next.page ?? page
    const nextPageSize = next.pageSize ?? pageSize

    if (nextTableId) params.set('table_id', nextTableId)
    if (nextKeyword) params.set('keyword', nextKeyword)
    if (nextField && nextFieldOperator && nextFieldValue) {
      params.set('field', nextField)
      params.set('field_operator', nextFieldOperator)
      params.set('field_value', nextFieldValue)
    }
    if (nextPage > 1) params.set('page', String(nextPage))
    if (nextPageSize !== 50) params.set('page_size', String(nextPageSize))

    router.push(`/warehouse/${routeSegmentByDomain[businessDomain]}?${params}`)
  }

  const handleApplyFieldFilter = () => {
    if (!selectedField) {
      message.warning('请选择要筛选的字段')
      return
    }
    if (!filterValue.trim()) {
      message.warning('请填写字段筛选值')
      return
    }
    if (numericFieldOperators.has(selectedOperator) && !isNumericValue(filterValue)) {
      message.warning('数值比较条件必须填写数字')
      return
    }
    navigate({
      field: selectedField,
      fieldOperator: selectedOperator,
      fieldValue: filterValue,
      page: 1,
    })
  }

  const handleClearFieldFilter = () => {
    setSelectedField(undefined)
    setSelectedOperator('contains')
    setFilterValue('')
    navigate({
      field: null,
      fieldOperator: null,
      fieldValue: null,
      page: 1,
    })
  }

  const handleSync = async () => {
    if (!activeTableId) {
      message.warning('请先在飞书配置中启用数据表')
      return
    }
    try {
      setSyncing(true)
      const response = await syncWarehouseFeishuTable(activeTableId)
      message.success(
        `已同步 ${response.data.record_count} 条记录、${response.data.field_count} 个字段`,
      )
      router.refresh()
    } catch (syncError) {
      message.error(syncError instanceof Error ? syncError.message : '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const handleRefresh = async () => {
    try {
      setRefreshing(true)
      await refreshWarehouseFeishuTables()
      message.success('表目录已刷新')
      router.refresh()
    } catch (refreshError) {
      message.error(
        refreshError instanceof Error ? refreshError.message : '刷新表目录失败',
      )
    } finally {
      setRefreshing(false)
    }
  }

  const controls = (
    <div className="flex flex-wrap items-center gap-3">
      <Tag className="m-0 max-w-[360px] truncate px-3 py-1 text-[13px]">
        {activeTable
          ? `${activeTable.name}（${activeTable.record_count || 0} 条）`
          : '未启用数据表'}
      </Tag>
      <Input.Search
        className="max-w-[320px]"
        allowClear
        enterButton={<SearchOutlined />}
        placeholder="搜索关键词"
        value={searchValue}
        onChange={(event) => setSearchValue(event.target.value)}
        onSearch={(value) => navigate({ keyword: value, page: 1 })}
      />
      <Select
        className="min-w-[180px]"
        allowClear
        showSearch
        placeholder="筛选字段"
        value={selectedField}
        options={fieldOptions}
        optionFilterProp="label"
        onChange={(value) => setSelectedField(value)}
      />
      <Select
        className="w-[120px]"
        value={selectedOperator}
        options={fieldOperatorOptions}
        onChange={setSelectedOperator}
      />
      <Input
        className="w-[180px]"
        allowClear
        placeholder="筛选值"
        value={filterValue}
        onChange={(event) => setFilterValue(event.target.value)}
        onPressEnter={handleApplyFieldFilter}
      />
      <Space>
        <Button icon={<FilterOutlined />} onClick={handleApplyFieldFilter}>
          筛选
        </Button>
        <Button icon={<CloseCircleOutlined />} onClick={handleClearFieldFilter}>
          清除
        </Button>
        <Button icon={<SyncOutlined />} loading={syncing} onClick={handleSync}>
          同步当前表
        </Button>
        <Button
          icon={<ReloadOutlined />}
          loading={refreshing}
          onClick={handleRefresh}
        >
          刷新目录
        </Button>
      </Space>
      <Tag>{tables.length} 张已启用表</Tag>
    </div>
  )

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
          {title}
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">{description}</p>
      </div>
      <FeishuRawRecordTable
        title={`${title}监测数据`}
        data={data}
        error={error}
        currentPage={page}
        pageSize={pageSize}
        onPageChange={(nextPage, nextPageSize) =>
          navigate({ page: nextPage, pageSize: nextPageSize })
        }
        extra={controls}
      />
    </div>
  )
}

const routeSegmentByDomain: Record<WarehouseFeishuBusinessDomain, string> = {
  finished_product: 'raw-material',
  materials_packaging: 'packaging',
  hardware: 'product',
}
