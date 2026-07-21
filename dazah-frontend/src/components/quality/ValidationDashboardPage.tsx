'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { Col, Empty, Row, Spin } from 'antd'
import {
  SafetyOutlined,
  FileProtectOutlined,
  ToolOutlined,
  ExperimentOutlined,
  BugOutlined,
  AppstoreOutlined,
  ClockCircleOutlined,
  ApartmentOutlined,
  RightOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { fetchValidationDashboardStats } from '@/lib/api/quality'
import type { ValidationDashboardStats } from '@/types/quality'

const navCards = [
  {
    href: '/quality/validation/plans',
    label: '验证主计划',
    desc: '验证主计划的列表与详情查看',
    icon: <FileProtectOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-purple-500',
    colorTo: 'to-fuchsia-500',
    shadow: 'shadow-purple-500/20',
  },
  {
    href: '/quality/validation/equipment-qualification',
    label: '设备确认',
    desc: '设备确认记录的列表与详情',
    icon: <ToolOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-blue-400',
    colorTo: 'to-indigo-500',
    shadow: 'shadow-blue-500/20',
  },
  {
    href: '/quality/validation/process-validation',
    label: '工艺验证',
    desc: '工艺验证记录的列表与详情',
    icon: <ExperimentOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-teal-400',
    colorTo: 'to-emerald-500',
    shadow: 'shadow-teal-500/20',
  },
  {
    href: '/quality/validation/cleaning-validation',
    label: '清洁验证',
    desc: '清洁验证记录的列表与详情',
    icon: <BugOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-emerald-400',
    colorTo: 'to-green-500',
    shadow: 'shadow-green-500/20',
  },
  {
    href: '/quality/validation/other-validations',
    label: '其他验证',
    desc: '其他验证记录的列表与详情',
    icon: <AppstoreOutlined style={{ fontSize: 24 }} />,
    colorFrom: 'from-orange-400',
    colorTo: 'to-amber-500',
    shadow: 'shadow-orange-500/20',
  },
]

const STATUS_MAP: Record<string, string> = {
  draft: '草稿',
  pending_approval: '待审批',
  approved: '已批准',
  rejected: '已驳回',
  closed: '已关闭',
  in_execution: '执行中',
}

const VALIDATION_TYPE_MAP: Record<string, string> = {
  equipment_qualification: '设备确认',
  process_validation: '工艺验证',
  cleaning_validation: '清洁验证',
  analytical_method_validation: '分析方法验证',
  computer_system_validation: '计算机化系统验证',
  other_validation: '其他验证',
}

export function ValidationDashboardPage() {
  const [stats, setStats] = useState<ValidationDashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void fetchValidationDashboardStats()
      .then(setStats)
      .finally(() => setLoading(false))
  }, [])

  // ECharts Options
  const getStatusOption = () => {
    const data = stats?.statusDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      color: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#64748b'],
      series: [
        {
          name: '状态分布',
          type: 'pie',
          radius: '70%',
          center: ['40%', '50%'],
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          data: data.map(d => ({ name: STATUS_MAP[d.status] || d.status || '未知', value: d.count })),
          emphasis: {
            itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }
          }
        }
      ]
    }
  }

  const getTypeOption = () => {
    const data = stats?.typeDistribution || []
    return {
      tooltip: { trigger: 'item' },
      legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, bottom: 20 },
      color: ['#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308', '#84cc16'],
      series: [
        {
          name: '验证类型',
          type: 'pie',
          radius: '70%',
          center: ['40%', '50%'],
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
          data: data.map(d => ({ name: VALIDATION_TYPE_MAP[d.validation_type] || d.validation_type || '未知', value: d.count }))
        }
      ]
    }
  }

  const getExecutionOption = () => {
    const data = stats?.executionDistribution || []
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
      xAxis: {
        type: 'category',
        data: data.map(d => VALIDATION_TYPE_MAP[d.validation_type] || d.validation_type || '未知'),
        axisTick: { alignWithLabel: true },
        axisLabel: { interval: 0, rotate: 45, fontSize: 11 }
      },
      yAxis: { type: 'value' },
      series: [
        {
          name: '执行数量',
          type: 'bar',
          barWidth: '60%',
          itemStyle: {
            color: '#8b5cf6',
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
          <span className="text-gray-600 font-medium">验证与确认</span>
        </div>
        <h1 className="text-3xl font-bold text-gray-800 tracking-tight">验证与确认仪表盘</h1>
        <p className="text-gray-500 mt-2 text-sm">全局监控验证主计划、设备/工艺验证记录及再验证提醒，关注合规风险</p>
      </div>

      <Spin spinning={loading} size="large">
        {/* ── 统计卡片区 ── */}
        <Row gutter={[24, 24]} className="mb-8">
          <Col xs={24} sm={8}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-purple-50 blur-3xl group-hover:bg-purple-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-purple-500 to-indigo-600 text-white shadow-lg shadow-purple-500/30">
                  <SafetyOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">验证主计划总数</div>
                  <div className="text-4xl font-bold text-gray-800 tracking-tight">
                    {stats?.total ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={8}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-blue-50 blur-3xl group-hover:bg-blue-100 transition-colors duration-500" />
              <div className="relative z-10 flex items-start gap-4">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br from-blue-400 to-cyan-500 text-white shadow-lg shadow-blue-500/30">
                  <ApartmentOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">执行子表总数</div>
                  <div className="text-4xl font-bold text-gray-800 tracking-tight">
                    {stats?.executionDistribution.reduce((sum, item) => sum + item.count, 0) ?? 0}
                  </div>
                </div>
              </div>
            </div>
          </Col>

          <Col xs={24} sm={8}>
            <div className="relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow duration-300 group h-full">
              <div className={`absolute -right-6 -bottom-6 w-32 h-32 rounded-full blur-3xl transition-colors duration-500 ${stats && stats.revalidationUpcoming > 0 ? 'bg-orange-50 group-hover:bg-orange-100' : 'bg-green-50 group-hover:bg-green-100'}`} />
              <div className="relative z-10 flex items-start gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white shadow-lg ${stats && stats.revalidationUpcoming > 0 ? 'bg-gradient-to-br from-orange-400 to-red-500 shadow-orange-500/30' : 'bg-gradient-to-br from-green-400 to-emerald-500 shadow-green-500/30'}`}>
                  <ClockCircleOutlined style={{ fontSize: 24 }} />
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-500 mb-1">近期待再验证</div>
                  <div className="text-4xl font-bold text-gray-800 tracking-tight">
                    {stats?.revalidationUpcoming ?? 0}
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
          <Row gutter={[16, 16]}>
            {navCards.map((card) => (
              <Col key={card.href} xs={24} sm={12} md={8} lg={24 / 5}>
                <Link href={card.href} className="block group h-full">
                  <div className="h-full relative overflow-hidden bg-white border border-gray-100 rounded-2xl p-5 transition-all duration-300 hover:border-teal-200 hover:shadow-xl hover:shadow-teal-500/5 hover:-translate-y-1 flex flex-col items-center text-center">
                    <div className={`w-12 h-12 rounded-xl mb-3 flex items-center justify-center bg-gradient-to-br ${card.colorFrom} ${card.colorTo} text-white shadow-lg ${card.shadow} group-hover:scale-110 transition-transform duration-300`}>
                      {card.icon}
                    </div>
                    <h3 className="text-sm font-bold text-gray-800 mb-1 group-hover:text-teal-600 transition-colors">
                      {card.label}
                    </h3>
                    <p className="text-[11px] text-gray-500 leading-snug line-clamp-2">
                      {card.desc}
                    </p>
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
                <h3 className="text-base font-semibold text-gray-800 mb-4">验证类型分布</h3>
                {stats?.typeDistribution?.length ? (
                  <ReactECharts option={getTypeOption()} style={{ height: '300px' }} />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" className="my-16" />
                )}
              </div>
            </Col>
            <Col xs={24} md={24}>
              <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                <h3 className="text-base font-semibold text-gray-800 mb-4">执行子表类型统计</h3>
                {stats?.executionDistribution?.length ? (
                  <ReactECharts option={getExecutionOption()} style={{ height: '300px' }} />
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
