'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Card, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getSalesPlanDetails } from '@/actions/production'
import {
  PRODUCT_COLORS,
  PRODUCT_LINE_ORDER,
  PRODUCT_NAME_TO_CODE,
} from './product-colors'
import type { SalesPlanDetail } from '@/types/production'

const dash = '--'
// 语义色与生产汇总表分档一致：达成绿 / 偏低橙 / 异常红
const RATE_GREEN = '#52c41a'
const RATE_ORANGE = '#fa8c16'
const ALERT_RED = '#cf1322'

function rateColor(rate: number): string {
  if (rate >= 100) return RATE_GREEN
  if (rate >= 70) return 'var(--color-primary)'
  return RATE_ORANGE
}

// 完成率为飞书同步的百分数口径（源表 100 即 100%），进度条 + 1 位小数百分比
function RateCell({ rate }: { rate: number | null | undefined }) {
  if (rate == null) {
    return <span style={{ color: 'var(--color-muted)' }}>{dash}</span>
  }
  const color = rateColor(rate)
  return (
    <div className="flex items-center gap-3">
      <div
        data-rate-bar={color}
        style={{
          width: 80,
          height: 10,
          borderRadius: 5,
          background: 'var(--color-hairline-soft)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${Math.min(rate, 100)}%`,
            height: '100%',
            borderRadius: 5,
            background: color,
          }}
        />
      </div>
      <span style={{ fontSize: 18, fontWeight: 600, color }}>
        {Math.round(rate * 10) / 10}%
      </span>
    </div>
  )
}

// 数值字号沿用生产汇总表两档：成果数字 24px 加粗（大），其余 18px（中）
function NumCell({
  v,
  tone,
  big = false,
}: {
  v: number | null | undefined
  tone?: string
  big?: boolean
}) {
  if (v == null) {
    return <span style={{ color: 'var(--color-muted)' }}>{dash}</span>
  }
  return (
    <span
      className="whitespace-nowrap"
      style={{
        fontSize: big ? 24 : 18,
        fontWeight: big ? 600 : 500,
        color: tone ?? (big ? 'var(--color-primary-deep)' : undefined),
      }}
    >
      {v.toLocaleString('zh-CN')}
    </span>
  )
}

// 行序与生产汇总表对齐（同一产品同一行位），未收录产线（如盐酸林可霉素）按源顺序排在其后
function orderIndex(row: SalesPlanDetail): number {
  const code = PRODUCT_NAME_TO_CODE[row.product_name ?? '']
  if (!code) return Number.MAX_SAFE_INTEGER
  return PRODUCT_LINE_ORDER.findIndex((line) => line.code === code)
}

// 汇总视图·产销计划卡：取产销计划「销售计划执行表」按概览月份数据，
// 与生产汇总表同版式（产线色条、固定行序、进度条完成率），
// 仅展示概览所需的 10 列；开票量、备注等全量字段仍在产销计划页查看
export default function SalesPlanCard({ month }: { month: string }) {
  const [rows, setRows] = useState<SalesPlanDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadSales = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // 当月产品行数有限，一次拉全展示，卡片内不分页
      const res = await getSalesPlanDetails({ page: 1, page_size: 200, month })
      if (res.code === 200) {
        setRows(res.data || [])
      } else {
        setRows([])
        setError(res.message || '销售计划数据加载失败')
      }
    } catch {
      setRows([])
      setError('销售计划数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [month])

  useEffect(() => {
    void loadSales() // eslint-disable-line react-hooks/set-state-in-effect -- 数据随月份切换加载
  }, [loadSales])

  const sortedRows = useMemo(
    () => [...rows].sort((a, b) => orderIndex(a) - orderIndex(b)),
    [rows],
  )

  // 不设固定列宽与 scroll.x，让表格自适应容器宽度，避免出现横向滚动条
  const columns: ColumnsType<SalesPlanDetail> = [
    {
      title: '产品',
      dataIndex: 'product_name',
      render: (name: string) => (
        <span className="flex items-center gap-2">
          <span
            style={{
              width: 6,
              height: 20,
              borderRadius: 3,
              background:
                PRODUCT_COLORS[PRODUCT_NAME_TO_CODE[name] ?? ''] ??
                'var(--color-muted)',
            }}
          />
          <span style={{ fontSize: 16, fontWeight: 600 }}>{name}</span>
        </span>
      ),
    },
    { title: '单位', dataIndex: 'unit', render: (v: string | null) => v || dash },
    {
      title: '上月已发货未开票',
      dataIndex: 'last_month_delivered_uninvoiced',
      render: (v: number | null) => <NumCell v={v} />,
    },
    {
      title: '本月计划发货量',
      dataIndex: 'month_planned_delivery',
      render: (v: number | null) => <NumCell v={v} />,
    },
    {
      title: '本月已发货量',
      dataIndex: 'month_delivered_qty',
      render: (v: number | null) => <NumCell v={v} big />,
    },
    {
      title: '未发货量',
      dataIndex: 'undelivered_qty',
      render: (v: number | null) => (
        <NumCell v={v} tone={v != null && v > 0 ? RATE_ORANGE : undefined} />
      ),
    },
    {
      title: '本月发货完成率',
      dataIndex: 'delivery_completion_rate',
      render: (rate: number | null) => <RateCell rate={rate} />,
    },
    {
      title: '上月底库存',
      dataIndex: 'last_month_end_inventory',
      render: (v: number | null) => <NumCell v={v} />,
    },
    {
      title: '本月预计产能',
      dataIndex: 'month_planned_capacity',
      render: (v: number | null) => <NumCell v={v} />,
    },
    {
      title: '本月底库存',
      dataIndex: 'month_end_inventory',
      render: (v: number | null) => (
        <NumCell v={v} tone={v != null && v < 0 ? ALERT_RED : undefined} />
      ),
    },
  ]

  return (
    <Card
      variant="borderless"
      className="shadow-sm"
      styles={{ body: { padding: '12px 20px' } }}
    >
      <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
        {/* 卡内小标题：与汇总播报标签同版式，保持汇总区各卡片视觉一致 */}
        <span className="text-xs font-semibold" style={{ color: 'var(--color-primary)' }}>
          产销计划
        </span>
        <span style={{ fontSize: 13, color: 'var(--color-muted)' }}>
          数据月份 {month}
        </span>
      </div>
      {error ? (
        <Alert type="warning" showIcon message={error} />
      ) : (
        <Table
          columns={columns}
          dataSource={sortedRows}
          rowKey="id"
          loading={loading}
          pagination={false}
          className="sales-plan-table"
          locale={{ emptyText: '暂无销售计划数据，请先完成飞书同步设置并同步' }}
        />
      )}
      <style>{`
        /* 销售计划表：与生产汇总表同版式字号与行距；水平内边距收紧让 10 列在
           1280px 宽度内放下，避免横向滚动 */
        .sales-plan-table .ant-table-thead > tr > th {
          font-size: 14px;
          font-weight: 600;
          white-space: nowrap;
          padding: 14px 10px;
        }
        .sales-plan-table .ant-table-tbody > tr > td {
          padding: 18px 10px;
          white-space: nowrap;
        }
      `}</style>
    </Card>
  )
}
