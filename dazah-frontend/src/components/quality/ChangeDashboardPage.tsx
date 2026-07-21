'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Col, Empty, Row, Spin } from 'antd'
import {
  AuditOutlined,
  UnorderedListOutlined,
  ScheduleOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  RightOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { fetchChangeDashboardStats } from '@/lib/api/quality'
import type { ChangeDashboardStats } from '@/types/quality'

const navCards = [
  {
    href: '/quality/change/ledger',
    label: '变更台账',
    desc: '变更主台账，支持筛选、导入导出与详情查看',
    icon: <UnorderedListOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-orange-400',
    colorTo: 'to-amber-500',
    shadow: 'shadow-orange-500/20',
  },
  {
    href: '/quality/change/action-plans',
    label: '变更计划',
    desc: '变更计划的列表、创建与跟踪编辑',
    icon: <ScheduleOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-blue-400',
    colorTo: 'to-indigo-500',
    shadow: 'shadow-blue-500/20',
  },
]

const EXECUTING_STATUSES = new Set(['执行中', 'in_execution'])

function buildDonutOption({
  title,
  ratio,
  numerator,
  denominator,
  colors,
}: {
  title: string
  ratio: number
  numerator: number
  denominator: number
  colors: [string, string]
}) {
  return {
    tooltip: { trigger: 'item' },
    color: colors,
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '42%',
        style: {
          text: `${ratio}%`,
          textAlign: 'center',
          fill: '#1f2937',
          fontSize: 28,
          fontWeight: 700,
        },
      },
      {
        type: 'text',
        left: 'center',
        top: '56%',
        style: {
          text: denominator > 0 ? `${numerator}/${denominator}` : '暂无数据',
          textAlign: 'center',
          fill: '#6b7280',
          fontSize: 12,
          fontWeight: 500,
        },
      },
    ],
    series: [
      {
        name: title,
        type: 'pie',
        radius: ['64%', '82%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: { borderWidth: 0 },
        data: [
          { value: numerator, name: title },
          { value: Math.max(denominator - numerator, 0), name: '其余' },
        ],
      },
    ],
  }
}

function buildDepartmentOption(data: ChangeDashboardStats['departmentDistribution']) {
  const sortedData = [...data].sort((a, b) => b.count - a.count)

  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '8%', right: '4%', top: '4%', bottom: '4%', containLabel: true },
    xAxis: {
      type: 'value',
      splitLine: {
        lineStyle: {
          color: '#f3f4f6',
        },
      },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      axisTick: { show: false },
      axisLine: { show: false },
      data: sortedData.map((item) => item.name || '未知'),
      axisLabel: {
        fontSize: 12,
        color: '#4b5563',
      },
    },
    series: [
      {
        name: '变更数量',
        type: 'bar',
        barWidth: '60%',
        itemStyle: {
          color: '#f97316',
          borderRadius: [0, 6, 6, 0],
        },
        label: {
          show: true,
          position: 'right',
          color: '#374151',
          fontWeight: 600,
        },
        data: sortedData.map((item) => item.count),
      },
    ],
  }
}

function buildLevelOption(data: ChangeDashboardStats['levelDistribution']) {
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: '0%', left: 'center' },
    color: ['#f97316', '#fb7185', '#8b5cf6', '#0ea5e9', '#10b981'],
    series: [
      {
        name: '变更等级',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: { show: false, position: 'center' },
        emphasis: {
          label: { show: true, fontSize: 20, fontWeight: 'bold' },
        },
        labelLine: { show: false },
        data: data.map((item) => ({ name: item.level || '未知', value: item.count })),
      },
    ],
  }
}

export function ChangeDashboardPage() {
  const [stats, setStats] = useState<ChangeDashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void fetchChangeDashboardStats()
      .then(setStats)
      .finally(() => setLoading(false))
  }, [])

  const overdueRatio = stats && stats.actionPlanTotal > 0 ? Math.round((stats.actionPlanOverdue / stats.actionPlanTotal) * 100) : 0
  const delayRatio = stats && stats.total > 0 ? Math.round((stats.delayCount / stats.total) * 100) : 0
  const executingCount = (stats?.statusDistribution || []).reduce((sum, item) => {
    return EXECUTING_STATUSES.has(item.status) ? sum + item.count : sum
  }, 0)
  const closedExecutionTotal = (stats?.closedCount ?? 0) + executingCount
  const closedExecutionRatio = closedExecutionTotal > 0 ? Math.round(((stats?.closedCount ?? 0) / closedExecutionTotal) * 100) : 0
  const closedExecutionOption = buildDonutOption({
    title: '已关闭执行总占比',
    ratio: closedExecutionRatio,
    numerator: stats?.closedCount ?? 0,
    denominator: closedExecutionTotal,
    colors: ['#10b981', '#e5e7eb'],
  })
  const delayOption = buildDonutOption({
    title: '延期数环形占比',
    ratio: delayRatio,
    numerator: stats?.delayCount ?? 0,
    denominator: stats?.total ?? 0,
    colors: ['#ef4444', '#fee2e2'],
  })
  const departmentOption = buildDepartmentOption(stats?.departmentDistribution || [])
  const levelOption = buildLevelOption(stats?.levelDistribution || [])

  return (
    <div className="max-w-7xl mx-auto pb-8">
      {/* ── 标题区 ── */}
      <div className="mb-8">
        <div className="flex items-center text-sm text-gray-400 mb-2 tracking-wide">
          <span>质量管理</span>
          <span className="mx-2">/</span>
          <span className="text-gray-600 font-medium">变更控制</span>
        </div>
        <h1 className="text-3xl font-bold text-gray-800 tracking-tight">变更控制仪表盘</h1>
        <p className="text-gray-500 mt-2 text-sm">全局监控质量变更记录、级别分布及关联行动计划，重点关注延期和逾期状态</p>
      </div>

      <Spin spinning={loading} size="large">
        {/* ── 统计卡片区 ── */}
        <Row gutter={[24, 24]} className="mb-8">
          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-orange-50 blur-3xl group-hover:bg-orange-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-orange-400 to-amber-500 text-white shadow-lg shadow-orange-500/30">
                  <AuditOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">变更总数</div>
                  <div className="text-3xl font-bold text-gray-800 tracking-tight">
                    {stats?.total ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-emerald-50 blur-3xl group-hover:bg-emerald-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-emerald-400 to-teal-500 text-white shadow-lg shadow-teal-500/30">
                  <CheckCircleOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">已关闭</div>
                  <div className="text-3xl font-bold text-gray-800 tracking-tight">
                    {stats?.closedCount ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-blue-50 blur-3xl group-hover:bg-blue-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-blue-400 to-indigo-500 text-white shadow-lg shadow-blue-500/30">
                  <ScheduleOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">执行中</div>
                  <div className="text-3xl font-bold text-gray-800 tracking-tight">
                    {executingCount}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className={`absolute -right-6 -bottom-6 w-32 h-32 rounded-full blur-3xl transition-colors duration-500 ${stats && stats.delayCount > 0 ? 'bg-red-50 group-hover:bg-red-100' : 'bg-amber-50 group-hover:bg-amber-100'}`} />
              <div className="relative z-10 flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white shadow-lg ${stats && stats.delayCount > 0 ? 'bg-gradient-to-br from-red-500 to-rose-600 shadow-red-500/30' : 'bg-gradient-to-br from-amber-400 to-orange-500 shadow-orange-500/30'}`}>
                  <ExclamationCircleOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">延期数</div>
                  <div className="flex items-baseline gap-2">
                    <div className="text-3xl font-bold text-gray-800 tracking-tight">
                      {stats?.delayCount ?? 0}
                    </div>
                    {stats && stats.total > 0 && (
                      <div className={`text-xs font-semibold px-2 py-0.5 rounded-full ${stats.delayCount > 0 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                        延期率 {delayRatio}%
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </Col>
        </Row>

        {/* ── 快捷导航区 ── */}
        <div className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 mb-4 tracking-tight flex items-center gap-2">
            <span className="w-1 h-5 bg-orange-500 rounded-full"></span>
            快捷入口
          </h2>
          <Row gutter={[24, 24]}>
            {navCards.map((card) => (
              <Col key={card.href} xs={24} sm={12}>
                <Link href={card.href} className="block group">
                  <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 transition-all duration-300 hover:border-orange-200 hover:shadow-xl hover:shadow-orange-500/5 hover:-translate-y-1">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 pr-4">
                        <div className={`w-12 h-12 rounded-xl mb-4 flex items-center justify-center bg-gradient-to-br ${card.colorFrom} ${card.colorTo} text-white shadow-lg ${card.shadow} group-hover:scale-110 transition-transform duration-300`}>
                          {card.icon}
                        </div>
                        <h3 className="text-lg font-bold text-gray-800 mb-1 group-hover:text-orange-600 transition-colors">
                          {card.label}
                        </h3>
                        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                          {card.desc}
                        </p>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-gray-50 flex items-center justify-center text-gray-400 group-hover:bg-orange-50 group-hover:text-orange-500 transition-colors">
                        <RightOutlined className="text-xs" />
                      </div>
                    </div>
                  </div>
                </Link>
              </Col>
            ))}
          </Row>
        </div>

        <div className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 mb-4 tracking-tight flex items-center gap-2">
            <span className="w-1 h-5 bg-amber-500 rounded-full"></span>
            变更分布分析
          </h2>
          <Row gutter={[24, 24]}>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">变更申请部门分布</h3>
                {stats?.departmentDistribution?.length ? (
                  <ReactECharts option={departmentOption} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">变更等级分类</h3>
                {stats?.levelDistribution?.length ? (
                  <ReactECharts option={levelOption} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
          </Row>
        </div>

        {/* ── 第二排占比图 ── */}
        <div className="mb-4">
          <h2 className="text-lg font-bold text-gray-800 mb-4 tracking-tight flex items-center gap-2">
            <span className="w-1 h-5 bg-indigo-500 rounded-full"></span>
            执行与延期占比
          </h2>
          <Row gutter={[24, 24]}>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-800">已关闭执行总占比</h3>
                    <p className="text-xs text-gray-500 mt-1">口径：已关闭 / (已关闭 + 执行中)</p>
                  </div>
                  <div className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                    {closedExecutionRatio}%
                  </div>
                </div>
                {closedExecutionTotal > 0 ? (
                  <>
                    <ReactECharts option={closedExecutionOption} style={{ height: '280px' }} />
                    <div className="mt-2 flex items-center justify-center text-sm text-gray-600">
                      已关闭 {stats?.closedCount ?? 0} / 已关闭+执行中 {closedExecutionTotal}
                    </div>
                  </>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-800">延期数环形占比</h3>
                    <p className="text-xs text-gray-500 mt-1">口径：延期 / 总数</p>
                  </div>
                  <div className="rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
                    {delayRatio}%
                  </div>
                </div>
                {(stats?.total ?? 0) > 0 ? (
                  <>
                    <ReactECharts option={delayOption} style={{ height: '280px' }} />
                    <div className="mt-2 flex items-center justify-center text-sm text-gray-600">
                      延期 {stats?.delayCount ?? 0} / 总数 {stats?.total ?? 0}
                    </div>
                  </>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
          </Row>
        </div>
      </Spin>
    </div>
  )
}
