'use client'

import { useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Input,
  Select,
  Statistic,
  Table,
  Tag,
  Upload,
} from 'antd'
import type { TableProps, UploadProps } from 'antd'
import {
  InboxOutlined,
  ReloadOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { importSupplierTable } from '@/actions/purchasing'
import { fetchSuppliers } from '@/lib/api/purchasing'
import type { SupplierListResponse, SupplierResponse } from '@/types/purchasing'
import { useAuthStore } from '@/stores/auth'

const { Dragger } = Upload
const { Search } = Input
const DEFAULT_PAGE_SIZE = 20
const MAX_SUPPLIER_UPLOAD_SIZE_MB = 50
const MAX_SUPPLIER_UPLOAD_SIZE_BYTES = MAX_SUPPLIER_UPLOAD_SIZE_MB * 1024 * 1024
const SUPPLIER_FILE_EXTENSIONS = ['.xlsx', '.xlsm', '.csv', '.tsv']
const FALLBACK_COLUMNS = [
  '供应商代码',
  '供应商名称',
  '物料编码',
  '物料名称',
  '生产厂家编码',
  '生产厂家名称',
  '采购品类名称',
  '最后更新人',
  '最后更新日期',
]

type SupplierManagementClientProps = {
  initialRecords: SupplierResponse[]
  initialTotal: number
  initialColumns: string[]
  initialLoadFailed?: boolean
}

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function isSupportedSupplierFile(fileName: string) {
  const normalized = fileName.toLowerCase()
  return SUPPLIER_FILE_EXTENSIONS.some((extension) =>
    normalized.endsWith(extension)
  )
}

function getResponseColumns(response: SupplierListResponse) {
  const columns = response.meta?.columns
  if (!Array.isArray(columns)) return []
  return columns.filter((column): column is string => typeof column === 'string')
}

export function SupplierManagementClient({
  initialRecords,
  initialTotal,
  initialColumns,
  initialLoadFailed = false,
}: SupplierManagementClientProps) {
  const { message, modal } = App.useApp()
  const canImport = useAuthStore((state) => state.hasPagePermission('purchasing:supplier', 'operate', 'bulk_import'))
  const [records, setRecords] = useState(initialRecords)
  const [columns, setColumns] = useState(
    initialColumns.length ? initialColumns : FALLBACK_COLUMNS
  )
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [supplierName, setSupplierName] = useState('')
  const [materialName, setMaterialName] = useState('')
  const [purchaseCategory, setPurchaseCategory] = useState<string | undefined>()
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)

  const categoryOptions = useMemo(() => {
    const values = new Set(
      records
        .map((record) => record.purchase_category)
        .filter((value): value is string => Boolean(value))
    )
    return Array.from(values).map((value) => ({ label: value, value }))
  }, [records])

  const latestFileName = records[0]?.import_file_name || '-'
  const latestImportTime = records[0]?.created_at
    ? records[0].created_at.replace('T', ' ').slice(0, 16)
    : '-'

  const loadRecords = async (
    nextPage = page,
    options?: { resetFilters?: boolean }
  ) => {
    const resetFilters = options?.resetFilters ?? false
    setLoading(true)
    try {
      const response = await fetchSuppliers({
        keyword: resetFilters ? undefined : keyword || undefined,
        supplier_name: resetFilters ? undefined : supplierName || undefined,
        material_name: resetFilters ? undefined : materialName || undefined,
        purchase_category: resetFilters ? undefined : purchaseCategory || undefined,
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setRecords(response.data ?? [])
      setTotal(Number(response.meta?.total ?? response.data?.length ?? 0))
      const nextColumns = getResponseColumns(response)
      if (nextColumns.length) {
        setColumns(nextColumns)
      }
      setPage(nextPage)
    } catch {
      message.error('供应商清单加载失败')
    } finally {
      setLoading(false)
    }
  }

  const handleImport: UploadProps['beforeUpload'] = (file) => {
    if (!canImport) {
      message.warning('未获得供应商清单的批量导入权限')
      return Upload.LIST_IGNORE
    }
    if (!isSupportedSupplierFile(file.name)) {
      message.error('请上传 xlsx、xlsm、csv 或 tsv 文件')
      return Upload.LIST_IGNORE
    }
    if (file.size > MAX_SUPPLIER_UPLOAD_SIZE_BYTES) {
      message.error(`表格文件不能超过 ${MAX_SUPPLIER_UPLOAD_SIZE_MB}MB`)
      return Upload.LIST_IGNORE
    }

    modal.confirm({ title: '确认覆盖供应商清单？',
      content: `将使用“${file.name}”替换当前供应商清单，共 ${total} 条现有记录可能被覆盖。`,
      okText: '确认覆盖导入', cancelText: '取消', onOk: () => {
        setUploading(true)
        const formData = new FormData()
        formData.append('file', file)
        return importSupplierTable(formData)
          .then(async (response) => {
            if (response.code >= 200 && response.code < 300) {
              const importedCount = response.data?.imported_count ?? 0
              const importedColumns = response.data?.columns ?? []
              message.success(`已导入 ${importedCount} 条供应商记录`)
              setKeyword('')
              setSupplierName('')
              setMaterialName('')
              setPurchaseCategory(undefined)
              setColumns(importedColumns.length ? importedColumns : columns)
              await loadRecords(1, { resetFilters: true })
            } else {
              message.error(response.message || '供应商清单导入失败')
            }
          })
          .catch(() => {
            message.error('供应商清单导入失败')
          })
          .finally(() => {
            setUploading(false)
          })
      },
    })

    return Upload.LIST_IGNORE
  }

  const tableColumns = useMemo<TableProps<SupplierResponse>['columns']>(
    () =>
      columns.map((column) => ({
        title: column,
        key: column,
        dataIndex: ['raw_data', column],
        width: column.includes('名称') ? 220 : 150,
        ellipsis: true,
        render: (value: unknown, record) => {
          const displayed = displayValue(value)
          if (column === '采购品类名称' && displayed !== '-') {
            return <Tag color="processing">{displayed}</Tag>
          }
          if (column === '供应商名称' && displayed === '-') {
            return displayValue(record.supplier_name)
          }
          return displayed
        },
      })),
    [columns]
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">
            采购管理 / 供应商管理
          </p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            供应商管理
          </h1>
          <p className="max-w-[760px] text-[14px] leading-6 text-[var(--color-steel)]">
            导入供应商清单表格后，系统按文件表头读取字段并展示，支持按供应商、物料和品类检索。
          </p>
        </div>
        <Button
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => void loadRecords(page)}
        >
          刷新
        </Button>
      </div>

      {initialLoadFailed && (
        <Alert
          showIcon
          type="warning"
          message="供应商清单暂时无法加载"
          description="请确认后端服务和数据库迁移已完成，页面仍可在服务恢复后刷新。"
        />
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <Statistic title="供应商记录" value={total} suffix="条" />
        </section>
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <Statistic title="展示字段" value={columns.length} suffix="列" />
        </section>
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <p className="text-[13px] text-[var(--color-stone)]">当前文件</p>
          <p className="mt-2 truncate text-[16px] font-semibold text-[var(--color-charcoal)]">
            {latestFileName}
          </p>
        </section>
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4">
          <p className="text-[13px] text-[var(--color-stone)]">导入时间</p>
          <p className="mt-2 text-[16px] font-semibold text-[var(--color-charcoal)]">
            {latestImportTime}
          </p>
        </section>
      </div>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
        <div className="border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)]">
                导入清单
              </h2>
              <p className="mt-1 text-[13px] text-[var(--color-stone)]">
                支持 xlsx、xlsm、csv、tsv，导入后替换当前供应商清单。
              </p>
            </div>
            <Tag icon={<UploadOutlined />}>表格导入</Tag>
          </div>
        </div>
        <div className="p-4">
          <Dragger
            accept=".xlsx,.xlsm,.csv,.tsv"
            beforeUpload={handleImport}
            disabled={uploading || !canImport}
            maxCount={1}
            showUploadList={false}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">{canImport ? '点击或拖拽供应商表格到此处' : '未获得批量导入权限，仅可查询供应商清单'}</p>
            <p className="ant-upload-hint">
              系统将按第一行表头读取字段，并保留原始列顺序。
            </p>
          </Dragger>
        </div>
      </section>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
        <div className="border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(220px,1.3fr)_minmax(180px,1fr)_minmax(180px,1fr)_180px_104px]">
            <Search
              allowClear
              enterButton={<SearchOutlined />}
              placeholder="搜索供应商、物料、厂家或任意原始字段"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={() => void loadRecords(1)}
            />
            <Input
              allowClear
              placeholder="供应商名称"
              value={supplierName}
              onChange={(event) => setSupplierName(event.target.value)}
              onPressEnter={() => void loadRecords(1)}
            />
            <Input
              allowClear
              placeholder="物料名称"
              value={materialName}
              onChange={(event) => setMaterialName(event.target.value)}
              onPressEnter={() => void loadRecords(1)}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={categoryOptions}
              placeholder="采购品类"
              value={purchaseCategory}
              onChange={setPurchaseCategory}
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={loading}
              onClick={() => void loadRecords(1)}
            >
              检索
            </Button>
          </div>
        </div>
        <Table<SupplierResponse>
          columns={tableColumns}
          dataSource={records}
          loading={loading || uploading}
          rowKey="id"
          scroll={{ x: Math.max(columns.length * 150, 1080) }}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage) => void loadRecords(nextPage),
          }}
        />
      </section>
    </div>
  )
}
