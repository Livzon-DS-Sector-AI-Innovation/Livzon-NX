'use client'

// 维修效能卡片：车间切换 + 月度趋势（纯 CSS 条形）+ 故障 TOP10 + 空态。
// 数据源 GET /equipment/maintenance/work-orders/efficiency（只读聚合）。

import { useCallback, useMemo, useState } from 'react'
import { Card, Divider, Select, Space, Tag, Typography } from 'antd'
import {
  BarChartOutlined,
  FireFilled,
  ReloadOutlined,
  ThunderboltFilled,
} from '@ant-design/icons'
import type { EfficiencyStatistics } from '@/types/equipment'
import { fmtMinutes } from './efficiency-format'

const { Text, Title } = Typography

export interface EfficiencyWorkshopOption {
  code: string
  name: string
}

interface EfficiencyCardProps {
  initialData: EfficiencyStatistics | null
  workshopOptions: EfficiencyWorkshopOption[]
  initialWorkshop?: string
  onWorkshopChange?: (workshop: string) => void
  /** 每次数据加载完成（含车间切换）后回传整份数据，供同排卡片联动展示 */
  onData?: (data: EfficiencyStatistics | null) => void
}

function fmtRate(rate: number | null): string {
  if (rate === null) return '—'
  return `${Math.round(rate * 100)}%`
}

export function EfficiencyCard({
  initialData,
  workshopOptions,
  initialWorkshop = '',
  onWorkshopChange,
  onData,
}: EfficiencyCardProps) {
  const [workshop, setWorkshop] = useState(initialWorkshop)
  const [data, setData] = useState<EfficiencyStatistics | null>(initialData)
  const [loading, setLoading] = useState(false)

  const publish = useCallback(
    (next: EfficiencyStatistics | null) => {
      setData(next)
      onData?.(next)
    },
    [onData],
  )

  const load = useCallback(
    async (ws: string) => {
      setLoading(true)
      try {
        const { fetchEfficiencyStatistics } = await import('@/actions/equipment')
        const next = await fetchEfficiencyStatistics(ws || undefined)
        publish(next)
      } catch {
        // 保持上次数据；聚合接口失败不阻塞页面
      } finally {
        setLoading(false)
      }
    },
    [publish],
  )

  const handleSelect = useCallback(
    (value: string) => {
      setWorkshop(value)
      onWorkshopChange?.(value)
      void load(value)
    },
    [onWorkshopChange, load],
  )

  const maxTotal = useMemo(
    () => Math.max(1, ...(data?.monthly ?? []).map((m) => m.total)),
    [data],
  )
  // 补齐空月份：横轴始终展示完整区间，避免单月数据时只剩一根孤柱
  const filledMonths = useMemo(() => {
    const byMonth = new Map((data?.monthly ?? []).map((m) => [m.month, m]))
    const months: {
      month: string; total: number; completed: number; urgent: number
      avg_response: number; avg_repair: number
    }[] = []
    const now = new Date()
    for (let i = 5; i >= 0; i -= 1) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      months.push(
        byMonth.get(key) ?? {
          month: key, total: 0, completed: 0, urgent: 0,
          avg_response: 0, avg_repair: 0,
        },
      )
    }
    return months
  }, [data])
  const maxCount = useMemo(
    () => Math.max(1, ...(data?.top_faults ?? []).map((t) => t.order_count)),
    [data],
  )
  const hasData = (data?.total_orders ?? 0) > 0
  // 近 N 个月汇总：填补左列与 TOP10 右列的高度差，避免左列下半空白
  const summary = useMemo(() => {
    const total = filledMonths.reduce((acc, m) => acc + m.total, 0)
    const completed = filledMonths.reduce((acc, m) => acc + m.completed, 0)
    const urgent = filledMonths.reduce((acc, m) => acc + m.urgent, 0)
    return {
      total,
      completed,
      urgent,
      completionRate: total > 0 ? Math.round((completed / total) * 100) : null,
    }
  }, [filledMonths])

  return (
    <Card
      loading={loading && !data}
      title={
        <Space size={8}>
          <BarChartOutlined style={{ color: '#5645d4' }} />
          <span>维修效能</span>
        </Space>
      }
      extra={
        <Space size={12}>
          <Select
            aria-label="车间筛选"
            value={workshop}
            onChange={handleSelect}
            style={{ width: 150 }}
            options={[
              { value: '', label: '全工厂' },
              ...workshopOptions.map((w) => ({ value: w.code, label: w.name })),
            ]}
          />
          <ReloadOutlined
            style={{ color: '#787671', cursor: 'pointer' }}
            aria-label="刷新效能数据"
            onClick={() => void load(workshop)}
          />
        </Space>
      }
      style={{ marginBottom: 28 }}
    >
      {!hasData ? (
        <div
          style={{ padding: '32px 0', textAlign: 'center' }}
          data-testid="efficiency-empty"
        >
          <Text type="secondary">暂无维修数据</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            工单产生后此处展示响应时长、修复时长与故障排行
          </Text>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
            gap: 24,
          }}
        >
          {/* 左列：指标 + 月度趋势 + 近6个月汇总（flex 贴底，对齐右列高度） */}
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <Space size={16} wrap style={{ marginBottom: 16 }}>
              <span data-testid="eff-avg-response">
                <Text type="secondary" style={{ fontSize: 12 }}>平均响应 </Text>
                <Title level={4} style={{ margin: 0 }}>
                  {fmtMinutes(data?.avg_response_minutes ?? 0)}
                </Title>
              </span>
              <span data-testid="eff-avg-repair">
                <Text type="secondary" style={{ fontSize: 12 }}>MTTR </Text>
                <Title level={4} style={{ margin: 0 }}>
                  {fmtMinutes(data?.avg_repair_minutes ?? 0)}
                </Title>
              </span>
              <span data-testid="eff-urgent-rate">
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <ThunderboltFilled style={{ color: '#fa8c16' }} /> 紧急达标{' '}
                </Text>
                <Title level={4} style={{ margin: 0 }}>
                  {fmtRate(data?.urgent_5min_rate ?? null)}
                </Title>
              </span>
            </Space>

            <Space size={12} style={{ marginBottom: 8 }}>
              <Text strong style={{ fontSize: 13 }}>月度工单走势</Text>
              <Text type="secondary" style={{ fontSize: 11 }}>
                <span
                  style={{
                    display: 'inline-block',
                    width: 10, height: 10,
                    borderRadius: 2,
                    background: 'linear-gradient(180deg,#5645d4,#8779f0)',
                    marginRight: 4,
                  }}
                />普通
                <span
                  style={{
                    display: 'inline-block',
                    width: 10, height: 10,
                    borderRadius: 2,
                    background: 'linear-gradient(180deg,#fa8c16,#faad14)',
                    margin: '0 4px 0 10px',
                  }}
                />含紧急
              </Text>
            </Space>
            <div
              data-testid="eff-monthly"
              style={{
                display: 'flex',
                alignItems: 'flex-end',
                gap: 8,
                height: 150,
              }}
            >
              {filledMonths.map((m) => (
                <div
                  key={m.month}
                  style={{ flex: 1, textAlign: 'center' }}
                  title={m.total > 0
                    ? `${m.month}：${m.total} 单（完成 ${m.completed}，紧急 ${m.urgent}），平均响应 ${fmtMinutes(m.avg_response)}，修复 ${fmtMinutes(m.avg_repair)}`
                    : `${m.month}：无工单`}
                >
                  <Text style={{ fontSize: 11 }}>{m.total > 0 ? `${m.total}单` : '—'}</Text>
                  <div
                    style={{
                      height: m.total > 0
                        ? `${(m.total / maxTotal) * 92}px`
                        : 8,
                      background: m.total === 0
                        ? '#ecebeb'
                        : m.urgent > 0
                          ? 'linear-gradient(180deg,#fa8c16,#faad14)'
                          : 'linear-gradient(180deg,#5645d4,#8779f0)',
                      borderRadius: 4,
                      margin: '0 auto',
                      width: '56%',
                    }}
                  />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {m.month.slice(5)}月
                  </Text>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 'auto' }}>
              <Divider style={{ margin: '4px 0 10px' }} />
              <div
                data-testid="eff-summary"
                style={{
                  display: 'flex',
                  gap: 20,
                  flexWrap: 'wrap',
                }}
              >
                <span>
                  <Text type="secondary" style={{ fontSize: 12 }}>近6个月工单 </Text>
                  <Text strong style={{ fontSize: 14 }}>{summary.total}单</Text>
                </span>
                <span>
                  <Text type="secondary" style={{ fontSize: 12 }}>已完成 </Text>
                  <Text strong style={{ fontSize: 14 }}>{summary.completed}单</Text>
                </span>
                <span>
                  <Text type="secondary" style={{ fontSize: 12 }}>含紧急 </Text>
                  <Text strong style={{ fontSize: 14 }}>{summary.urgent}单</Text>
                </span>
                <span>
                  <Text type="secondary" style={{ fontSize: 12 }}>完成率 </Text>
                  <Text strong style={{ fontSize: 14 }}>
                    {summary.completionRate === null ? '—' : `${summary.completionRate}%`}
                  </Text>
                </span>
              </div>
            </div>
          </div>

          {/* 右列：故障 TOP10 */}
          <div>
            <Space size={6} style={{ marginBottom: 10 }}>
              <FireFilled style={{ color: '#fa541c' }} />
              <Text strong style={{ fontSize: 13 }}>故障 TOP{data?.top_faults.length ?? 0}</Text>
            </Space>
            <div data-testid="eff-top-faults">
              {(data?.top_faults ?? []).map((t, i) => (
                <div
                  key={t.equipment_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '4px 0',
                  }}
                >
                  <Text
                    strong={i < 3}
                    style={{ width: 20, fontSize: 12, color: i < 3 ? '#fa541c' : undefined }}
                  >
                    {i + 1}
                  </Text>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Text ellipsis style={{ flex: 1, fontSize: 13 }}>
                        {t.equipment_name}
                        {t.equipment_no ? `（${t.equipment_no}）` : ''}
                      </Text>
                      {workshop === '' && t.workshop_code ? (
                        <Tag style={{ fontSize: 11, lineHeight: '16px' }}>
                          {t.workshop_code}
                        </Tag>
                      ) : null}
                    </div>
                    <div
                      style={{
                        height: 6,
                        borderRadius: 3,
                        background: '#f0efeD',
                        marginTop: 3,
                      }}
                    >
                      <div
                        style={{
                          width: `${(t.order_count / maxCount) * 100}%`,
                          minWidth: 6,
                          height: '100%',
                          borderRadius: 3,
                          background: i < 3 ? '#fa541c' : '#fa8c16',
                          opacity: 1 - i * 0.07,
                        }}
                      />
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', minWidth: 56 }}>
                    <Text strong style={{ fontSize: 13 }}>{t.order_count}次</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      均{fmtMinutes(t.avg_repair_minutes)}
                    </Text>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
