'use client'

import { qualityTokens } from '../themeTokens'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ColumnsType } from 'antd/es/table'
import type { EChartsOption, LineSeriesOption } from 'echarts'
import ReactECharts from 'echarts-for-react'
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Modal,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  AlertOutlined,
  ExpandOutlined,
  ReloadOutlined,
  TableOutlined,
} from '@ant-design/icons'

import type {
  QualityInspectionDashboardAlert,
  QualityInspectionDashboardApiResponse,
  QualityInspectionDashboardChart,
} from '@/types/quality-inspection-dashboard'

export const CHART_HEIGHT = 380
export const EXPANDED_CHART_HEIGHT = 620

export function formatMetricValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return Number(value).toFixed(3).replace(/\.?0+$/, '')
}

export function formatSpecLines(
  specLines: QualityInspectionDashboardAlert['spec_lines'] | QualityInspectionDashboardChart['spec_lines']
): string {
  if (!specLines.length) return '-'
  return specLines.map((item) => `${item.label} ${formatMetricValue(item.value)}`).join(' / ')
}

export function buildXAxisLabelFormatter(categories: string[], expanded: boolean) {
  const labelLimit = expanded ? 24 : 12
  if (categories.length <= labelLimit) {
    return (_value: string, index: number) => categories[index] || ''
  }

  const step = Math.max(1, Math.ceil(categories.length / labelLimit))
  const lastIndex = categories.length - 1

  return (_value: string, index: number) => {
    if (index === 0 || index === lastIndex || index % step === 0) {
      return categories[index] || ''
    }
    return ''
  }
}

export function getNotificationTag(alert: QualityInspectionDashboardAlert) {
  if (alert.notification_deduplicated) {
    return <Tag color="blue">已通知（未重复发送）</Tag>
  }
  if (alert.notification_status === 'sent') {
    return <Tag color="green">首次通知成功</Tag>
  }
  if (alert.notification_status === 'partial') {
    return <Tag color="gold">部分通知成功</Tag>
  }
  if (alert.notification_status === 'failed') {
    return <Tag color="red">通知失败</Tag>
  }
  if (alert.notification_status === 'unmapped') {
    return <Tag color="orange">未找到通知对象</Tag>
  }
  if (alert.notification_status === 'missing_open_id') {
    return <Tag color="orange">通知对象缺少联系方式</Tag>
  }
  return <Tag>{alert.notification_status || '未知状态'}</Tag>
}

export function buildTrendOption(chart: QualityInspectionDashboardChart, expanded: boolean): EChartsOption {
  const series: LineSeriesOption[] = [
    {
      name: '实际值',
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      data: chart.actual_series,
      lineStyle: { width: 3, type: 'solid', color: '#52c41a' },
      itemStyle: { color: '#52c41a' },
    },
    {
      name: '平均值',
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: chart.mean_series,
      lineStyle: { width: 2, type: 'solid', color: '#91caff' },
    },
    {
      name: '平均值 + 3σ',
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: chart.upper_sigma_series,
      lineStyle: { width: 2, type: 'solid', color: qualityTokens.warning },
    },
    {
      name: '平均值 - 3σ',
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: chart.lower_sigma_series,
      lineStyle: { width: 2, type: 'solid', color: '#d4a017' },
    },
    ...chart.spec_lines.map<LineSeriesOption>((line) => ({
      name: line.label,
      type: 'line',
      symbol: 'none',
      data: chart.categories.map(() => line.value),
      lineStyle: {
        width: 2,
        type: 'solid',
        color: line.label.includes('OOT上限')
          ? '#722ed1'
          : line.label.includes('OOT下限')
            ? '#ff85c0'
            : line.label.includes('标准下限')
              ? '#eb2f96'
              : '#ff0000',
      },
      itemStyle: {
        color: line.label.includes('OOT上限')
          ? '#722ed1'
          : line.label.includes('OOT下限')
            ? '#ff85c0'
            : line.label.includes('标准下限')
              ? '#eb2f96'
              : '#ff0000',
      },
    })),
  ]

  return {
    tooltip: { trigger: 'axis' },
    legend: {
      top: 4,
      type: 'scroll',
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontSize: expanded ? 12 : 11 },
    },
    grid: {
      left: 44,
      right: 14,
      top: 42,
      bottom: expanded ? 88 : 72,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: chart.categories,
      axisTick: { alignWithLabel: true },
      axisLabel: {
        interval: 0,
        hideOverlap: true,
        rotate: chart.categories.length > (expanded ? 24 : 12) ? 28 : 0,
        margin: 10,
        fontSize: expanded ? 10 : 9,
        color: 'rgba(0, 0, 0, 0.65)',
        formatter: buildXAxisLabelFormatter(chart.categories, expanded),
      },
      axisLine: { lineStyle: { color: '#d9d9d9' } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: expanded ? 11 : 10 },
      splitLine: { lineStyle: { color: qualityTokens.borderLight } },
    },
    series,
  }
}

export interface TrendChartCardProps {
  chart: QualityInspectionDashboardChart
  expanded?: boolean
  onExpand?: (chart: QualityInspectionDashboardChart) => void
}

export function TrendChartCard({ chart, expanded = false, onExpand }: TrendChartCardProps) {
  const chartOption = useMemo(() => buildTrendOption(chart, expanded), [chart, expanded])

  return (
    <Card
      size="small"
      title={<span>{chart.metric_label}</span>}
      extra={
        !expanded ? (
          <Button
            type="text"
            icon={<ExpandOutlined />}
            onClick={() => onExpand?.(chart)}
            aria-label={`放大 ${chart.metric_label}`}
          >
            放大
          </Button>
        ) : null
      }
      styles={{ body: { padding: expanded ? 14 : 12 } }}
    >
      <Space orientation="vertical" size={8} style={{ width: '100%' }}>
        {chart.categories.length === 0 ? (
          <Empty description="暂无趋势数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <ReactECharts
            option={chartOption}
            style={{ height: expanded ? EXPANDED_CHART_HEIGHT : CHART_HEIGHT }}
            notMerge
            lazyUpdate
          />
        )}
      </Space>
    </Card>
  )
}

export interface BaseTrendDashboardProps {
  defaultTitle: string
  fetchDashboard: (entityCode?: string) => Promise<QualityInspectionDashboardApiResponse>
  entityCode?: string
  isSupportedEntity?: boolean
  unsupportedMessage?: string
  chartColumnSpan?: number
  /** 指定后按“每行 N 图”横向滚动布局，优先于 chartColumnSpan */
  chartCountPerRow?: number
  descriptionText?: string
  defaultSourceLabel?: string
}

export function BaseTrendDashboard({
  defaultTitle,
  fetchDashboard,
  entityCode,
  isSupportedEntity = true,
  unsupportedMessage,
  chartColumnSpan = 6,
  chartCountPerRow,
  descriptionText,
}: BaseTrendDashboardProps) {
  const { data: response, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['quality-inspection', 'dashboard', entityCode],
    queryFn: () => fetchDashboard(entityCode),
    enabled: isSupportedEntity,
  })
  const [activeChart, setActiveChart] = useState<QualityInspectionDashboardChart | null>(null)
  const [alertsOpen, setAlertsOpen] = useState(false)

  const errorMessage = error instanceof Error ? error.message : '加载趋势仪表盘失败'

  const dashboard = response?.data ?? null
  const configured = response?.meta.configured !== false
  const alerts = dashboard?.alerts ?? []
  const title = dashboard?.source_label ? `${dashboard.source_label}趋势仪表盘` : defaultTitle

  const alertColumns = useMemo<ColumnsType<QualityInspectionDashboardAlert>>(
    () => [
      { title: '批号', dataIndex: 'batch_no', key: 'batch_no', width: 140 },
      { title: '指标', dataIndex: 'metric_label', key: 'metric_label', width: 220 },
      {
        title: '实际值',
        dataIndex: 'actual_value',
        key: 'actual_value',
        width: 100,
        render: (value: number) => formatMetricValue(value),
      },
      {
        title: '平均值',
        dataIndex: 'mean',
        key: 'mean',
        width: 100,
        render: (value: number | null) => formatMetricValue(value),
      },
      {
        title: '平均值 + 3σ',
        dataIndex: 'upper_control_limit',
        key: 'upper_control_limit',
        width: 120,
        render: (value: number | null) => formatMetricValue(value),
      },
      {
        title: '平均值 - 3σ',
        dataIndex: 'lower_control_limit',
        key: 'lower_control_limit',
        width: 120,
        render: (value: number | null) => formatMetricValue(value),
      },
      {
        title: '标准线',
        dataIndex: 'spec_lines',
        key: 'spec_lines',
        width: 220,
        render: (value: QualityInspectionDashboardAlert['spec_lines']) => formatSpecLines(value),
      },
      {
        title: '通知状态',
        key: 'notification_status',
        width: 180,
        render: (_, record) => getNotificationTag(record),
      },
      {
        title: '通知对象',
        key: 'recipient_name',
        width: 140,
        render: (_, record) => record.recipient_name || '-',
      },
      {
        title: '通知时间',
        dataIndex: 'notified_at',
        key: 'notified_at',
        width: 180,
        render: (value: string | null) => value || '-',
      },
    ],
    []
  )

  if (!isSupportedEntity) {
    return (
      <Card title={defaultTitle}>
        <Alert
          type="info"
          showIcon
          title="当前子表未配置趋势仪表盘"
          description={unsupportedMessage}
        />
      </Card>
    )
  }

  if (loading) {
    return (
      <Card title={title}>
        <div style={{ padding: 48, textAlign: 'center' }}>
          <Spin size="large" />
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        title={title}
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void refetch()}>
            重试
          </Button>
        }
      >
        <Alert title="加载失败" description={errorMessage} type="error" showIcon />
      </Card>
    )
  }

  if (!configured) {
    return (
      <Card
        title={title}
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void refetch()}>
            刷新
          </Button>
        }
      >
        <Alert
          type="warning"
          showIcon
          title="飞书数据源未配置"
          description={`当前无法加载${defaultTitle}，请先检查后端飞书配置。`}
        />
      </Card>
    )
  }

  return (
    <>
      <Card
        title={title}
        extra={
          <Space>
            <Button
              icon={<TableOutlined />}
              onClick={() => setAlertsOpen(true)}
              disabled={alerts.length === 0}
            >
              查看异常明细
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => void refetch()}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type={alerts.length > 0 ? 'warning' : 'success'}
            showIcon
            icon={<AlertOutlined />}
            title={alerts.length > 0 ? '发现趋势异常批次' : '当前未发现趋势异常'}
            description={
              <Space size={[8, 8]} wrap>
                <Tag color="blue">批次数 {dashboard?.summary.alert_batch_count ?? 0}</Tag>
                <Tag color="purple">异常指标数 {dashboard?.summary.alert_metric_count ?? 0}</Tag>
                <Tag color="green">首次通知成功 {dashboard?.summary.first_notification_sent_count ?? 0}</Tag>
                <Tag color="gold">已通知未重复发送 {dashboard?.summary.deduplicated_notification_count ?? 0}</Tag>
                <Tag color="red">通知失败 {dashboard?.summary.failed_notification_count ?? 0}</Tag>
                <Tag color="orange">未找到通知对象 {dashboard?.summary.unmapped_notification_count ?? 0}</Tag>
                <Tag>忽略异常值 {dashboard?.summary.skipped_value_count ?? 0}</Tag>
              </Space>
            }
            action={
              <Button type="link" onClick={() => setAlertsOpen(true)} disabled={alerts.length === 0}>
                查看异常明细
              </Button>
            }
          />

          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="总记录数" value={dashboard?.summary.total_records ?? 0} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="有效记录数" value={dashboard?.summary.valid_record_count ?? 0} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="异常批次数" value={dashboard?.summary.alert_batch_count ?? 0} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="异常指标数" value={dashboard?.summary.alert_metric_count ?? 0} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="首次通知成功" value={dashboard?.summary.first_notification_sent_count ?? 0} />
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <Statistic title="去重未重发" value={dashboard?.summary.deduplicated_notification_count ?? 0} />
            </Col>
          </Row>

          {dashboard && dashboard.charts.length > 0 ? (
            chartCountPerRow ? (
              <div style={{ overflowX: 'auto' }}>
                <Row gutter={[16, 16]} wrap={false} style={{ minWidth: chartCountPerRow * 320 }}>
                  {dashboard.charts.map((chart) => (
                    <Col
                      key={chart.metric_key}
                      flex={`0 0 calc((100% - ${(chartCountPerRow - 1) * 16}px) / ${chartCountPerRow})`}
                    >
                      <TrendChartCard chart={chart} onExpand={setActiveChart} />
                    </Col>
                  ))}
                </Row>
              </div>
            ) : (
              <Row gutter={[16, 16]}>
                {dashboard.charts.map((chart) => (
                  <Col key={chart.metric_key} xs={24} xl={chartColumnSpan}>
                    <TrendChartCard chart={chart} onExpand={setActiveChart} />
                  </Col>
                ))}
              </Row>
            )
          ) : (
            <Empty description="暂无可展示的趋势数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}

          {descriptionText ? (
            <Typography.Text type="secondary">{descriptionText}</Typography.Text>
          ) : null}
        </Space>
      </Card>

      <Modal
        title={activeChart?.metric_label || '趋势图放大'}
        open={!!activeChart}
        onCancel={() => setActiveChart(null)}
        footer={null}
        width={1200}
        destroyOnHidden
      >
        {activeChart ? <TrendChartCard chart={activeChart} expanded /> : null}
      </Modal>

      <Modal
        title="异常明细"
        open={alertsOpen}
        onCancel={() => setAlertsOpen(false)}
        footer={null}
        width={1400}
        destroyOnHidden
      >
        {alerts.length > 0 ? (
          <Table<QualityInspectionDashboardAlert>
            rowKey={(record) => `${record.batch_no}-${record.metric_key}`}
            columns={alertColumns}
            dataSource={alerts}
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            scroll={{ x: 1400 }}
          />
        ) : (
          <Empty description="暂无异常明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Modal>
    </>
  )
}
