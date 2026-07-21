'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Col, Empty, Row, Spin } from 'antd'
import {
  FileTextOutlined,
  SendOutlined,
  TableOutlined,
  AlertOutlined,
  ClockCircleOutlined,
  AuditOutlined,
  RightOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { fetchDeviationStatistics } from '@/lib/api/quality'
import type { DeviationDashboardStats } from '@/types/quality'

const navCards = [
  {
    href: '/quality/deviations/records',
    label: '报告记录',
    desc: '偏差报告阶段视图，左侧记录列表，右侧 AI 分析面板',
    icon: <FileTextOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-blue-500',
    colorTo: 'to-cyan-400',
    shadow: 'shadow-blue-500/20',
  },
  {
    href: '/quality/deviations/investigations',
    label: '调查推送',
    desc: '偏差调查推送的列表、创建与编辑',
    icon: <SendOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-purple-500',
    colorTo: 'to-pink-400',
    shadow: 'shadow-purple-500/20',
  },
  {
    href: '/quality/deviations/ledger',
    label: '偏差台账',
    desc: '偏差主台账，支持筛选、导入导出与详情查看',
    icon: <TableOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-teal-500',
    colorTo: 'to-emerald-400',
    shadow: 'shadow-teal-500/20',
  },
]

const STATUS_MAP: Record<string, string> = {
  draft: '处理中',
  closed: '已关闭',
  pending_ai_analysis: 'AI分析中',
  pending_investigation: '调查中',
  pending_dept_head_review: '部门审核中',
  pending_qa_review: 'QA审核中',
}

export function DeviationDashboardPage() {
  const [stats, setStats] = useState<DeviationDashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void fetchDeviationStatistics()
      .then(setStats)
      .finally(() => setLoading(false))
  }, [])

  const pendingRatio = stats && stats.total > 0 ? Math.round((stats.pending / stats.total) * 100) : 0
  const closedRatio = stats && stats.total > 0 ? Math.round((stats.closedCount / stats.total) * 100) : 0

  // ECharts Options
  const getLevelOption = () => {
    const data = stats?.levelDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: '0%', left: 'center' },
      color: ['#3b82f6', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'],
      series: [
        {
          name: '偏差等级',
          type: 'pie',
          radius: ['40%', '70%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 10,
            borderColor: '#fff',
            borderWidth: 2
          },
          label: { show: false, position: 'center' },
          emphasis: {
            label: { show: true, fontSize: 20, fontWeight: 'bold' }
          },
          labelLine: { show: false },
          data: data.map(d => ({ name: d.level || '未知', value: d.count }))
        }
      ]
    }
  }

  const getRootCauseOption = () => {
    const data = stats?.rootCauseDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      color: ['#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308', '#84cc16'],
      series: [
        {
          name: '根本原因',
          type: 'pie',
          radius: '70%',
          center: ['40%', '50%'],
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          data: data.map(d => ({ name: d.category || '未知', value: d.count }))
        }
      ]
    }
  }

  const getStatusOption = () => {
    const data = stats?.statusDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      color: ['#6366f1', '#14b8a6', '#f59e0b', '#ef4444', '#64748b', '#0ea5e9'],
      series: [
        {
          name: '状态分布',
          type: 'pie',
          radius: '70%',
          center: ['40%', '50%'],
          data: data.map(d => ({ name: STATUS_MAP[d.status] || d.status || '未知', value: d.count })),
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }
          }
        }
      ]
    }
  }

  const getDeptOption = () => {
    const data = stats?.departmentDistribution || []
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
      xAxis: {
        type: 'category',
        data: data.map(d => d.name || '未知'),
        axisTick: { alignWithLabel: true },
        axisLabel: { interval: 0, rotate: 45, fontSize: 11 }
      },
      yAxis: { type: 'value' },
      series: [
        {
          name: '偏差数量',
          type: 'bar',
          barWidth: '60%',
          itemStyle: {
            color: '#3b82f6',
            borderRadius: [4, 4, 0, 0]
          },
          data: data.map(d => d.count)
        }
      ]
    }
  }

  return (
    <div className="max-w-7xl mx-auto pb-8">
      {/* ── 标题区 ── */}
      <div className="mb-8">
        <div className="flex items-center text-sm text-gray-400 mb-2 tracking-wide">
          <span>质量管理</span>
          <span className="mx-2">/</span>
          <span className="text-gray-600 font-medium">偏差管理</span>
        </div>
        <h1 className="text-3xl font-bold text-gray-800 tracking-tight">偏差管理仪表盘</h1>
        <p className="text-gray-500 mt-2 text-sm">全局监控偏差报告、调查进展与台账数据，遵循GMP质量体系指标</p>
      </div>

      <Spin spinning={loading} size="large">
        {/* ── 统计卡片区 ── */}
        <Row gutter={[24, 24]} className="mb-8">
          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-blue-50 blur-3xl group-hover:bg-blue-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/30">
                  <AlertOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">偏差总数</div>
                  <div className="text-3xl font-bold text-gray-800 tracking-tight">
                    {stats?.total ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className={`absolute -right-6 -bottom-6 w-32 h-32 rounded-full blur-3xl transition-colors duration-500 ${stats && stats.pending > 0 ? 'bg-orange-50 group-hover:bg-orange-100' : 'bg-green-50 group-hover:bg-green-100'}`} />
              <div className="relative z-10 flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white shadow-lg ${stats && stats.pending > 0 ? 'bg-gradient-to-br from-orange-400 to-red-500 shadow-orange-500/30' : 'bg-gradient-to-br from-green-400 to-emerald-500 shadow-green-500/30'}`}>
                  <ClockCircleOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">待处理 / 进行中</div>
                  <div className="flex items-baseline gap-2">
                    <div className="text-3xl font-bold text-gray-800 tracking-tight">
                      {stats?.pending ?? 0}
                    </div>
                    {stats && stats.total > 0 && (
                      <div className={`text-xs font-semibold px-2 py-0.5 rounded-full ${stats.pending > 0 ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'}`}>
                        占比 {pendingRatio}%
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-emerald-50 blur-3xl group-hover:bg-emerald-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-lg shadow-emerald-500/30">
                  <FileTextOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">已关闭</div>
                  <div className="flex items-baseline gap-2">
                    <div className="text-3xl font-bold text-gray-800 tracking-tight">
                      {stats?.closedCount ?? 0}
                    </div>
                    {stats && stats.total > 0 && (
                      <div className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                        关闭率 {closedRatio}%
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={6}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-purple-50 blur-3xl group-hover:bg-purple-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-purple-500 to-pink-500 text-white shadow-lg shadow-purple-500/30">
                  <AuditOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">审批环节分布数</div>
                  <div className="text-3xl font-bold text-gray-800 tracking-tight">
                    {stats?.stepBreakdown?.length ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>
        </Row>

        {/* ── 快捷导航区 ── */}
        <div className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 mb-4 tracking-tight flex items-center gap-2">
            <span className="w-1 h-5 bg-blue-500 rounded-full"></span>
            快捷入口
          </h2>
          <Row gutter={[24, 24]}>
            {navCards.map((card) => (
              <Col key={card.href} xs={24} sm={8}>
                <Link href={card.href} className="block group">
                  <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 transition-all duration-300 hover:border-blue-200 hover:shadow-xl hover:shadow-blue-500/5 hover:-translate-y-1">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 pr-4">
                        <div className={`w-12 h-12 rounded-xl mb-4 flex items-center justify-center bg-gradient-to-br ${card.colorFrom} ${card.colorTo} text-white shadow-lg ${card.shadow} group-hover:scale-110 transition-transform duration-300`}>
                          {card.icon}
                        </div>
                        <h3 className="text-lg font-bold text-gray-800 mb-1 group-hover:text-blue-600 transition-colors">
                          {card.label}
                        </h3>
                        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                          {card.desc}
                        </p>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-gray-50 flex items-center justify-center text-gray-400 group-hover:bg-blue-50 group-hover:text-blue-500 transition-colors">
                        <RightOutlined className="text-xs" />
                      </div>
                    </div>
                  </div>
                </Link>
              </Col>
            ))}
          </Row>
        </div>

        {/* ── 分布图表区 ── */}
        <div className="mb-4">
          <h2 className="text-lg font-bold text-gray-800 mb-4 tracking-tight flex items-center gap-2">
            <span className="w-1 h-5 bg-purple-500 rounded-full"></span>
            GMP质量体系分析
          </h2>
          <Row gutter={[24, 24]}>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">偏差等级分布</h3>
                {stats?.levelDistribution?.length ? (
                  <ReactECharts option={getLevelOption()} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">根本原因分类</h3>
                {stats?.rootCauseDistribution?.length ? (
                  <ReactECharts option={getRootCauseOption()} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">状态分布</h3>
                {stats?.statusDistribution?.length ? (
                  <ReactECharts option={getStatusOption()} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">发生部门统计</h3>
                {stats?.departmentDistribution?.length ? (
                  <ReactECharts option={getDeptOption()} style={{ height: '300px' }} />
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
