'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { Alert, Button, Card, Col, Empty, Row, Space, Spin, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { fetchCapaStatistics } from '@/lib/api/client/quality'

// CAPA 台账已本地化：仪表盘与台账列表同源（本地台账），维度对齐台账列。
// 效果评估取台账原文（有效/无效/进行中），空值由后端归为「未填」。

function renderChart(hasData: boolean, option: unknown, retry: () => void, error: unknown, loading: boolean) {
  if (error) {
    return (
      <Space orientation="vertical" style={{ width: '100%' }} align="center">
        <Alert type="error" showIcon title="统计数据加载失败" />
        <Button onClick={() => void retry()} loading={loading}>
          重试
        </Button>
      </Space>
    )
  }
  if (!hasData) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
  }
  return <ReactECharts option={option} style={{ height: 300 }} />
}

export function CapaDashboardPage() {
  const { data: stats, isLoading: loading, error, refetch } = useQuery({
    queryKey: ['quality-stats', 'capa'],
    queryFn: fetchCapaStatistics,
  })

  const closureRate = useMemo(() => {
    if (!stats || stats.total === 0) return 0
    return Math.round((stats.closedCount / stats.total) * 100)
  }, [stats])

  const resultChartOption = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: stats?.resultDistribution.map(s => s.name) || [] },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'bar',
      barMaxWidth: 48,
      data: stats?.resultDistribution.map(s => s.count) || [],
      itemStyle: { color: '#059669' },
    }],
  }), [stats])

  const departmentChartOption = useMemo(() => ({
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: stats?.departmentDistribution.map(s => ({ name: s.name, value: s.count })) || [],
    }],
  }), [stats])

  const monthlyTrendOption = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: stats?.monthlyTrend.map(m => m.month) || [] },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'line',
      smooth: true,
      data: stats?.monthlyTrend.map(m => m.count) || [],
      itemStyle: { color: '#059669' },
      areaStyle: { opacity: 0.12 },
    }],
  }), [stats])

  const retry = () => refetch()

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>CAPA管理仪表盘</h1>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Link href="/quality/capas/ledger"><Button type="primary">进入CAPA台账</Button></Link>
        <Link href="/quality/capas/plans"><Button>进入计划跟踪</Button></Link>
      </Space>
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}><Card><Statistic title="CAPA总数" value={stats?.total ?? 0} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="进行中" value={stats?.inProgressCount ?? 0} /></Card></Col>
          <Col xs={24} md={8}>
            <Card>
              <Statistic
                title={`已关闭（关闭率 ${closureRate}%）`}
                value={stats?.closedCount ?? 0}
              />
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="CAPA效果评估分布">
              {renderChart(!!stats?.resultDistribution.length, resultChartOption, retry, error, loading)}
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="事件部门分布">
              {renderChart(!!stats?.departmentDistribution.length, departmentChartOption, retry, error, loading)}
            </Card>
          </Col>
          <Col xs={24}>
            <Card title="近 6 个月启动趋势">
              {renderChart(!!stats?.monthlyTrend.length, monthlyTrendOption, retry, error, loading)}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}