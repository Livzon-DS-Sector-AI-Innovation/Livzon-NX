'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Alert, Card, Spin, Table, Tag, Typography } from 'antd'
import { getProductionSummary } from '@/actions/production'
import type { ProductionSummaryRow } from '@/types/production'

const { Text } = Typography

const dash = '--'

// 产线识别色（与顶部导航块一致；色相互不重叠，新增红/金避开既有紫蓝橙绿玫红青）
const PRODUCT_COLORS: Record<string, string> = {
  MC: '#1677ff',
  DR: '#d46b08',
  FA: '#389e0d',
  LV: '#c41d7f',
  MV: '#08979c',
  TY: '#cf1322',
  FL: '#d4b106',
}

// 比率分档配色：≥100 绿（达成/超额）、70~100 主色（正常推进）、<70 橙（偏低）
function rateColor(rate: number): string {
  if (rate >= 100) return '#52c41a'
  if (rate >= 70) return 'var(--color-primary)'
  return '#fa8c16'
}

/** 数值格：成果数字 24px 加粗（大），计划数字 18px（中），单位小字灰 */
function ValueCell({
  v,
  digits = 0,
  unit,
  big = false,
}: {
  v: number | null
  digits?: number
  unit: string
  big?: boolean
}) {
  if (v == null) return <span style={{ color: 'var(--color-muted)' }}>{dash}</span>
  return (
    <span className="whitespace-nowrap">
      <span
        style={{
          fontSize: big ? 24 : 18,
          fontWeight: big ? 600 : 500,
          color: big ? 'var(--color-primary-deep)' : undefined,
        }}
      >
        {v.toLocaleString('zh-CN', {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        })}
      </span>
      <span style={{ fontSize: 12, color: 'var(--color-muted)', marginLeft: 4 }}>
        {unit}
      </span>
    </span>
  )
}

/** 比率格：120px 加宽进度条（10px 高）+ 18px 加粗百分比，分档变色 */
function RateCell({ rate }: { rate: number | null }) {
  if (rate == null) {
    return <span style={{ color: 'var(--color-muted)' }}>{dash}</span>
  }
  const clamped = Math.min(rate, 100)
  const color = rateColor(rate)
  return (
    <div className="flex items-center gap-3">
      <div
        data-rate-bar={color}
        style={{
          width: 120,
          height: 10,
          borderRadius: 5,
          background: 'var(--color-hairline-soft)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${clamped}%`,
            height: '100%',
            borderRadius: 5,
            background: color,
          }}
        />
      </div>
      <span style={{ fontSize: 18, fontWeight: 600, color }}>{rate}%</span>
    </div>
  )
}

function fermentCell(
  row: ProductionSummaryRow,
  key: 'planned_batches' | 'planned_capacity_kg' | 'done_yield_kg',
): React.ReactNode {
  if (!row.ferment) return dash
  const v = row.ferment[key]
  if (v == null) return dash
  // 已完成产能为实测口径，保留两位小数（与单产品看板「发酵已完成产能」一致）；
  // 计划批次数仅小数批（他汀折算）带小数；月计划产能维持整数
  const digits =
    key === 'done_yield_kg' || (key === 'planned_batches' && v % 1) ? 2 : 0
  const unit = key === 'planned_batches' ? '批' : 'kg'
  return <ValueCell v={v} digits={digits} unit={unit} big={key === 'done_yield_kg'} />
}

function extractCell(
  row: ProductionSummaryRow,
  key: 'planned_yield_kg' | 'finished_inbound_kg',
): React.ReactNode {
  if (!row.extract) return dash
  const v = row.extract[key]
  if (v == null) return dash
  return <ValueCell v={v} unit="kg" big={key === 'finished_inbound_kg'} />
}

/** 生产汇总：五产线聚合播报（无缝跑马灯）+ 关键指标大表（跟随概览月份切换） */
export default function ProductionSummary({ month }: { month: string }) {
  const [rows, setRows] = useState<ProductionSummaryRow[]>([])
  const [periodLabel, setPeriodLabel] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadSummary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // 取当月 15 日为参考日：稳定落在该月扎帐周期（27日～26日）内
      const res = await getProductionSummary(`${month}-15`)
      if (res.code === 200 && res.data) {
        setRows(res.data.rows || [])
        setPeriodLabel(res.data.period?.label ?? '')
      } else {
        setRows([])
        setError(res.message || '汇总数据加载失败')
      }
    } catch {
      setRows([])
      setError('汇总数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [month])

  useEffect(() => {
    void loadSummary() // eslint-disable-line react-hooks/set-state-in-effect -- 数据随月份切换加载
  }, [loadSummary])

  // 播报汇总：五条产线合并；内容复制两份做无缝循环（播完一份接第二份）
  const mergedAlerts = rows.flatMap((r) =>
    (r.alerts || []).map((a) => ({
      ...a,
      product: r.product_name,
      productCode: r.product_code,
    })),
  )

  // 恒速跑马灯：按单份内容实测宽度换算动画时长（速度 130px/s，最短 8s）
  const MARQUEE_SPEED = 130
  const marqueeRef = useRef<HTMLDivElement | null>(null)
  const [marqueeDuration, setMarqueeDuration] = useState(60)
  useLayoutEffect(() => {
    const el = marqueeRef.current
    if (!el) return
    const measure = () => {
      const half = el.scrollWidth / 2
      if (half > 0) setMarqueeDuration(Math.max(8, half / MARQUEE_SPEED))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [mergedAlerts])
  const marqueeItems = [...mergedAlerts, ...mergedAlerts]

  const columns = [
    {
      title: '产线',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 200,
      render: (name: string, row: ProductionSummaryRow) => (
        <span className="flex items-center gap-2">
          <span
            style={{
              width: 6,
              height: 20,
              borderRadius: 3,
              background: PRODUCT_COLORS[row.product_code] ?? 'var(--color-muted)',
            }}
          />
          <span style={{ fontSize: 16, fontWeight: 600 }}>{name}</span>
          {!row.covered && (
            <Tag style={{ marginInlineEnd: 0 }} color="default">
              排产未覆盖
            </Tag>
          )}
        </span>
      ),
    },
    {
      title: '发酵月计划批次',
      key: 'planned_batches',
      render: (_: unknown, row: ProductionSummaryRow) =>
        fermentCell(row, 'planned_batches'),
    },
    {
      title: '发酵月计划产能(kg)',
      key: 'planned_capacity_kg',
      render: (_: unknown, row: ProductionSummaryRow) =>
        fermentCell(row, 'planned_capacity_kg'),
    },
    {
      title: '发酵已完成产能(kg)',
      key: 'done_yield_kg',
      render: (_: unknown, row: ProductionSummaryRow) =>
        fermentCell(row, 'done_yield_kg'),
    },
    {
      title: '发酵产能达成率',
      key: 'capacity_rate',
      width: 240,
      render: (_: unknown, row: ProductionSummaryRow) => (
        <RateCell rate={row.ferment?.capacity_rate ?? null} />
      ),
    },
    {
      title: '提炼计划产量(kg)',
      key: 'planned_yield_kg',
      render: (_: unknown, row: ProductionSummaryRow) =>
        extractCell(row, 'planned_yield_kg'),
    },
    {
      title: '提炼已出成品(kg)',
      key: 'finished_inbound_kg',
      render: (_: unknown, row: ProductionSummaryRow) =>
        extractCell(row, 'finished_inbound_kg'),
    },
    {
      title: '提炼完成率',
      key: 'completion_rate',
      width: 240,
      render: (_: unknown, row: ProductionSummaryRow) => (
        <RateCell rate={row.extract?.completion_rate ?? null} />
      ),
    },
  ]

  return (
    <>
      {/* 播报汇总：五产线播报合并为无缝循环跑马灯，前缀来源产品（两行高，无滚动条） */}
      <Card
        variant="borderless"
        className="shadow-sm"
        styles={{ body: { padding: '8px 16px', overflow: 'hidden' } }}
      >
        {mergedAlerts.length > 0 ? (
          <>
            <div className="flex items-center gap-3 overflow-hidden">
              <span
                className="flex-shrink-0 text-xs font-semibold"
                style={{ color: 'var(--color-primary)' }}
              >
                汇总播报
              </span>
              <div className="overflow-hidden flex-1">
                <div
                  className="production-summary-marquee"
                  ref={marqueeRef}
                  style={{ animationDuration: `${marqueeDuration}s` }}
                >
                {marqueeItems.map((a, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center gap-2"
                    style={{ fontSize: 13, marginRight: 48 }}
                  >
                    <span
                      style={{
                        color: PRODUCT_COLORS[a.productCode] ?? 'var(--color-primary)',
                        fontWeight: 600,
                      }}
                    >
                      【{a.product}】
                    </span>
                    {a.text}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <style>{`
            .production-summary-marquee {
              display: block;
              white-space: nowrap;
              width: max-content;
              animation: production-summary-marquee 60s linear infinite;
            }
            @keyframes production-summary-marquee {
              0% { transform: translateX(0); }
              100% { transform: translateX(-50%); }
            }
          `}</style>
          </>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--color-muted)' }}>
            车间运行正常，无待处理播报
          </span>
        )}
      </Card>

      <Card
        variant="borderless"
        className="shadow-sm"
        styles={{ body: { padding: '4px 20px 12px' } }}
      >
        {periodLabel && (
          <Text type="secondary" style={{ fontSize: 13 }}>
            生产周期 {periodLabel}
          </Text>
        )}
        {error ? (
          <Alert type="warning" showIcon message={error} />
        ) : (
          <Spin spinning={loading}>
            <Table
              rowKey="product_code"
              columns={columns}
              dataSource={rows}
              pagination={false}
              scroll={{ x: 1400 }}
              className="production-summary-table"
            />
          </Spin>
        )}
      </Card>
      <style>{`
        /* 生产汇总表：大气版字号与行距 */
        .production-summary-table .ant-table-thead > tr > th {
          font-size: 14px;
          font-weight: 600;
          white-space: nowrap;
          padding: 14px 16px;
        }
        .production-summary-table .ant-table-tbody > tr > td {
          padding: 18px 16px;
          white-space: nowrap;
        }
        .production-summary-table .ant-table-tbody > tr:last-child > td {
          border-top: 2px solid var(--color-primary);
          background: var(--color-primary-soft, #f0f7ff);
        }
      `}</style>
    </>
  )
}
