'use client'

import { qualityTokens } from './themeTokens'
import { useMemo, useState } from 'react'
import Link from 'next/link'
import {
  Alert,
  Card,
  Col,
  Empty,
  InputNumber,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  ToolOutlined,
  ExperimentOutlined,
  ClearOutlined,
  AppstoreOutlined,
  FileDoneOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import {
  fetchFeishuValidationDashboardStats,
  fetchFeishuValidationUpcoming,
} from '@/lib/api/client/quality'
import type {
  ValidationDashboardStats,
  ValidationUpcomingItem,
} from '@/types/quality'

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

/** 与后端"近期待再验证"排除口径保持一致的任务状态集合 */
const COMPLETED_STATUSES = new Set([
  '完成',
  '已完成',
  'completed',
  'finished',
  'done',
])

function isCompletedStatus(status: string): boolean {
  return COMPLETED_STATUSES.has(status.trim().toLowerCase())
}

const validationLinks = [
  { href: '/quality/validation/plans', label: '验证主计划', icon: <FileTextOutlined /> },
  { href: '/quality/validation/equipment-qualification', label: '设备确认', icon: <ToolOutlined /> },
  { href: '/quality/validation/process-validation', label: '工艺验证', icon: <ExperimentOutlined /> },
  { href: '/quality/validation/cleaning-validation', label: '清洁验证', icon: <ClearOutlined /> },
  { href: '/quality/validation/other-validations', label: '其他验证', icon: <AppstoreOutlined /> },
  { href: '/quality/validation/qc-validation', label: 'QC验证', icon: <FileDoneOutlined /> },
]

const chartColors = ['#5b8ff9', '#61ddaa', '#65789b', '#f6bd16', '#7262fd', '#78d3f8', '#9661bc']

const UPCOMING_DAYS_OPTIONS = [
  { value: 30, label: '30天' },
  { value: 60, label: '60天' },
  { value: 90, label: '90天' },
  { value: 180, label: '180天' },
]

/** 仪表盘默认统计今年 */
const DEFAULT_YEAR_FROM = new Date().getFullYear()

/** 飞书"验证到期时间"为文本列（如 2026.02），展示时统一为连字符日期 */
function formatDueDate(value: string | null): string {
  if (!value) return '—'
  return value.replace(/\./g, '-')
}

export function ValidationDashboardClient({
  initialStats,
}: {
  initialStats: ValidationDashboardStats | null
}) {
  const [days, setDays] = useState(30)
  const [yearFrom, setYearFrom] = useState(DEFAULT_YEAR_FROM)
  const [upcomingOpen, setUpcomingOpen] = useState(false)
  const [upcomingPage, setUpcomingPage] = useState(1)

  const { data: stats, isFetching: statsLoading, isError: statsError } = useQuery({
    queryKey: ['quality-validation', 'dashboard', days, yearFrom],
    queryFn: () => fetchFeishuValidationDashboardStats(days, yearFrom),
    placeholderData: keepPreviousData,
    ...(initialStats && days === 30 && yearFrom === DEFAULT_YEAR_FROM
      ? { initialData: initialStats }
      : {}),
  })

  const upcomingQuery = useQuery({
    queryKey: ['quality-validation', 'upcoming', days, yearFrom, upcomingPage],
    queryFn: () =>
      fetchFeishuValidationUpcoming(days, yearFrom, {
        page: upcomingPage,
        page_size: 10,
      }),
    enabled: upcomingOpen,
    placeholderData: keepPreviousData,
  })

  const total = stats?.total ?? 0
  const completedCount =
    stats?.statusDistribution
      .filter((s) => isCompletedStatus(s.status))
      .reduce((sum, s) => sum + s.count, 0) ?? 0
  const completionRate = total > 0 ? Math.round((completedCount / total) * 100) : 0

  const upcomingColumns: ColumnsType<ValidationUpcomingItem> = useMemo(
    () => [
      {
        title: '验证名称',
        dataIndex: 'title',
        key: 'title',
        ellipsis: true,
        width: 260,
      },
      {
        title: '类型',
        dataIndex: 'validation_type',
        key: 'validation_type',
        width: 110,
        render: (v: string) => validationTypeLabelMap[v] ?? v,
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (v: string) => (v ? (statusLabelMap[v] ?? v) : '未知'),
      },
      {
        title: '到期时间',
        dataIndex: 'planned_end_date',
        key: 'planned_end_date',
        width: 120,
        render: (v: string | null) => formatDueDate(v),
      },
      {
        title: '部门',
        dataIndex: 'department',
        key: 'department',
        width: 130,
        ellipsis: true,
        render: (v: string | null) => v || '—',
      },
      {
        title: '方案名称',
        dataIndex: 'plan_name',
        key: 'plan_name',
        ellipsis: true,
        render: (v: string | null) => v || '—',
      },
    ],
    [],
  )

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
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 验证与确认</p>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>验证与确认仪表盘</h1>
        </div>
        <Space wrap>
          <span style={{ color: '#666', fontSize: 13 }}>起始年份</span>
          <InputNumber
            value={yearFrom}
            min={2000}
            max={2100}
            style={{ width: 110 }}
            onChange={(v) => setYearFrom(v ?? DEFAULT_YEAR_FROM)}
          />
          <span style={{ color: '#666', fontSize: 13 }}>近期待再验证窗口</span>
          <Select
            value={days}
            onChange={setDays}
            options={UPCOMING_DAYS_OPTIONS}
            style={{ width: 96 }}
            aria-label="近期待再验证窗口"
          />
        </Space>
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

      <Spin spinning={statsLoading}>
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
            <Card
              hoverable
              style={{ borderRadius: 8, cursor: 'pointer' }}
              onClick={() => setUpcomingOpen(true)}
            >
              <Statistic
                title={<span style={{ fontSize: 14 }}>近期待再验证</span>}
                value={stats?.revalidationUpcoming ?? 0}
                prefix={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
                styles={{ content: { fontSize: 28, fontWeight: 700, color: '#ff4d4f' } }}
              />
            </Card>
          </Col>

          {statsError && (
            <Col span={24}>
              <Alert
                type="error"
                showIcon
                title="统计数据加载失败，请稍后重试"
                style={{ borderRadius: 8 }}
              />
            </Col>
          )}

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
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无数据，请确认已在同步设置中绑定验证主计划年度飞书表"
                />
              )}
            </Card>
          </Col>

          {/* 状态分布饼图 */}
          <Col xs={24} md={12}>
            <Card title="状态分布" style={{ borderRadius: 8 }}>
              {stats?.statusDistribution.length ? (
                <ReactECharts option={statusChartOption} style={{ height: 300 }} />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无数据，请确认已在同步设置中绑定验证主计划年度飞书表"
                />
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
                            background: qualityTokens.bgSoft,
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
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无数据，请确认已在同步设置中绑定验证主计划年度飞书表"
                />
              )}
            </Card>
          </Col>
        </Row>
      </Spin>

      {/* 近期待再验证明细弹窗 */}
      <Modal
        title={`近期待再验证（未来 ${days} 天内，${yearFrom} 年起）`}
        open={upcomingOpen}
        onCancel={() => setUpcomingOpen(false)}
        footer={null}
        width={880}
      >
        <p style={{ color: '#888', fontSize: 13, marginBottom: 12 }}>
          仅展示验证主计划各年度台账中「未完成且到期时间不超过 {days} 天」的验证项。
        </p>
        {upcomingQuery.isError && (
          <Alert
            type="error"
            showIcon
            title="明细加载失败，请稍后重试"
            style={{ marginBottom: 12, borderRadius: 8 }}
          />
        )}
        <Table
          rowKey="record_id"
          columns={upcomingColumns}
          dataSource={upcomingQuery.data?.items ?? []}
          loading={upcomingQuery.isFetching}
          size="small"
          tableLayout="fixed"
          pagination={{
            current: upcomingPage,
            pageSize: 10,
            total: upcomingQuery.data?.total ?? 0,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p) => setUpcomingPage(p),
          }}
        />
      </Modal>
    </div>
  )
}
