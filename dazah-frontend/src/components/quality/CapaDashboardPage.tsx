'use client'

import Link from 'next/link'
import { Button, Card, Col, Empty, Row, Space, Spin, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { fetchCapaStatistics } from '@/lib/api/client/quality'


export function CapaDashboardPage() {
  const { data: stats, isLoading: loading } = useQuery({
    queryKey: ['quality-stats', 'capa'],
    queryFn: fetchCapaStatistics,
  })

  const statusChartOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: stats?.statusDistribution.map(s => s.status) || [] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: stats?.statusDistribution.map(s => s.count) || [], itemStyle: { color: '#059669' } }],
  }

  const sourceChartOption = {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: stats?.sourceDistribution.map(s => ({ name: s.source, value: s.count })) || [],
    }],
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / CAPA管理</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>CAPA管理仪表盘</h1>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Link href="/quality/capas/ledger"><Button type="primary">进入CAPA台账</Button></Link>
        <Link href="/quality/capas/plans"><Button>进入计划跟踪</Button></Link>
      </Space>
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}><Card><Statistic title="CAPA总数" value={stats?.total ?? 0} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="状态类别数" value={stats?.statusDistribution.length ?? 0} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="来源类别数" value={stats?.sourceDistribution.length ?? 0} /></Card></Col>
          <Col xs={24} md={12}>
            <Card title="状态分布">
              {stats?.statusDistribution.length ? (
                <ReactECharts option={statusChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="来源分布">
              {stats?.sourceDistribution.length ? (
                <ReactECharts option={sourceChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
