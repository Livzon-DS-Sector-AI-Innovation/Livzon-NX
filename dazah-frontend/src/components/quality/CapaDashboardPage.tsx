'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Col, Empty, Row, Spin } from 'antd'
import {
  SafetyCertificateOutlined,
  UnorderedListOutlined,
  ScheduleOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  RightOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { fetchCapaStatistics } from '@/lib/api/quality'
import type { CapaDashboardStats } from '@/types/quality'

const navCards = [
  {
    href: '/quality/capas/ledger',
    label: 'CAPA台账',
    desc: 'CAPA 主台账，支持筛选、导入导出与详情查看',
    icon: <UnorderedListOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-emerald-400',
    colorTo: 'to-teal-500',
    shadow: 'shadow-teal-500/20',
  },
  {
    href: '/quality/capas/plans',
    label: '计划跟踪',
    desc: 'CAPA 子计划的列表、创建与跟踪编辑',
    icon: <ScheduleOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-blue-400',
    colorTo: 'to-indigo-500',
    shadow: 'shadow-blue-500/20',
  },
]

const STATUS_MAP: Record<string, string> = {
  draft: '进行中',
  closed: '已关闭',
  cancelled: '已取消',
}

export function CapaDashboardPage() {
  const [stats, setStats] = useState<CapaDashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void fetchCapaStatistics()
      .then(setStats)
      .finally(() => setLoading(false))
  }, [])

  const overdueRatio = stats && stats.total > 0 ? Math.round((stats.overdueCount / stats.total) * 100) : 0
  const closedRatio = stats && stats.total > 0 ? Math.round((stats.closedCount / stats.total) * 100) : 0

  // ECharts Options
  const getStatusOption = () => {
    const data = stats?.statusDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { bottom: '0%', left: 'center' },
      color: ['#6366f1', '#14b8a6', '#f59e0b', '#ef4444', '#64748b', '#0ea5e9'],
      series: [
        {
          name: '状态分布',
          type: 'pie',
          radius: ['40%', '70%'],
          itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
          label: { show: false, position: 'center' },
          emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
          data: data.map(d => ({ name: STATUS_MAP[d.status] || d.status || '未知', value: d.count }))
        }
      ]
    }
  }

  const getSourceOption = () => {
    const data = stats?.sourceDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      color: ['#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308', '#84cc16'],
      series: [
        {
          name: '来源分布',
          type: 'pie',
          radius: '70%',
          center: ['40%', '50%'],
          data: data.map(d => ({ name: d.source || '未知', value: d.count })),
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }
          }
        }
      ]
    }
  }

  const getCategoryOption = () => {
    const data = stats?.categoryDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      color: ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899'],
      series: [
        {
          name: '分类分布',
          type: 'pie',
          radius: '70%',
          center: ['40%', '50%'],
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          data: data.map(d => ({ name: d.category || '未知', value: d.count }))
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
          name: 'CAPA数量',
          type: 'bar',
          barWidth: '60%',
          itemStyle: { color: '#10b981', borderRadius: [4, 4, 0, 0] },
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
          <span className="text-gray-600 font-medium">CAPA管理</span>
        </div>
        <h1 className="text-3xl font-bold text-gray-800 tracking-tight">CAPA管理仪表盘</h1>
        <p className="text-gray-500 mt-2 text-sm">全局监控纠正与预防措施、台账数据及计划跟踪，重点关注逾期及关闭情况</p>
      </div>

      <Spin spinning={loading} size="large">
        {/* ── 统计卡片区 ── */}
        <Row gutter={[24, 24]} className="mb-8">
          <Col xs={24} sm={8}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-teal-50 blur-3xl group-hover:bg-teal-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-teal-400 to-emerald-500 text-white shadow-lg shadow-teal-500/30">
                  <SafetyCertificateOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">CAPA总数</div>
                  <div className="text-3xl font-bold text-gray-800 tracking-tight">
                    {stats?.total ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={8}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className={`absolute -right-6 -bottom-6 w-32 h-32 rounded-full blur-3xl transition-colors duration-500 ${stats && stats.overdueCount > 0 ? 'bg-red-50 group-hover:bg-red-100' : 'bg-orange-50 group-hover:bg-orange-100'}`} />
              <div className="relative z-10 flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white shadow-lg ${stats && stats.overdueCount > 0 ? 'bg-gradient-to-br from-red-500 to-rose-600 shadow-red-500/30' : 'bg-gradient-to-br from-orange-400 to-amber-500 shadow-orange-500/30'}`}>
                  <WarningOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">已逾期</div>
                  <div className="flex items-baseline gap-2">
                    <div className="text-3xl font-bold text-gray-800 tracking-tight">
                      {stats?.overdueCount ?? 0}
                    </div>
                    {stats && stats.total > 0 && (
                      <div className={`text-xs font-semibold px-2 py-0.5 rounded-full ${stats.overdueCount > 0 ? 'bg-red-100 text-red-700' : 'bg-orange-100 text-orange-700'}`}>
                        逾期率 {overdueRatio}%
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={8}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-blue-50 blur-3xl group-hover:bg-blue-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/30">
                  <CheckCircleOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">已关闭</div>
                  <div className="flex items-baseline gap-2">
                    <div className="text-3xl font-bold text-gray-800 tracking-tight">
                      {stats?.closedCount ?? 0}
                    </div>
                    {stats && stats.total > 0 && (
                      <div className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                        关闭率 {closedRatio}%
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
            <span className="w-1 h-5 bg-teal-500 rounded-full"></span>
            快捷入口
          </h2>
          <Row gutter={[24, 24]}>
            {navCards.map((card) => (
              <Col key={card.href} xs={24} sm={12}>
                <Link href={card.href} className="block group">
                  <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 transition-all duration-300 hover:border-teal-200 hover:shadow-xl hover:shadow-teal-500/5 hover:-translate-y-1">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 pr-4">
                        <div className={`w-12 h-12 rounded-xl mb-4 flex items-center justify-center bg-gradient-to-br ${card.colorFrom} ${card.colorTo} text-white shadow-lg ${card.shadow} group-hover:scale-110 transition-transform duration-300`}>
                          {card.icon}
                        </div>
                        <h3 className="text-lg font-bold text-gray-800 mb-1 group-hover:text-teal-600 transition-colors">
                          {card.label}
                        </h3>
                        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                          {card.desc}
                        </p>
                      </div>
                      <div className="w-8 h-8 rounded-full bg-gray-50 flex items-center justify-center text-gray-400 group-hover:bg-teal-50 group-hover:text-teal-500 transition-colors">
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
            <span className="w-1 h-5 bg-indigo-500 rounded-full"></span>
            GMP质量体系分析
          </h2>
          <Row gutter={[24, 24]}>
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
                <h3 className="text-base font-semibold text-gray-800 mb-4">来源分布</h3>
                {stats?.sourceDistribution?.length ? (
                  <ReactECharts option={getSourceOption()} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={12}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">分类分布</h3>
                {stats?.categoryDistribution?.length ? (
                  <ReactECharts option={getCategoryOption()} style={{ height: '300px' }} />
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
