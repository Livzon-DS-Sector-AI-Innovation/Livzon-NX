'use client'

import {
  CloudOutlined,
  DashboardOutlined,
  FireOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Empty,
  Select,
  Skeleton,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useMemo } from 'react'
import {
  fetchEnergyOverview,
  type EnergyOverview as EnergyOverviewData,
} from '@/lib/api/energy'
import styles from './EnergyOverview.module.css'

const { RangePicker } = DatePicker

type SourceScope = 'detail' | 'daily_summary' | 'energy_summary'

const palette = ['#5645d4', '#2a9d99', '#dd5b00', '#0075de', '#7b3ff2', '#1aae39']

function readScope(value: string | null): SourceScope {
  return value === 'daily_summary' || value === 'energy_summary' ? value : 'detail'
}

function metricLabel(metric: { metric_key?: string | null; energy_type: string }) {
  return metric.metric_key || metric.energy_type
}

function metricVisual(label: string) {
  if (label.includes('电')) return { color: '#5645d4', tint: '#eeeaff', icon: <ThunderboltOutlined /> }
  if (label.includes('蒸汽') || label.includes('锅炉')) return { color: '#dd5b00', tint: '#fff0df', icon: <FireOutlined /> }
  if (label.includes('饮用水')) return { color: '#0075de', tint: '#eaf4ff', icon: <CloudOutlined /> }
  if (label.includes('冰水') || label.includes('冷水')) return { color: '#2a9d99', tint: '#e5f7f5', icon: <CloudOutlined /> }
  if (label.includes('空气')) return { color: '#787671', tint: '#f0eeec', icon: <CloudOutlined /> }
  if (label.includes('循环水')) return { color: '#1aae39', tint: '#e9f8ed', icon: <CloudOutlined /> }
  return { color: '#5645d4', tint: '#eeeaff', icon: <DashboardOutlined /> }
}

function buildTrendOption(data: EnergyOverviewData['trend']): EChartsOption {
  const seriesMap = new Map<string, Map<string, number>>()
  data.forEach((item) => {
    const label = `${metricLabel(item)} · ${item.unit}`
    const points = seriesMap.get(label) ?? new Map<string, number>()
    points.set(item.date, item.value)
    seriesMap.set(label, points)
  })
  const dates = Array.from(new Set(data.map((item) => item.date))).sort()
  return {
    color: palette,
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: 48, right: 20, top: 30, bottom: 56 },
    xAxis: { type: 'category', data: dates, boundaryGap: false },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#ede9e4' } } },
    series: Array.from(seriesMap.entries()).slice(0, 8).map(([name, points]) => ({
      name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: dates.map((date) => points.get(date) ?? null),
      lineStyle: { width: 2 },
    })),
  }
}

function buildDistributionOption(data: EnergyOverviewData['distribution']): EChartsOption {
  const values = [...data]
    .sort((left, right) => right.value - left.value)
    .slice(0, 12)
  return {
    color: ['#5645d4'],
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 88, right: 24, top: 18, bottom: 24 },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#ede9e4' } } },
    yAxis: {
      type: 'category',
      data: values.map((item) => item.key),
      axisLabel: { width: 76, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 22,
        itemStyle: { borderRadius: [0, 5, 5, 0] },
        data: values.map((item) => item.value),
      },
    ],
  }
}

function metricIdentity(metric: { metric_key?: string | null; energy_type: string; unit: string }) {
  return `${metricLabel(metric)}::${metric.energy_type}::${metric.unit}`
}

function formatRange(range: [Dayjs, Dayjs]) {
  return `${range[0].format('YYYY.MM.DD')} – ${range[1].format('YYYY.MM.DD')}`
}

export function EnergyOverview() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const sourceScope = readScope(searchParams.get('source_scope'))
  const workshop = searchParams.get('workshop') || undefined
  const sourceSheetTitle = searchParams.get('source_sheet_title') || undefined
  const energyType = searchParams.get('energy_type') || undefined
  const range = useMemo<[Dayjs, Dayjs]>(() => {
    const start = dayjs(searchParams.get('start_time'))
    const end = dayjs(searchParams.get('end_time'))
    return [
      start.isValid() ? start.startOf('day') : dayjs().startOf('month'),
      end.isValid() ? end.endOf('day') : dayjs().endOf('day'),
    ]
  }, [searchParams])
  const isFactoryOverview = sourceScope === 'detail' && !workshop && !sourceSheetTitle
  const groupBy = sourceScope === 'energy_summary' ? '车间/区域' : '车间'

  const overviewQuery = useQuery({
    queryKey: ['energy-overview', sourceScope, workshop, sourceSheetTitle, energyType, range[0].toISOString(), range[1].toISOString()],
    queryFn: () => fetchEnergyOverview({
      start_time: range[0].toISOString(),
      end_time: range[1].toISOString(),
      energy_type: energyType,
      group_by: groupBy,
      source_scope: sourceScope,
      workshop,
      source_sheet_title: sourceSheetTitle,
    }),
  })
  const dailySummaryQuery = useQuery({
    queryKey: ['energy-daily-summary', range[0].toISOString(), range[1].toISOString()],
    enabled: isFactoryOverview,
    queryFn: () => fetchEnergyOverview({
      start_time: range[0].toISOString(),
      end_time: range[1].toISOString(),
      source_scope: 'daily_summary',
    }),
  })

  const overview = overviewQuery.data
  const hasDailySummary = Boolean(dailySummaryQuery.data?.metrics.length)
  const headline = isFactoryOverview && hasDailySummary ? dailySummaryQuery.data : overview
  const latestRatio = (isFactoryOverview ? dailySummaryQuery.data : headline)?.latest_metrics.find(
    (metric) => metric.unit === '%' || metric.unit === '％' || metricLabel(metric).includes('占比'),
  )
  const headlineMetrics = headline?.metrics ?? []
  const viewLabel = workshop || sourceSheetTitle || '全厂能源总览'
  const loading = overviewQuery.isLoading || (isFactoryOverview && dailySummaryQuery.isLoading)
  const error = overviewQuery.error || (isFactoryOverview ? dailySummaryQuery.error : null)
  const metricOptions = useMemo(
    () => (overview?.metrics ?? []).map((metric) => ({
      label: `${metricLabel(metric)}（${metric.unit}）`,
      value: metricIdentity(metric),
    })),
    [overview?.metrics],
  )
  const requestedMetric = searchParams.get('metric')
  const selectedMetric = requestedMetric && metricOptions.some((option) => option.value === requestedMetric)
    ? requestedMetric
    : metricOptions[0]?.value
  const selectedMetricData = overview?.metrics.find(
    (metric) => metricIdentity(metric) === selectedMetric,
  )
  const selectedTrend = overview?.trend.filter(
    (point) => metricIdentity(point) === selectedMetric,
  ) ?? []
  const selectedDistribution = overview?.distribution.filter(
    (point) => metricIdentity(point) === selectedMetric,
  ) ?? []

  const updateQuery = (values: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams.toString())
    Object.entries(values).forEach(([key, value]) => {
      if (value) next.set(key, value)
      else next.delete(key)
    })
    router.replace(`/energy${next.size ? `?${next.toString()}` : ''}`)
  }

  return (
    <main className={styles.page}>
      <section style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, color: '#1a1a1a', fontSize: 30, letterSpacing: '-0.5px' }}>能源总览</h1>
          <p style={{ margin: '7px 0 0', color: '#787671' }}>
            {isFactoryOverview
              ? '统计已映射能源数据表中的用量、趋势与车间分布，日总量作为全厂统计口径。'
              : `${viewLabel} · ${formatRange(range)}`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <RangePicker
            value={range}
            allowClear={false}
            onChange={(value) => {
              if (!value?.[0] || !value[1]) return
              updateQuery({ start_time: value[0].startOf('day').toISOString(), end_time: value[1].endOf('day').toISOString() })
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => { void overviewQuery.refetch(); if (isFactoryOverview) void dailySummaryQuery.refetch() }} loading={overviewQuery.isFetching || dailySummaryQuery.isFetching}>
            刷新
          </Button>
        </div>
      </section>

      {loading ? (
        <Skeleton active paragraph={{ rows: 12 }} style={{ marginTop: 28 }} />
      ) : error ? (
        <Card style={{ marginTop: 24, borderColor: '#f3c2c2' }}>
          <Empty description={(error as Error).message || '总览读取失败'} />
        </Card>
      ) : !overview?.metrics.length && !headlineMetrics.length ? (
        <Card style={{ marginTop: 24 }}>
          <Empty description={workshop ? `${workshop} 在当前统计周期暂无有效能源数据` : '当前统计周期暂无有效数据。请确认能源页面已发布数据表映射且最新快照包含正数用量。'} />
        </Card>
      ) : (
        <>
          <section style={{ marginTop: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h2 style={{ margin: 0, fontSize: 18 }}>能源分类汇总</h2>
                <Tag color="processing">统计结果</Tag>
              </div>
              <span style={{ color: '#787671', fontSize: 13 }}>
                统计周期 {formatRange(range)} · 最近有效数据 {headline?.last_observed_at ? dayjs(headline.last_observed_at).format('YYYY-MM-DD') : '暂无'}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(196px, 1fr))', gap: 14 }}>
              {headlineMetrics.map((metric) => {
                const label = metricLabel(metric)
                const visual = metricVisual(label)
                return (
                  <div key={metricIdentity(metric)} style={{ border: '1px solid #e5e3df', borderRadius: 12, background: visual.tint, padding: 18, minHeight: 166, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span style={{ color: visual.color, fontSize: 14, fontWeight: 600 }}>{label}</span>
                      <span style={{ color: visual.color, fontSize: 19 }}>{visual.icon}</span>
                    </div>
                    <Statistic value={metric.total_value} precision={2} suffix={metric.unit} valueStyle={{ color: '#1a1a1a', fontSize: 24, fontWeight: 600 }} />
                    <span style={{ color: '#787671', fontSize: 12 }}>{metric.record_count} 条有效数据</span>
                  </div>
                )
              })}
              {latestRatio && (
                <div style={{ border: '1px solid #f3d1ad', borderRadius: 12, background: '#fff7ec', padding: 18, minHeight: 166, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ color: '#793400', fontSize: 14, fontWeight: 600 }}>{metricLabel(latestRatio)}</span>
                    <WarningOutlined style={{ color: '#dd5b00', fontSize: 18 }} />
                  </div>
                  <Statistic value={latestRatio.value} precision={2} suffix={latestRatio.unit} valueStyle={{ color: '#793400', fontSize: 24, fontWeight: 600 }} />
                  <span style={{ color: '#a45a1c', fontSize: 12 }}>最新日 {dayjs(latestRatio.observed_at).format('MM-DD')}，不参与累计</span>
                </div>
              )}
            </div>
          </section>

          {isFactoryOverview && !hasDailySummary && (
            <Alert
              style={{ marginTop: 14 }}
              type="warning"
              showIcon
              message="“日总量”页面尚未发布有效数据表映射"
              description="当前卡片与图表改用各能源分类表统计；发布“日总量”页面映射后，将以全厂日总量作为顶部指标口径。"
            />
          )}

          <section style={{ marginTop: 16 }}>
            <Card
              title="能源用量分析"
              styles={{ body: { paddingTop: 8 } }}
            >
              {metricOptions.length ? (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                  <Select
                    aria-label="选择能源指标"
                    value={selectedMetric}
                    options={metricOptions}
                    style={{ width: 'min(100%, 260px)' }}
                    onChange={(value) => updateQuery({ metric: value })}
                  />
                </div>
              ) : null}
              <div className={styles.analysisGrid}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, margin: '4px 0 8px' }}>
                    <strong>日趋势</strong>
                    <Tag>{selectedTrend.length} 个数据点</Tag>
                  </div>
                  {selectedTrend.length ? <ReactECharts option={buildTrendOption(selectedTrend)} style={{ height: 320 }} opts={{ renderer: 'svg' }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前指标暂无趋势数据" />}
                </div>
                <div>
                  <div style={{ margin: '4px 0 8px' }}>
                    <strong>{sourceScope === 'energy_summary' ? '区域用量排行' : '车间用量排行'}</strong>
                  </div>
                  {selectedDistribution.length ? <ReactECharts option={buildDistributionOption(selectedDistribution)} style={{ height: 320 }} opts={{ renderer: 'svg' }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前指标暂无可排名数据" />}
                </div>
              </div>
            </Card>
          </section>

          <section style={{ marginTop: 16 }}>
            <Card
              title="指标明细"
              extra={overview?.invalid_count ? <Tooltip title="负数、公式错误或未形成有效用量的记录不会纳入统计"><Tag color="orange">{overview.invalid_count} 条异常数据</Tag></Tooltip> : selectedMetricData ? <Tag>{metricLabel(selectedMetricData)}</Tag> : null}
              styles={{ body: { paddingTop: 0 } }}
            >
              <Table
                size="small"
                rowKey={(record) => `${metricLabel(record)}-${record.energy_type}-${record.unit}`}
                pagination={{ pageSize: 10, showSizeChanger: false }}
                scroll={{ x: 720 }}
                dataSource={overview?.metrics ?? []}
                columns={[
                  { title: '指标', key: 'metric', render: (_, record) => metricLabel(record) },
                  { title: '能源类别', dataIndex: 'energy_type', width: 150 },
                  { title: '单位', dataIndex: 'unit', width: 90 },
                  { title: '期间用量', dataIndex: 'total_value', align: 'right', render: (value) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }) },
                  { title: '有效记录', dataIndex: 'record_count', width: 100, align: 'right' },
                ]}
              />
            </Card>
          </section>
        </>
      )}
    </main>
  )
}
