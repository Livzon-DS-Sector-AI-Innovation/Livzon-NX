'use client'

import { useMemo, useState } from 'react'
import {
  App,
  Button,
  Drawer,
  Input,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import type { TableProps } from 'antd'
import {
  InfoCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import ThemedEChart from '@/components/shared/ThemedEChart'
import {
  fetchMaterialPriceDetail,
  fetchMaterialPrices,
} from '@/lib/api/purchasing'
import { MaterialPriceFillPanel } from './MaterialPriceFillPanel'
import type {
  MaterialPriceBatch,
  MaterialPriceDetail,
  MaterialPriceSummary,
  MaterialPriceYear,
} from '@/types/purchasing'

const DEFAULT_PAGE_SIZE = 20

const costCategoryOptions = [
  '五金备件',
  '五金电气',
  '劳保用品',
  '化学试剂',
  '包材',
  '办公用品',
  '玻璃仪器',
  '原料',
  '辅料',
  '委托加工',
].map((value) => ({ label: value, value }))

const subInventoryOptions = [
  'C03 五金备件仓',
  'C01 原辅料仓',
  'C02 包材仓',
  'C04 劳保仓',
  'C05 化玻试剂仓',
  'C07 污水处理车间材料仓',
  'C09 中间体仓',
].map((value) => ({ label: value, value }))

const yearOptions = Array.from({ length: 8 }, (_, index) => {
  const year = 2020 + index
  return { label: `${year}年`, value: year }
})

type MaterialPriceClientProps = {
  initialRecords?: MaterialPriceSummary[]
  initialTotal?: number
}

type MaterialPriceMode = 'query' | 'fill'

function formatPrice(value: string | number | null | undefined) {
  const numberValue = Number(value ?? 0)
  if (!Number.isFinite(numberValue)) return '-'
  return numberValue
    .toFixed(4)
    .replace(/\.?0+$/, '')
}

function formatMoney(value: string | number | null | undefined) {
  const numberValue = Number(value ?? 0)
  if (!Number.isFinite(numberValue)) return '-'
  return `¥${numberValue.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function buildChartOption(detail: MaterialPriceDetail | null) {
  const years = detail?.years ?? []
  if (years.length === 0) return {}
  const labels = years.map((item) => `${item.data_year}`)
  const series = (
    [
      ['均价', 'avg_price'],
      ['最低', 'min_price'],
      ['最高', 'max_price'],
    ] as const
  ).map(([name, key], index) => ({
    name,
    type: 'line' as const,
    smooth: true,
    symbolSize: 6,
    lineStyle: index === 0 ? undefined : { type: 'dashed' as const },
    data: years.map((item) => Number(item[key])),
  }))
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: series.map((item) => item.name) },
    grid: { left: 48, right: 24, top: 40, bottom: 32 },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', scale: true },
    series,
  }
}

export function MaterialPriceClient({
  initialRecords,
  initialTotal,
}: MaterialPriceClientProps) {
  const { message } = App.useApp()
  const [mode, setMode] = useState<MaterialPriceMode>('query')
  const [records, setRecords] = useState(initialRecords)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [costCategory, setCostCategory] = useState<string | undefined>()
  const [subInventory, setSubInventory] = useState<string | undefined>()
  const [dataYear, setDataYear] = useState<number | undefined>()
  const [detail, setDetail] = useState<MaterialPriceDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadRecords = async (nextPage = page) => {
    // 未输入关键词且未选筛选时不查询，页面保持空态
    if (!keyword.trim() && !costCategory && !subInventory && dataYear === undefined) {
      setRecords([])
      setTotal(0)
      setPage(1)
      return
    }
    setLoading(true)
    try {
      const response = await fetchMaterialPrices({
        keyword: keyword.trim() || undefined,
        cost_category: costCategory,
        sub_inventory: subInventory,
        year: dataYear,
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setRecords(response.data ?? [])
      setTotal(Number(response.meta?.total ?? response.data?.length ?? 0))
      setPage(nextPage)
    } catch {
      message.error('物料价格加载失败')
    } finally {
      setLoading(false)
    }
  }

  const openDetail = async (record: MaterialPriceSummary) => {
    setDetailOpen(true)
    setDetail(null)
    setDetailLoading(true)
    try {
      const response = await fetchMaterialPriceDetail(record.material_code)
      setDetail(response.data)
    } catch {
      message.error('物料价格详情加载失败')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const chartOption = useMemo(() => buildChartOption(detail), [detail])

  const columns: TableProps<MaterialPriceSummary>['columns'] = [
    {
      title: '物料编码',
      dataIndex: 'material_code',
      key: 'material_code',
      width: 150,
      fixed: 'left',
    },
    {
      title: '物料名称',
      dataIndex: 'material_name',
      key: 'material_name',
      width: 280,
      ellipsis: true,
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 80,
    },
    {
      title: '成本类别',
      dataIndex: 'cost_category',
      key: 'cost_category',
      width: 120,
      render: (value: string) => (value ? <Tag>{value}</Tag> : '-'),
    },
    {
      title: '最近年度',
      dataIndex: 'latest_year',
      key: 'latest_year',
      width: 100,
    },
    {
      title: '均价',
      dataIndex: 'avg_price',
      key: 'avg_price',
      width: 110,
      align: 'right',
      render: (value, record) => (
        <Space size={4}>
          <span>{formatPrice(value)}</span>
          {record.has_suspicious && (
            <Tooltip title="历史批次中存在单位换算或录入异常的价格">
              <InfoCircleOutlined className="text-[var(--color-warning)]" />
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: '价格区间',
      key: 'price_range',
      width: 150,
      align: 'right',
      render: (_, record) =>
        `${formatPrice(record.min_price)} ~ ${formatPrice(record.max_price)}`,
    },
    {
      title: '批次',
      dataIndex: 'batch_count',
      key: 'batch_count',
      width: 80,
      align: 'right',
    },
    {
      title: '供应商',
      dataIndex: 'supplier_count',
      key: 'supplier_count',
      width: 90,
      align: 'right',
    },
    {
      title: '最近入库价',
      key: 'live_latest_price',
      width: 150,
      align: 'right',
      render: (_, record) =>
        record.live_latest_price ? (
          <Tooltip title={`仓储最近入库 ${record.live_latest_date ?? ''}`}>
            <span className="font-medium">
              {formatPrice(record.live_latest_price)}
            </span>
          </Tooltip>
        ) : (
          '-'
        ),
    },
  ]

  const yearColumns: TableProps<MaterialPriceYear>['columns'] = [
    { title: '年度', dataIndex: 'data_year', key: 'data_year', width: 90 },
    {
      title: '均价',
      dataIndex: 'avg_price',
      key: 'avg_price',
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '最低',
      dataIndex: 'min_price',
      key: 'min_price',
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '最高',
      dataIndex: 'max_price',
      key: 'max_price',
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '记录数',
      dataIndex: 'batch_count',
      key: 'batch_count',
      align: 'right',
    },
  ]

  const batchColumns: TableProps<MaterialPriceBatch>['columns'] = [
    { title: '年度', dataIndex: 'data_year', key: 'data_year', width: 80 },
    {
      title: '批次',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 140,
      ellipsis: true,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      ellipsis: true,
      render: (value: string) => value || '未记录',
    },
    {
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 110,
      align: 'right',
      render: (value, record) => (
        <Space size={4}>
          <span>{formatPrice(value)}</span>
          {record.price_flag === 'suspicious' && (
            <Tag color="warning">异常</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      width: 130,
      align: 'right',
      render: (value) => formatMoney(value),
    },
    {
      title: '仓库',
      dataIndex: 'sub_inventory',
      key: 'sub_inventory',
      width: 130,
      ellipsis: true,
    },
  ]

  const liveColumns: TableProps<MaterialPriceBatch>['columns'] = [
    {
      title: '入库日期',
      dataIndex: 'data_date',
      key: 'data_date',
      width: 120,
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: '批次',
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 150,
      ellipsis: true,
    },
    {
      title: '供应商',
      dataIndex: 'supplier_name',
      key: 'supplier_name',
      ellipsis: true,
      render: (value: string) => value || '未记录',
    },
    {
      title: '单价',
      dataIndex: 'unit_price',
      key: 'unit_price',
      width: 110,
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 100,
      align: 'right',
      render: (value) => formatPrice(value),
    },
    {
      title: '金额',
      dataIndex: 'amount',
      key: 'amount',
      width: 130,
      align: 'right',
      render: (value) => formatMoney(value),
    },
    {
      title: '车间',
      dataIndex: 'department',
      key: 'department',
      width: 130,
      ellipsis: true,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">
            采购管理 / 物料价格
          </p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            物料价格查询
          </h1>
        </div>
        {mode === 'query' && (
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => void loadRecords(page)}
          >
            刷新
          </Button>
        )}
      </div>

      <Segmented
        value={mode}
        onChange={(value) => {
          setDetailOpen(false)
          setMode(value as MaterialPriceMode)
        }}
        options={[
          { label: '价格查询', value: 'query' },
          { label: '表格补价', value: 'fill' },
        ]}
      />

      {mode === 'fill' && <MaterialPriceFillPanel />}

      {mode === 'query' && (
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
          <div className="grid gap-3 border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4 md:grid-cols-[minmax(220px,1.4fr)_180px_200px_140px_auto]">
          <Input.Search
            allowClear
            enterButton={<SearchOutlined />}
            placeholder="物料编码、名称或别名"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={() => void loadRecords(1)}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="成本类别"
            value={costCategory}
            options={costCategoryOptions}
            onChange={setCostCategory}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="子库存"
            value={subInventory}
            options={subInventoryOptions}
            onChange={setSubInventory}
          />
          <Select
            allowClear
            placeholder="年度"
            value={dataYear}
            options={yearOptions}
            onChange={setDataYear}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            loading={loading}
            onClick={() => void loadRecords(1)}
          >
            查询
          </Button>
        </div>

        <Table<MaterialPriceSummary>
          columns={columns}
          dataSource={records}
          loading={loading}
          rowKey="material_code"
          scroll={{ x: 1500 }}
          onRow={(record) => ({
            onClick: () => void openDetail(record),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize: DEFAULT_PAGE_SIZE,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条`,
            onChange: (nextPage) => void loadRecords(nextPage),
          }}
          locale={{ emptyText: '未找到匹配的物料价格记录' }}
          />
        </section>
      )}

      <Drawer
        size={960}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={
          detail
            ? `${detail.material_code} · ${detail.material_name || '物料价格'}`
            : '物料价格详情'
        }
        loading={detailLoading}
      >
        {detail && (
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-4">
              <div>
                <p className="text-[12px] text-[var(--color-stone)]">单位</p>
                <p className="text-[15px] font-medium text-[var(--color-charcoal)]">
                  {detail.unit || '-'}
                </p>
              </div>
              <div>
                <p className="text-[12px] text-[var(--color-stone)]">成本类别</p>
                <p className="text-[15px] font-medium text-[var(--color-charcoal)]">
                  {detail.cost_category || '-'}
                </p>
              </div>
              <div>
                <p className="text-[12px] text-[var(--color-stone)]">物料类别</p>
                <p className="text-[15px] font-medium text-[var(--color-charcoal)]">
                  {detail.material_category || '-'}
                </p>
              </div>
              <div>
                <p className="text-[12px] text-[var(--color-stone)]">子库存</p>
                <p className="text-[15px] font-medium text-[var(--color-charcoal)]">
                  {detail.sub_inventory || '-'}
                </p>
              </div>
            </div>

            {(detail.years?.length ?? 0) > 1 && (
              <div className="rounded-[12px] border border-[var(--color-hairline)] p-4">
                <h3 className="mb-2 text-[15px] font-semibold text-[var(--color-charcoal)]">
                  年度价格走势
                </h3>
                <ThemedEChart style={{ height: 260 }} option={chartOption} />
              </div>
            )}

            <div>
              <h3 className="mb-2 text-[15px] font-semibold text-[var(--color-charcoal)]">
                年度汇总
              </h3>
              <Table<MaterialPriceYear>
                columns={yearColumns}
                dataSource={detail.years ?? []}
                rowKey="data_year"
                size="small"
                bordered
                pagination={false}
              />
            </div>

            <div>
              <h3 className="mb-2 text-[15px] font-semibold text-[var(--color-charcoal)]">
                价格明细
              </h3>
              <Table<MaterialPriceBatch>
                columns={batchColumns}
                dataSource={detail.batches}
                rowKey="id"
                size="small"
                bordered
                pagination={{ pageSize: 20, hideOnSinglePage: true }}
                scroll={{ x: 1100 }}
              />
            </div>

            {(detail.live_batches?.length ?? 0) > 0 && (
              <div>
                <h3 className="mb-2 text-[15px] font-semibold text-[var(--color-charcoal)]">
                  仓储实时入库
                </h3>
                <Table<MaterialPriceBatch>
                  columns={liveColumns}
                  dataSource={detail.live_batches ?? []}
                  rowKey="id"
                  size="small"
                  bordered
                  pagination={{ pageSize: 20, hideOnSinglePage: true }}
                  scroll={{ x: 1000 }}
                />
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  )
}