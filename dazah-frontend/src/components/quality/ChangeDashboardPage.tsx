'use client'

import Link from 'next/link'
import { Button, Card, Col, Empty, Row, Space, Spin, Statistic } from 'antd'
import { useQuery } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import { fetchChangeDashboardStats } from '@/lib/api/client/quality'


const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  pending_approval: '待批准',
  in_execution: '执行中',
  closed: '已关闭',
}

export function ChangeDashboardPage() {
  const { data: stats, isLoading: loading } = useQuery({
    queryKey: ['quality-stats', 'change'],
    queryFn: fetchChangeDashboardStats,
  })

  const statusChartOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: stats?.statusDistribution.map(s => STATUS_LABELS[s.status] || s.status) || [] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: stats?.statusDistribution.map(s => s.count) || [], itemStyle: { color: '#2563eb' } }],
  }

  const levelChartOption = {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: stats?.levelDistribution.map(l => ({ name: l.level, value: l.count })) || [],
    }],
  }

  const deptChartOption = {
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      data: stats?.departmentDistribution.map(d => ({ name: d.name, value: d.count })) || [],
    }],
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 变更控制</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>变更控制仪表盘</h1>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Link href="/quality/change/ledger"><Button type="primary">进入技术变更台账</Button></Link>
        <Link href="/quality/change/action-plans"><Button>进入变更计划</Button></Link>
      </Space>
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} md={6}><Card><Statistic title="变更总数" value={stats?.total ?? 0} /></Card></Col>
          <Col xs={24} md={6}><Card><Statistic title="变更计划总数" value={stats?.actionPlanTotal ?? 0} /></Card></Col>
          <Col xs={24} md={6}><Card><Statistic title="逾期计划" value={stats?.actionPlanOverdue ?? 0} styles={{ content: { color: '#cf1322' } }} /></Card></Col>
          <Col xs={24} md={6}><Card><Statistic title="已确认提醒" value={stats?.actionPlanConfirmed ?? 0} /></Card></Col>
          <Col xs={24} md={8}>
            <Card title="状态分布">
              {stats?.statusDistribution.length ? (
                <ReactECharts option={statusChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card title="等级分布">
              {stats?.levelDistribution.length ? (
                <ReactECharts option={levelChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
          <Col xs={24} md={8}>
            <Card title="部门分布">
              {stats?.departmentDistribution.length ? (
                <ReactECharts option={deptChartOption} style={{ height: 300 }} />
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
