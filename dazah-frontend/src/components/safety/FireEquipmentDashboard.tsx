'use client'

import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Row,
  Segmented,
  Typography,
  theme,
} from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  FireOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { EChartsOption } from 'echarts'

import ReactECharts from '@/components/shared/ThemedEChart'
import type { components } from '@/types/generated/schema'

const { Text } = Typography

type FireEquipmentStats = components['schemas']['FireEquipmentStats']
type FireEquipmentDashboardResponse =
  components['schemas']['FireEquipmentDashboardResponse']

const WINDOWS = [7, 15, 30]

// 与 PageFeishuStatsBar 一致的图表配色（紫主色 + 语义色 + 主题线色）
const PRIMARY_COLOR = '#5645d4'
const SUCCESS_COLOR = '#1aae39'
const NEUTRAL_COLOR = '#bfbfbf'
const SPLIT_LINE_COLOR = 'var(--color-hairline-soft)'
const AXIS_LINE_COLOR = 'var(--color-hairline)'

interface Props {
  stats: FireEquipmentStats | null
  dashboard: FireEquipmentDashboardResponse | null
  /** 当前生效的到期穿透筛选（'due_30' 等）；null 表示未筛选 */
  drilling: string | null
  onDrill: (expiryStatus: string | null) => void
  onFilterUninspected: () => void
}

function StatCard({
  icon,
  tone,
  title,
  value,
  subtitle,
  onClick,
}: {
  icon: React.ReactNode
  tone: 'primary' | 'success' | 'warning' | 'danger'
  title: string
  value: number
  subtitle: string
  onClick?: () => void
}) {
  const { token } = theme.useToken()
  const toneBg: Record<string, string> = {
    primary: token.colorPrimaryBg,
    success: token.colorSuccessBg,
    warning: token.colorWarningBg,
    danger: token.colorErrorBg,
  }
  const toneColor: Record<string, string> = {
    primary: token.colorPrimary,
    success: token.colorSuccess,
    warning: token.colorWarning,
    danger: token.colorError,
  }
  return (
    <Card
      size="small"
      hoverable={Boolean(onClick)}
      onClick={onClick}
      data-stat-card={title}
      styles={{ body: { padding: 14 } }}
      style={{ height: '100%' }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <span
          aria-hidden
          style={{
            width: 42,
            height: 42,
            borderRadius: 10,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            background: toneBg[tone],
            color: toneColor[tone],
            flex: 'none',
          }}
        >
          {icon}
        </span>
        <div style={{ minWidth: 0 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {title}
          </Text>
          <div style={{ fontSize: 26, fontWeight: 600, lineHeight: 1.2 }}>
            {value}
          </div>
          <Text
            type="secondary"
            style={{ fontSize: 12, display: 'block' }}
            ellipsis
          >
            {subtitle}
          </Text>
        </div>
      </div>
    </Card>
  )
}

/** 点检仪表盘：指标卡 + 有效期到期提醒 + 点检趋势/车间覆盖图表。 */
export default function FireEquipmentDashboard({
  stats,
  dashboard,
  drilling,
  onDrill,
  onFilterUninspected,
}: Props) {
  const [window, setWindow] = useState(30)
  const summary = dashboard?.expiry_summary
  const within =
    summary?.[`within_${window}` as keyof NonNullable<typeof summary>] ?? 0
  const overdue = summary?.overdue ?? 0
  const trend = useMemo(() => dashboard?.trend ?? [], [dashboard])
  const coverage = useMemo(
    () => dashboard?.workshop_coverage ?? [],
    [dashboard]
  )

  const trendOption: EChartsOption = useMemo(
    () => ({
      grid: { left: 8, right: 12, top: 30, bottom: 4, containLabel: true },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: trend.map((point) => point.month),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
        axisLabel: { fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
      },
      series: [
        {
          name: '点检台数',
          type: 'bar',
          data: trend.map((point) => point.count),
          barMaxWidth: 26,
          itemStyle: { color: PRIMARY_COLOR, borderRadius: [4, 4, 0, 0] },
          label: { show: true, position: 'top', fontSize: 11 },
        },
      ],
    }),
    [trend]
  )

  const coverageOption: EChartsOption = useMemo(
    () => ({
      grid: { left: 8, right: 24, top: 34, bottom: 4, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: {
        top: 2,
        right: 0,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { fontSize: 11 },
      },
      xAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: SPLIT_LINE_COLOR } },
      },
      yAxis: {
        type: 'category',
        data: coverage.map((item) => item.tab_name),
        inverse: true,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: AXIS_LINE_COLOR } },
        axisLabel: { fontSize: 11 },
      },
      series: [
        {
          name: '本月已检（台）',
          type: 'bar',
          stack: 'coverage',
          data: coverage.map((item) => item.inspected),
          barMaxWidth: 14,
          itemStyle: { color: SUCCESS_COLOR },
        },
        {
          name: '未检（台）',
          type: 'bar',
          stack: 'coverage',
          data: coverage.map((item) => item.total - item.inspected),
          barMaxWidth: 14,
          itemStyle: { color: NEUTRAL_COLOR },
        },
      ],
    }),
    [coverage]
  )

  const coverageHeight = Math.max(220, coverage.length * 30 + 70)
  const drillingActive = drilling !== null

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Row gutter={[12, 12]}>
        <Col xs={12} md={6}>
          <StatCard
            icon={<FireOutlined />}
            tone="primary"
            title="器材总数"
            value={stats?.total ?? 0}
            subtitle={`灭火器 ${stats?.extinguisher_count ?? 0} · 消防栓 ${
              stats?.hydrant_count ?? 0
            }`}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            icon={<CheckCircleOutlined />}
            tone="success"
            title="本月已检"
            value={stats?.inspected_this_month ?? 0}
            subtitle={
              stats && stats.total > 0
                ? `覆盖率 ${Math.round(
                    (stats.inspected_this_month / stats.total) * 100
                  )}%`
                : '暂无器材'
            }
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            icon={<ClockCircleOutlined />}
            tone="warning"
            title="本月未检"
            value={stats?.uninspected_this_month ?? 0}
            subtitle="点击筛选未检器材"
            onClick={onFilterUninspected}
          />
        </Col>
        <Col xs={12} md={6}>
          <StatCard
            icon={<WarningOutlined />}
            tone="danger"
            title="有效期异常"
            value={(stats?.expired_count ?? 0) + (stats?.expiring_in_30_count ?? 0)}
            subtitle={`已过期 ${stats?.expired_count ?? 0} · 30天内到期 ${
              stats?.expiring_in_30_count ?? 0
            }`}
            onClick={() => onDrill(drillingActive ? null : 'due_30')}
          />
        </Col>
      </Row>
      <Row gutter={[12, 12]}>
        <Col xs={24} md={8}>
          <Card
            size="small"
            title="有效期到期提醒"
            styles={{ body: { paddingBlock: 10 } }}
            style={{ height: '100%' }}
            extra={
              <Segmented
                size="small"
                value={window}
                options={WINDOWS.map((days) => ({
                  label: `${days}天`,
                  value: days,
                }))}
                onChange={(value) => setWindow(value as number)}
              />
            }
          >
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 28, fontWeight: 600, lineHeight: 1 }}>
                {overdue + within}
              </span>
              <Text type="secondary">台进入提醒窗口</Text>
            </div>
            <Text
              type={overdue > 0 ? 'danger' : 'secondary'}
              style={{ fontSize: 12, display: 'block' }}
            >
              已过期 {overdue} 台 · {window} 天内到期 {within} 台
            </Text>
            <div style={{ marginTop: 8 }}>
              <Button
                size="small"
                type={drillingActive ? 'default' : 'primary'}
                data-drill-button
                onClick={() => onDrill(drillingActive ? null : `due_${window}`)}
              >
                {drillingActive ? '取消筛选' : '筛选明细'}
              </Button>
            </div>
          </Card>
        </Col>
        <Col xs={24} md={16}>
          <Card
            size="small"
            title="近 6 个月点检趋势（台）"
            styles={{ body: { paddingRight: 8 } }}
          >
            <ReactECharts option={trendOption} style={{ height: 200 }} notMerge />
          </Card>
        </Col>
      </Row>
      <Card
        size="small"
        title="各车间本月点检覆盖（台）"
        styles={{ body: { paddingRight: 8 } }}
      >
        {coverage.length === 0 ? (
          <Text type="secondary">暂无器材数据，先同步飞书台账</Text>
        ) : (
          <ReactECharts option={coverageOption} style={{ height: coverageHeight }} notMerge />
        )}
      </Card>
    </div>
  )
}
