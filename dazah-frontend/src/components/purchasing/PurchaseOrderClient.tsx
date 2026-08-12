'use client'

import { useMemo, useState } from 'react'
import { App, Button, Select, Space, Table, Tag } from 'antd'
import type { TableProps } from 'antd'
import {
  DownloadOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  exportPurchaseOrdersExcel,
  fetchPurchaseOrders,
} from '@/lib/api/purchasing'
import type {
  PurchaseOrderLineResponse,
  PurchaseRequestCategory,
} from '@/types/purchasing'
import {
  formatMoney,
  purchaseCategories,
  purchaseCategoryLabels,
  usesMaterialFields,
} from './purchaseRequestConstants'

type PurchaseOrderClientProps = {
  initialLines: PurchaseOrderLineResponse[]
  initialTotal: number
  initialYear: number
  initialMonth: number
}

type CategoryFilter = PurchaseRequestCategory | 'all'

const DEFAULT_PAGE_SIZE = 20

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function PurchaseOrderClient({
  initialLines,
  initialTotal,
  initialYear,
  initialMonth,
}: PurchaseOrderClientProps) {
  const { message } = App.useApp()
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [year, setYear] = useState(initialYear)
  const [month, setMonth] = useState(initialMonth)
  const [records, setRecords] = useState(initialLines)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)

  const selectedCategory =
    category === 'all' ? undefined : (category as PurchaseRequestCategory)
  const selectedCategoryLabel = selectedCategory
    ? purchaseCategoryLabels[selectedCategory]
    : '全部类别'
  const isUrgent = selectedCategory === 'urgent'
  const selectedMaterialFields = selectedCategory
    ? isUrgent
      ? null
      : usesMaterialFields(selectedCategory)
    : null

  const yearOptions = useMemo(() => {
    const currentYear = new Date().getFullYear()
    return Array.from({ length: 9 }, (_, index) => currentYear - 4 + index).map(
      (value) => ({ label: `${value}年`, value })
    )
  }, [])

  const totalAmount = useMemo(
    () =>
      records.reduce((sum, record) => sum + Number(record.total_amount ?? 0), 0),
    [records]
  )

  const loadRecords = async (nextPage = page) => {
    setLoading(true)
    try {
      const response = await fetchPurchaseOrders({
        category: selectedCategory,
        year,
        month,
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setRecords(response.data ?? [])
      setTotal(Number(response.meta?.total ?? response.data?.length ?? 0))
      setPage(nextPage)
    } catch {
      message.error('采购订单汇总加载失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = () => {
    void loadRecords(1)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const { blob, filename } = await exportPurchaseOrdersExcel({
        category: selectedCategory,
        year,
        month,
      })
      downloadBlob(blob, filename)
      message.success('Excel 已导出')
    } catch {
      message.error('Excel 导出失败')
    } finally {
      setExporting(false)
    }
  }

  const columns: TableProps<PurchaseOrderLineResponse>['columns'] = [
    {
      title: '申请日期',
      dataIndex: 'request_date',
      key: 'request_date',
      width: 120,
    },
    {
      title: '采购类别',
      dataIndex: 'category_label',
      key: 'category_label',
      width: 120,
      render: (value: string) => <Tag color="processing">{value}</Tag>,
    },
    {
      title: '申购部门',
      dataIndex: 'request_department',
      key: 'request_department',
      width: 150,
      ellipsis: true,
    },
    ...(isUrgent
      ? [
          {
            title: '申请类型',
            dataIndex: 'item_category',
            key: 'item_category',
            width: 130,
            render: (value: PurchaseRequestCategory) => purchaseCategoryLabels[value] ?? value,
          },
          {
            title: '物料编码/商品名称',
            key: 'material_code_compatibility',
            width: 180,
            ellipsis: true,
            render: (_value: unknown, record: PurchaseOrderLineResponse) => record.material_code || record.product_name,
          },
          {
            title: '物料说明/商品名称',
            key: 'material_description_compatibility',
            width: 190,
            ellipsis: true,
            render: (_value: unknown, record: PurchaseOrderLineResponse) => record.material_description || record.product_name,
          },
          {
            title: '规则型号/规格型号',
            key: 'rule_model_compatibility',
            width: 170,
            ellipsis: true,
            render: (_value: unknown, record: PurchaseOrderLineResponse) => record.rule_model || record.specification,
          },
        ]
      : selectedMaterialFields === true
      ? [
          {
            title: '物料编码',
            dataIndex: 'material_code',
            key: 'material_code',
            width: 150,
            ellipsis: true,
          },
          {
            title: '物料说明',
            dataIndex: 'material_description',
            key: 'material_description',
            width: 180,
            ellipsis: true,
          },
          {
            title: '规则型号',
            dataIndex: 'rule_model',
            key: 'rule_model',
            width: 150,
            ellipsis: true,
          },
        ]
      : selectedMaterialFields === false
        ? [
            {
              title: '商品名称',
              dataIndex: 'product_name',
              key: 'product_name',
              width: 170,
              ellipsis: true,
            },
            {
              title: '规格',
              dataIndex: 'specification',
              key: 'specification',
              width: 130,
              ellipsis: true,
            },
          ]
        : [
            {
              title: '物料编码/商品名称',
              key: 'material_code_compatibility',
              width: 180,
              ellipsis: true,
              render: (_value: unknown, record: PurchaseOrderLineResponse) =>
                record.material_code || record.product_name,
            },
            {
              title: '物料说明/商品名称',
              key: 'material_description_compatibility',
              width: 190,
              ellipsis: true,
              render: (_value: unknown, record: PurchaseOrderLineResponse) =>
                record.material_description || record.product_name,
            },
            {
              title: '规则型号/规格型号',
              key: 'rule_model_compatibility',
              width: 170,
              ellipsis: true,
              render: (_value: unknown, record: PurchaseOrderLineResponse) =>
                record.rule_model || record.specification,
            },
          ]),
    {
      title: '用途',
      dataIndex: 'purpose',
      key: 'purpose',
      width: 150,
      ellipsis: true,
    },
    {
      title: '材质',
      dataIndex: 'material',
      key: 'material',
      width: 110,
      ellipsis: true,
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      key: 'brand',
      width: 110,
      ellipsis: true,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 90,
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 80,
    },
    {
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 110,
      render: (value: string | number) => formatMoney(value),
    },
    {
      title: '金额',
      dataIndex: 'total_amount',
      key: 'total_amount',
      width: 110,
      render: (value: string | number) => formatMoney(value),
    },
    {
      title: '备注',
      dataIndex: 'remarks',
      key: 'remarks',
      width: 180,
      ellipsis: true,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">
            采购管理 / 采购订单
          </p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            采购订单月度汇总
          </h1>
          <Space size="small" wrap>
            <Tag color="processing">{selectedCategoryLabel}</Tag>
            <Tag>{year}年{month}月</Tag>
            <Tag color="success">已通过申请</Tag>
          </Space>
        </div>
        <Space wrap>
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => loadRecords(page)}
          >
            刷新
          </Button>
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            loading={exporting}
            onClick={handleExport}
          >
            导出 Excel
          </Button>
        </Space>
      </div>

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
        <div className="grid gap-4 border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4 md:grid-cols-[minmax(180px,240px)_160px_160px_auto]">
          <div>
            <label className="mb-2 block text-[13px] font-medium text-[var(--color-charcoal)]">
              采购类别
            </label>
            <Select
              className="w-full"
              value={category}
              options={[
                { label: '全部类别', value: 'all' },
                ...purchaseCategories.map((item) => ({
                  label: purchaseCategoryLabels[item],
                  value: item,
                })),
              ]}
              onChange={(value) => setCategory(value as CategoryFilter)}
            />
          </div>
          <div>
            <label className="mb-2 block text-[13px] font-medium text-[var(--color-charcoal)]">
              年份
            </label>
            <Select
              className="w-full"
              value={year}
              options={yearOptions}
              onChange={setYear}
            />
          </div>
          <div>
            <label className="mb-2 block text-[13px] font-medium text-[var(--color-charcoal)]">
              月份
            </label>
            <Select
              className="w-full"
              value={month}
              options={Array.from({ length: 12 }, (_, index) => ({
                label: `${index + 1}月`,
                value: index + 1,
              }))}
              onChange={setMonth}
            />
          </div>
          <div className="flex items-end">
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={loading}
              onClick={handleSearch}
            >
              查询
            </Button>
          </div>
        </div>

        <div className="grid gap-3 border-b border-[var(--color-hairline-soft)] px-4 py-3 md:grid-cols-3">
          <div>
            <p className="text-[12px] text-[var(--color-stone)]">明细行数</p>
            <p className="text-[18px] font-semibold text-[var(--color-charcoal)]">
              {total}
            </p>
          </div>
          <div>
            <p className="text-[12px] text-[var(--color-stone)]">当前页金额</p>
            <p className="text-[18px] font-semibold text-[var(--color-charcoal)]">
              {formatMoney(totalAmount)}
            </p>
          </div>
          <div>
            <p className="text-[12px] text-[var(--color-stone)]">汇总范围</p>
            <p className="text-[18px] font-semibold text-[var(--color-charcoal)]">
              整月申请明细
            </p>
          </div>
        </div>

        <Table
          columns={columns}
          dataSource={records}
          rowKey="item_id"
          loading={loading}
          scroll={{ x: 1580 }}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage) => loadRecords(nextPage),
          }}
          locale={{ emptyText: '暂无符合条件的已通过采购申请明细' }}
        />
      </section>
    </div>
  )
}
