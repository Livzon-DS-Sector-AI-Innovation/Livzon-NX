'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {  Col, InputNumber, Row, Spin, Typography } from 'antd'
import type { FeeDashboard, FeeTypeSummary, YearSummary } from '@/types/registration'
import { fetchFeeDashboard } from '@/lib/api/client/registration'
import {
  RegistrationChartCard,
  RegistrationSummaryHero,
  buildDonutOption,
  type RegistrationChartDatum,
  type RegistrationMetricItem,
} from '@/components/registration'
import type { DefaultLabelFormatterCallbackParams, EChartsOption, TooltipComponentFormatterCallbackParams } from 'echarts'

interface FeeDashboardPageProps {
  dashboard: FeeDashboard
  defaultYearFrom?: number
}

const CHART_COLORS = ['#1677ff', '#52c41a', '#fa8c16', '#722ed1', '#eb2f96', '#13c2c2', '#f5222d', '#2f54eb', '#faad14', '#a0d911']

function formatAmount(value: number): string {
  if (value >= 10000) return `¥${(value / 10000).toFixed(1)}万`
  return `¥${value.toLocaleString()}`
}

export default function FeeDashboardPage({ dashboard: initialDashboard, defaultYearFrom = 2023 }: FeeDashboardPageProps) {
  const [yearFrom, setYearFrom] = useState(defaultYearFrom)
  const { data: dashboard = initialDashboard, isLoading: loading } = useQuery({
    queryKey: ['registration-fee', 'dashboard', yearFrom],
    queryFn: () => fetchFeeDashboard(yearFrom),
    initialData: yearFrom === defaultYearFrom ? initialDashboard : undefined,
  })

  // ── Metrics ──────────────────────────────────────────────────────────
  const metrics: RegistrationMetricItem[] = [
    { label: '费用总金额(当年起)', value: formatAmount(Number(dashboard.total_amount)), accent: '#1677ff' },
    { label: '已支付', value: formatAmount(Number(dashboard.paid_amount)), accent: '#52c41a' },
    { label: '待支付', value: formatAmount(Number(dashboard.pending_amount)), accent: '#fa8c16' },
    { label: '总笔数 / 外检机构', value: `${dashboard.total_records} / ${dashboard.inspection_contact_count}`, accent: '#722ed1' },
  ]

  // ── Fee type donut ───────────────────────────────────────────────────
  const feeTypeDonutData: RegistrationChartDatum[] = useMemo(
    () => dashboard.fee_type_summaries
      .filter((s: FeeTypeSummary) => Number(s.total_amount) > 0)
      .slice(0, 8)
      .map((s: FeeTypeSummary) => ({ name: s.fee_type, value: Number(s.total_amount) })),
    [dashboard]
  )
  const feeTypeDonutColors = CHART_COLORS.slice(0, feeTypeDonutData.length)

  // ── Year × Fee Type stacked bar ─────────────────────────────────────
  const stackedBarOption: EChartsOption = useMemo(() => {
    const yearSummaries = [...dashboard.year_summaries].sort((a: YearSummary, b: YearSummary) => a.year - b.year)
    const years = yearSummaries.map(s => String(s.year))
    const feeTypes = dashboard.fee_type_summaries
      .filter(s => Number(s.total_amount) > 0)
      .slice(0, 8)
      .map(s => s.fee_type)

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: TooltipComponentFormatterCallbackParams) => {
          const arr = Array.isArray(params) ? params : [params]
          const year = arr[0]?.name || ''
          let html = `<div style="font-weight:600;margin-bottom:4px">${year}年</div>`
          let total = 0
          for (const p of arr) {
            const val = Number(p.value) || 0
            total += val
            html += `<div style="display:flex;justify-content:space-between;gap:16px"><span>${p.marker}${p.seriesName}</span><span>¥${val.toLocaleString()}</span></div>`
          }
          html += `<div style="border-top:1px solid #eee;margin-top:4px;padding-top:4px;font-weight:600;display:flex;justify-content:space-between"><span>合计</span><span>¥${total.toLocaleString()}</span></div>`
          return html
        },
      },
      legend: {
        bottom: 0,
        itemWidth: 12,
        itemHeight: 12,
        type: 'scroll',
      },
      grid: { left: 80, right: 24, top: 16, bottom: 44 },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: (v: number) => v >= 10000 ? `${(v/10000).toFixed(0)}万` : String(v) },
        splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
      },
      yAxis: {
        type: 'category',
        data: years,
      },
      series: feeTypes.map((type, idx) => ({
        name: type,
        type: 'bar' as const,
        stack: 'total',
        barWidth: 24,
        itemStyle: {
          color: CHART_COLORS[idx % CHART_COLORS.length],
          borderRadius: 0,
        },
        emphasis: { focus: 'series' },
        data: yearSummaries.map(yearSummary => {
          const match = (dashboard.year_fee_type_summaries || []).find(
            s => s.year === yearSummary.year && s.fee_type === type
          )
          return match ? Number(match.total_amount) : 0
        }),
      })),
    }
  }, [dashboard])

  // ── Agency bar (top 10) ──────────────────────────────────────────────
  const agencyBarData: RegistrationChartDatum[] = useMemo(
    () => dashboard.agency_summaries
      .filter(a => Number(a.total_amount) > 0)
      .slice(0, 10)
      .map(a => ({ name: a.agency_name, value: Number(a.total_amount) })),
    [dashboard]
  )

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>注册费用仪表盘</Typography.Title>
        <InputNumber value={yearFrom} min={2000} max={2099} style={{ width: 120 }}
          onChange={(v) => setYearFrom(v || 2023)} />
      </div>

      <Spin spinning={loading}>
        <RegistrationSummaryHero title="" subtitle="" metrics={metrics} />

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={12}>
            <RegistrationChartCard
              title="费用类型分布"
              option={buildDonutOption(feeTypeDonutData, feeTypeDonutColors)}
              hasData={feeTypeDonutData.length > 0}
              height={340}
            />
          </Col>
          <Col xs={24} lg={12}>
            <RegistrationChartCard
              title="年度费用趋势（按类型）"
              option={stackedBarOption}
              hasData={dashboard.year_summaries.length > 0}
              height={340}
            />
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24}>
            <RegistrationChartCard
              title="付款方费用 TOP 10"
              option={{
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
                grid: { left: 140, right: 80, top: 16, bottom: 16 },
                xAxis: { type: 'value', axisLabel: { formatter: (v: number) => v >= 10000 ? `${(v/10000).toFixed(0)}万` : String(v) }, splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } } },
                yAxis: { type: 'category', data: agencyBarData.map(d => d.name), axisLabel: { width: 120, overflow: 'truncate' } },
                series: [{ type: 'bar', data: agencyBarData.map(d => d.value), barWidth: 18, itemStyle: { color: '#fa8c16', borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', formatter: (p: DefaultLabelFormatterCallbackParams) => `¥${Number(p.value).toLocaleString()}` } }],
              }}
              hasData={agencyBarData.length > 0}
              height={420}
            />
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
