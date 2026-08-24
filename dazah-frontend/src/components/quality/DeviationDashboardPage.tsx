'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { Button, Card, Col, Empty, Row, Space, Spin, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { fetchDeviationStatistics } from '@/lib/api/client/quality'


const STATUS_LABEL_MAP: Record<string, string> = {
  已关闭: '已关闭',
  进行中: '进行中',
  是: '已关闭',
  否: '进行中',
  closed: '已关闭',
  draft: '草稿',
  pending_ai_analysis: 'AI分析中',
  pending_investigation: '调查中',
  pending_dept_head_review: '部门负责人审核',
  pending_cross_dept_head_review: '跨部门审核',
  pending_qa_review: 'QA审核',
  pending_qa_head_review: 'QA主管审核',
  pending_quality_head_review: '质量负责人审核',
  pending_final_code: '待最终编码',
  returned: '已退回',
  cancelled: '已取消',
  未知: '未知',
}

const LEVEL_LABEL_MAP: Record<string, string> = {
  次要: '次要偏差',
  中等: '中等偏差',
  重大: '严重偏差',
  minor: '次要偏差',
  moderate: '中等偏差',
  major: '严重偏差',
}

function getStatusLabel(status: string): string {
  return STATUS_LABEL_MAP[status] || status
}

function getLevelLabel(level: string): string {
  return LEVEL_LABEL_MAP[level] || level
}

export function DeviationDashboardPage() {
  const { data: stats, isLoading: loading } = useQuery({
    queryKey: ['quality-stats', 'deviation'],
    queryFn: fetchDeviationStatistics,
  })

  const closureRate = useMemo(() => {
    if (!stats || stats.total === 0) return 0
    return Math.round((stats.closedCount / stats.total) * 100)
  }, [stats])

  const statusChartOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: stats?.statusDistribution.map(s => getStatusLabel(s.status)) || [],
        axisLabel: { interval: 0, rotate: 0 },
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'bar',
          data: stats?.statusDistribution.map(s => s.count) || [],
          itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 48,
          label: { show: true, position: 'top' },
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
          data: stats?.departmentDistribution.map(d => ({ name: d.name, value: d.count })) || [],
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
          color: ['#52c41a', '#faad14', '#ff4d4f', '#1677ff', '#722ed1'],
          data:
            stats?.levelDistribution.map(l => ({
              name: getLevelLabel(l.level),
              value: l.count,
            })) || [],
        },
      ],
    }),
    [stats],
  )

  const monthlyTrendOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: stats?.monthlyTrend.map(m => m.month) || [],
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'line',
          smooth: true,
          data: stats?.monthlyTrend.map(m => m.count) || [],
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

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 偏差管理</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>偏差管理仪表盘</h1>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Link href="/quality/deviations/records"><Button type="primary">进入报告记录</Button></Link>
        <Link href="/quality/deviations/investigations"><Button>进入调查推送</Button></Link>
        <Link href="/quality/deviations/ledger"><Button>进入偏差台账</Button></Link>
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
              <Statistic title="待处理" value={stats?.pending ?? 0} styles={{ content: { color: '#faad14' } }} />
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
              <Statistic title="CAPA总数" value={stats?.capaTotal ?? 0} />
            </Card>
          </Col>
          <Col span={24}>
            <Card title="偏差月度趋势（近6个月）">
              {stats?.monthlyTrend.length ? (
                <ReactECharts option={monthlyTrendOption} style={{ height: 300 }} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="状态分布">
              {stats?.statusDistribution.length ? (
                <ReactECharts option={statusChartOption} style={{ height: 300 }} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
              )}
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card title="偏差等级分布">
              {stats?.levelDistribution.length ? (
                <ReactECharts option={levelChartOption} style={{ height: 300 }} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
              )}
            </Card>
          </Col>
          <Col span={24}>
            <Card title="部门分布">
              {stats?.departmentDistribution.length ? (
                <ReactECharts option={deptChartOption} style={{ height: 320 }} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
