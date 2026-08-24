'use client'

import { Card, Col, Empty, Row, Typography } from 'antd'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'

export interface RegistrationChartDatum {
  name: string
  value: number
}

export interface RegistrationStackedChartSeries {
  key: string
  label: string
  color: string
}

export interface RegistrationStackedChartDatum {
  name: string
  values: Record<string, number>
}

interface RegistrationChartCardProps {
  title: string
  option: EChartsOption
  hasData: boolean
  height?: number
  subtitle?: string
}

export interface RegistrationMetricItem {
  label: string
  value: string | number
  helper?: string
  accent: string
}

interface RegistrationSummaryHeroProps {
  title: string
  subtitle: string
  metrics: RegistrationMetricItem[]
}

export function RegistrationChartCard({
  title,
  option,
  hasData,
  height = 320,
}: RegistrationChartCardProps) {
  return (
    <Card
      size="small"
      title={
        <div>
          <div style={{ fontWeight: 600 }}>{title}</div>
        </div>
      }
      styles={{ body: { paddingTop: 12 } }}
    >
      {hasData ? (
        <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无统计数据" style={{ padding: '40px 0' }} />
      )}
    </Card>
  )
}

export function RegistrationSummaryHero({
  title,
  metrics,
}: RegistrationSummaryHeroProps) {
  return (
    <Card
      size="small"
      styles={{
        body: {
          padding: 20,
          background:
            'linear-gradient(135deg, rgba(37,99,235,0.08) 0%, rgba(99,102,241,0.08) 50%, rgba(20,184,166,0.08) 100%)',
        },
      }}
    >
      <div style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {title}
        </Typography.Title>
      </div>

      <Row gutter={[12, 12]}>
        {metrics.map((item) => (
          <Col xs={24} sm={12} xl={6} key={item.label}>
            <div
              style={{
                background: '#fff',
                borderRadius: 12,
                padding: '16px 18px',
                border: '1px solid rgba(148,163,184,0.18)',
                boxShadow: '0 8px 24px rgba(15,23,42,0.04)',
                minHeight: 108,
              }}
            >
              <div
                style={{
                  width: 36,
                  height: 4,
                  borderRadius: 999,
                  background: item.accent,
                  marginBottom: 12,
                }}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {item.label}
              </Typography.Text>
              <div
                style={{
                  marginTop: 6,
                  fontSize: 28,
                  lineHeight: 1.1,
                  fontWeight: 700,
                  color: '#0f172a',
                }}
              >
                {item.value}
              </div>
            </div>
          </Col>
        ))}
      </Row>
    </Card>
  )
}

export function buildHorizontalBarOption(
  data: RegistrationChartDatum[],
  color: string,
  seriesName: string
): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const normalized = Array.isArray(params) ? params[0] : params
        const item = normalized as { name?: string; value?: number | string | (number | string)[] }
        const value = Array.isArray(item.value) ? item.value[0] : item.value
        return `${item.name || '-'}<br/>${seriesName}: ${value ?? 0}`
      },
    },
    grid: { left: 140, right: 24, top: 16, bottom: 16 },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'category',
      data: data.map((item) => item.name),
      axisLabel: { width: 120, overflow: 'truncate' },
    },
    series: [
      {
        name: seriesName,
        type: 'bar',
        data: data.map((item) => item.value),
        barWidth: 18,
        itemStyle: {
          color,
          borderRadius: [0, 6, 6, 0],
        },
        label: {
          show: true,
          position: 'right',
          color: '#475569',
        },
      },
    ],
  }
}

export function buildStackedBarOption(
  data: RegistrationStackedChartDatum[],
  series: RegistrationStackedChartSeries[]
): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    legend: {
      bottom: 0,
      itemWidth: 12,
      itemHeight: 12,
    },
    grid: { left: 140, right: 24, top: 16, bottom: 44 },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
    },
    yAxis: {
      type: 'category',
      data: data.map((item) => item.name),
      axisLabel: { width: 120, overflow: 'truncate' },
    },
    series: series.map((item) => ({
      name: item.label,
      type: 'bar',
      stack: 'total',
      barWidth: 18,
      itemStyle: {
        color: item.color,
        borderRadius: item === series[series.length - 1] ? [0, 6, 6, 0] : 0,
      },
      emphasis: { focus: 'series' },
      data: data.map((row) => row.values[item.key] || 0),
    })),
  }
}

export function buildDonutOption(data: RegistrationChartDatum[], colors: string[]): EChartsOption {
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    color: colors,
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['50%', '44%'],
        itemStyle: {
          borderRadius: 8,
          borderColor: '#fff',
          borderWidth: 3,
        },
        label: {
          show: true,
          formatter: '{b}\n{d}%',
        },
        data,
      },
    ],
  }
}
