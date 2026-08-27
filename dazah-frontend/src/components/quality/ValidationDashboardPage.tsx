'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Card, Col, Empty, Progress, Row, Spin, Statistic } from 'antd'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  ToolOutlined,
  ExperimentOutlined,
  ClearOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { ValidationDashboardStats } from '@/types/quality'

const validationTypeLabelMap: Record<string, string> = {
  equipment_qualification: '设备确认',
  process_validation: '工艺验证',
  cleaning_validation: '清洁验证',
  other_validation: '其他验证',
}

const statusLabelMap: Record<string, string> = {
  '完成': '完成',
  '未完成': '未完成',
  '待完成': '待完成',
  completed: '完成',
  incomplete: '未完成',
  pending: '待完成',
  unknown: '未知',
}

const validationLinks = [
  { href: '/quality/validation/plans', label: '验证主计划', icon: <FileTextOutlined /> },
  { href: '/quality/validation/equipment-qualification', label: '设备确认', icon: <ToolOutlined /> },
  { href: '/quality/validation/process-validation', label: '工艺验证', icon: <ExperimentOutlined /> },
  { href: '/quality/validation/cleaning-validation', label: '清洁验证', icon: <ClearOutlined /> },
  { href: '/quality/validation/other-validations', label: '其他验证', icon: <AppstoreOutlined /> },
]

const chartColors = ['#5b8ff9', '#61ddaa', '#65789b', '#f6bd16', '#7262fd', '#78d3f8', '#9661bc']

export function ValidationDashboardClient({
  initialStats,
}: {
  initialStats: ValidationDashboardStats | null
}) {
  const [stats, setStats] = useState<ValidationDashboardStats | null>(initialStats)
  const [loading, setLoading] = useState(false)

  const total = stats?.total ?? 0
  const completedCount = stats?.statusDistribution
    .filter((s) => s.status === '完成' || s.status === 'completed')
    .reduce((sum, s) => sum + s.count, 0) ?? 0
  const completionRate = total > 0 ? Math.round((completedCount / total) * 100) : 0

  const typeChartOption = {
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number }>) => {
        const item = params[0]
        return `${item.name}<br/>数量：${item.value}`
      },
    },
    xAxis: {
      type: 'category',
      data: stats?.typeDistribution.map((t) => validationTypeLabelMap[t.validation_type] ?? t.validation_type) || [],
      axisLabel: { fontSize: 13, color: '#555' },
    },
    yAxis: { type: 'value', name: '数量', axisLabel: { fontSize: 12 } },
    series: [
      {
        type: 'bar',
        data: stats?.typeDistribution.map((t) => t.count) || [],
        itemStyle: {
          color: {
            type: 'linear' as const,
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#5b8ff9' },
              { offset: 1, color: '#a0c4ff' },
            ],
          },
          borderRadius: [6, 6, 0, 0],
        },
        barWidth: '40%',
        label: { show: true, position: 'top' as const, fontSize: 13, fontWeight: 'bold' },
      },
    ],
    grid: { top: 30, bottom: 10, left: 40, right: 20 },
  }

  const statusChartOption = {
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}<br/>数量：${params.value}（${params.percent}%）`,
    },
    legend: {
      bottom: 5,
      textStyle: { fontSize: 13 },
    },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: {
          show: true,
          formatter: '{b}\n{c}条',
          fontSize: 13,
        },
        data:
          stats?.statusDistribution.map((s, i) => ({
            name: statusLabelMap[s.status] ?? s.status,
            value: s.count,
            itemStyle: { color: chartColors[i % chartColors.length] },
          })) || [],
      },
    ],
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 验证与确认</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>验证与确认仪表盘</h1>
      </div>

      {/* 快捷导航 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {validationLinks.map((item) => (
          <Col key={item.href} xs={12} md={4}>
            <Link href={item.href}>
              <Card
                hoverable
                size="small"
                style={{ textAlign: 'center', borderRadius: 8 }}
                styles={{ body: { padding: '12px 8px' } }}
              >
                <div style={{ fontSize: 22, color: '#5b8ff9', marginBottom: 4 }}>{item.icon}</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{item.label}</div>
              </Card>
            </Link>
          </Col>
        ))}
      </Row>

      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          {/* 核心指标卡片 */}
          <Col xs={24} md={6}>
            <Card style={{ borderRadius: 8 }}>
              <Statistic
                title={<span style={{ fontSize: 14 }}>验证总数</span>}
                value={total}
                prefix={<FileTextOutlined style={{ color: '#5b8ff9' }} />}
                styles={{ content: { fontSize: 28, fontWeight: 700 } }}
              />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card style={{ borderRadius: 8 }}>
              <Statistic
                title={<span style={{ fontSize: 14 }}>已完成</span>}
                value={completedCount}
                prefix={<CheckCircleOutlined style={{ color: '#61ddaa' }} />}
                styles={{ content: { fontSize: 28, fontWeight: 700, color: '#61ddaa' } }}
              />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card style={{ borderRadius: 8 }}>
              <Statistic
                title={<span style={{ fontSize: 14 }}>待完成</span>}
                value={total - completedCount}
                prefix={<ClockCircleOutlined style={{ color: '#f6bd16' }} />}
                styles={{ content: { fontSize: 28, fontWeight: 700, color: '#f6bd16' } }}
              />
            </Card>
          </Col>
          <Col xs={24} md={6}>
            <Card style={{ borderRadius: 8 }}>
              <Statistic
                title={<span style={{ fontSize: 14 }}>近期待再验证</span>}
                value={stats?.revalidationUpcoming ?? 0}
                prefix={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
                styles={{ content: { fontSize: 28, fontWeight: 700, color: '#ff4d4f' } }}
              />
            </Card>
          </Col>

          {/* 完成率进度条 */}
          <Col span={24}>
            <Card title="验证完成率" style={{ borderRadius: 8 }}>
              <Progress
                percent={completionRate}
                status={completionRate >= 80 ? 'success' : completionRate >= 50 ? 'active' : 'exception'}
                strokeColor={completionRate >= 80 ? '#61ddaa' : completionRate >= 50 ? '#5b8ff9' : '#ff4d4f'}
                format={(percent) => `${percent}%`}
                size={['100%', 20]}
              />
              <div style={{ marginTop: 8, color: '#888', fontSize: 13 }}>
                已完成 {completedCount} 条 / 共 {total} 条
              </div>
            </Card>
          </Col>

          {/* 验证类型分布柱状图 */}
          <Col xs={24} md={12}>
            <Card title="验证类型分布" style={{ borderRadius: 8 }}>
              {stats?.typeDistribution.length ? (
                <ReactECharts option={typeChartOption} style={{ height: 300 }} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
              )}
            </Card>
          </Col>

          {/* 状态分布饼图 */}
          <Col xs={24} md={12}>
            <Card title="状态分布" style={{ borderRadius: 8 }}>
              {stats?.statusDistribution.length ? (
                <ReactECharts option={statusChartOption} style={{ height: 300 }} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
              )}
            </Card>
          </Col>

          {/* 执行子表概览 */}
          <Col span={24}>
            <Card title="执行子表概览" style={{ borderRadius: 8 }}>
              {stats?.executionDistribution.length ? (
                <Row gutter={[16, 16]}>
                  {stats.executionDistribution.map((item, idx) => {
                    const label = validationTypeLabelMap[item.validation_type] ?? item.validation_type
                    const percent = total > 0 ? Math.round((item.count / total) * 100) : 0
                    return (
                      <Col key={item.validation_type} xs={24} md={6}>
                        <Card
                          size="small"
                          style={{
                            borderRadius: 8,
                            background: '#fafafa',
                            border: `2px solid ${chartColors[idx % chartColors.length]}33`,
                          }}
                        >
                          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{label}</div>
                          <div style={{ fontSize: 28, fontWeight: 700, color: chartColors[idx % chartColors.length] }}>
                            {item.count}
                            <span style={{ fontSize: 14, color: '#999', marginLeft: 4 }}>条</span>
                          </div>
                          <Progress
                            percent={percent}
                            size="small"
                            strokeColor={chartColors[idx % chartColors.length]}
                            format={(p) => `${p}%`}
                          />
                        </Card>
                      </Col>
                    )
                  })}
                </Row>
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
