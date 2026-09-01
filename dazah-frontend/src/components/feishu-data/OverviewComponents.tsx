'use client'

import type { ReactNode } from 'react'
import { Alert, Card, Col, Empty, Row, Space, Statistic, Tag, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'

export function OverviewPageShell({
  title,
  description,
  filters,
  children,
}: {
  title: string
  description?: string
  filters?: ReactNode
  children: ReactNode
}) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row align="middle" justify="space-between" gutter={[16, 12]}>
        <Col>
          <Typography.Title level={3} style={{ margin: 0 }}>{title}</Typography.Title>
          {description ? <Typography.Text type="secondary">{description}</Typography.Text> : null}
        </Col>
        <Col>{filters}</Col>
      </Row>
      {children}
    </Space>
  )
}

export function MetricCard({
  title,
  value,
  unit,
  trend,
}: {
  title: string
  value: number | string
  unit?: string
  trend?: { value: number; label: string }
}) {
  const improving = (trend?.value || 0) >= 0
  return (
    <Card size="small">
      <Statistic title={title} value={value} suffix={unit} />
      {trend ? <Tag color={improving ? 'green' : 'red'}>{trend.label} {trend.value > 0 ? '+' : ''}{trend.value}%</Tag> : null}
    </Card>
  )
}

function ChartCard({ title, option, emptyText }: { title: string; option?: EChartsOption; emptyText: string }) {
  return (
    <Card title={title} size="small">
      {option ? <ReactECharts option={option} style={{ height: 320 }} opts={{ renderer: 'svg' }} /> : <Empty description={emptyText} />}
    </Card>
  )
}

export function TrendChart(props: { title: string; option?: EChartsOption }) {
  return <ChartCard {...props} emptyText="当前范围暂无趋势数据" />
}

export function DistributionChart(props: { title: string; option?: EChartsOption }) {
  return <ChartCard {...props} emptyText="当前范围暂无分布数据" />
}

export function RankingChart(props: { title: string; option?: EChartsOption }) {
  return <ChartCard {...props} emptyText="当前范围暂无排名数据" />
}

export function DataQualityCard({ issues, sampleSize }: { issues: string[]; sampleSize: number }) {
  return (
    <Card title="数据质量" size="small">
      <Statistic title="有效样本" value={sampleSize} />
      {issues.length ? <Alert type="warning" showIcon title="分析前需要关注" description={issues.join('；')} /> : <Alert type="success" showIcon title="未发现阻断分析的数据质量问题" />}
    </Card>
  )
}

export function AnalysisPanel({ facts, algorithm, ai }: { facts: ReactNode; algorithm: ReactNode; ai?: ReactNode }) {
  return (
    <Card title="分析结论" size="small">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Alert type="info" title="已验证事实" description={facts} />
        <Alert type="warning" title="算法检测结果" description={algorithm} />
        <Alert type="success" title="AI 辅助推断" description={ai || '尚未生成 AI 解释'} />
      </Space>
    </Card>
  )
}
