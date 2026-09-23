'use client'

import { qualityTokens } from './themeTokens'
import { useMemo } from 'react'
import Link from 'next/link'
import { Button, Card, Col, Empty, Row, Space, Spin, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { fetchDeviationStatistics } from '@/lib/api/client/quality'

const LEVEL_LABEL_MAP: Record<string, string> = {
  minor: '次要偏差',
  moderate: '中等偏差',
  major: '严重偏差',
  未定级: '未定级',
}

// 根本原因归类（人机料法环），与 CAPA 原因类别同一口径
const CAUSE_LABEL_MAP: Record<string, string> = {
  人员: '人员（人）',
  '设施/设备': '设施/设备（机）',
  '产品/物料': '产品/物料（料）',
  文件: '文件（法）',
  环境: '环境（环）',
  其它: '其它',
}

function getLevelLabel(level: string): string {
  return LEVEL_LABEL_MAP[level] || level
}

function getCauseLabel(category: string): string {
  return CAUSE_LABEL_MAP[category] || category
}

export function DeviationDashboardPage() {
  const { data: stats, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['quality-stats', 'deviation'],
    queryFn: fetchDeviationStatistics,
  })

  const closureRate = useMemo(() => {
    if (!stats || stats.total === 0) return 0
    return Math.round((stats.closedCount / stats.total) * 100)
  }, [stats])

  const monthlyTrendOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: stats?.monthlyTrend.map((m) => m.month) || [],
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'line',
          smooth: true,
          data: stats?.monthlyTrend.map((m) => m.count) || [],
          itemStyle: { color: '#2563eb' },
          lineStyle: { width: 3 },
          symbolSize: 8,
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(37, 99, 235, 0.25)' },
                { offset: 1, color: 'rgba(37, 99, 235, 0.02)' },
              ],
            },
          },
          label: { show: true, position: 'top' },
        },
      ],
    }),
    [stats],
  )

  const causeChartOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: stats?.rootCauseDistribution.map((item) => getCauseLabel(item.name)) || [],
        axisLabel: { interval: 0, rotate: 0 },
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'bar',
          data: stats?.rootCauseDistribution.map((item) => item.count) || [],
          itemStyle: { color: qualityTokens.primary, borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 48,
          label: { show: true, position: 'top' },
        },
      ],
    }),
    [stats],
  )

  const levelChartOption = useMemo(
    () => ({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle' },
      series: [
        {
          type: 'pie',
          radius: ['45%', '72%'],
          center: ['40%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{b}\n{d}%' },
          color: ['#52c41a', '#faad14', '#ff4d4f', '#8c8c8c'],
          data:
            stats?.levelDistribution.map((item) => ({
              name: getLevelLabel(item.name),
              value: item.count,
            })) || [],
        },
      ],
    }),
    [stats],
  )

  const deptChartOption = useMemo(
    () => ({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['40%', '50%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, formatter: '{b}\n{d}%' },
          data:
            stats?.departmentDistribution.map((item) => ({
              name: item.name,
              value: item.count,
            })) || [],
        },
      ],
    }),
    [stats],
  )

  const renderChart = (dataLength: number | undefined, option: object, height = 300) => {
    if (error) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="统计数据加载失败"
        >
          <Button onClick={() => refetch()}>重试</Button>
        </Empty>
      )
    }
    if (!dataLength) {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
    }
    return <ReactECharts option={option} style={{ height }} />
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>偏差管理仪表盘</h1>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Link href="/quality/deviations/ledger"><Button type="primary">进入偏差台账</Button></Link>
        <Link href="/quality/deviations/records"><Button>进入报告记录</Button></Link>
        <Link href="/quality/deviations/investigations"><Button>进入调查推送</Button></Link>
      </Space>
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}>
            <Card>
              <Statistic title="偏差总数" value={stats?.total ?? 0} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic title="已关闭" value={stats?.closedCount ?? 0} styles={{ content: { color: '#52c41a' } }} />
              <div style={{ marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>关闭率 {closureRate}%</div>
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic title="严重偏差" value={stats?.majorCount ?? 0} styles={{ content: { color: '#ff4d4f' } }} />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="未关闭"
                value={(stats?.total ?? 0) - (stats?.closedCount ?? 0)}
                styles={{ content: { color: '#faad14' } }}
              />
            </Card>
          </Col>
          <Col span={24}>
            <Card title="偏差月度趋势（近6个月）">
              {renderChart(stats?.monthlyTrend.length, monthlyTrendOption)}
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="根本原因归类分析（人机料法环）">
              {renderChart(stats?.rootCauseDistribution.length, causeChartOption)}
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="发生部门分布">
              {renderChart(stats?.departmentDistribution.length, deptChartOption)}
            </Card>
          </Col>
          <Col span={24}>
            <Card title="偏差等级分布">
              {renderChart(stats?.levelDistribution.length, levelChartOption)}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
