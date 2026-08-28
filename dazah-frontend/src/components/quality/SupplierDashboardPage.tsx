'use client'

import Link from 'next/link'
import { Col, Empty, Row, Spin, Tooltip } from 'antd'
import {
  SafetyCertificateOutlined,
  CheckCircleOutlined,
  ShopOutlined,
  ClockCircleOutlined,
  AlertOutlined,
  RightOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import ReactECharts from 'echarts-for-react'
import { fetchSupplierStatistics } from '@/lib/api/client/quality'
import type { SupplierDashboardStats } from '@/types/quality'

/* ── 色板（GMP 审计风格）── */
const C = {
  primary: '#2563eb',
  success: '#059669',
  warning: '#d97706',
  danger: '#dc2626',
  info: '#6366f1',
  solid: '#f97316',
  liquid: '#3b82f6',
  pack: '#8b5cf6',
  bg: '#f8fafc',
}

function pct(v: number) {
  return v.toFixed(1) + '%'
}

export function SupplierDashboardPage() {
  const { data: stats, isLoading: loading } = useQuery<SupplierDashboardStats>({
    queryKey: ['quality-supplier', 'stats'],
    queryFn: fetchSupplierStatistics,
  })

  const hasData = (stats?.total ?? 0) > 0

  /* ── 物料类型合规率 柱状图 ── */
  const materialComplianceOption = () => {
    const data = stats?.material_type_compliance || []
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (p: any) => {
          const d = p[0]
          return `${d.name}<br/>总量: ${d.value} 项`
        },
      },
      legend: { bottom: 0 },
      grid: { left: 8, right: 8, top: 8, bottom: 36 },
      xAxis: { type: 'category', data: data.map(d => d.type), axisLabel: { fontWeight: 500 } },
      yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
      series: [
        { name: '已完成', type: 'bar', stack: 'total', data: data.map(d => d.completed), itemStyle: { color: C.success, borderRadius: [4, 4, 0, 0] }, barWidth: 48 },
        { name: '未完成', type: 'bar', stack: 'total', data: data.map(d => d.pending), itemStyle: { color: '#fca5a5' } },
      ],
    }
  }

  /* ── 资质类型完成率 横向柱状图 ── */
  const qualComplianceOption = () => {
    const data = (stats?.qualification_compliance || [])
      .filter(d => d.total > 0)
      .sort((a, b) => a.completion_rate - b.completion_rate)
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (p: any) => {
          const d = p[0]
          return `${d.name}<br/>已完成: ${data.find(x => x.name === d.name)?.completed}/${data.find(x => x.name === d.name)?.total} (${data.find(x => x.name === d.name)?.completion_rate}%)`
        },
      },
      grid: { left: 110, right: 48, top: 4, bottom: 4 },
      xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { type: 'dashed' } } },
      yAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { fontSize: 11, width: 100, overflow: 'truncate' } },
      series: [{
        name: '完成率', type: 'bar',
        data: data.map(d => ({
          value: d.completion_rate,
          itemStyle: { color: d.completion_rate >= 80 ? C.success : d.completion_rate >= 50 ? C.warning : C.danger, borderRadius: [0, 4, 4, 0] },
        })),
        barWidth: 16,
        label: { show: true, position: 'right', fontSize: 11, formatter: (p: any) => `${p.value}%` },
      }],
    }
  }

  /* ── 供应商风险排名 ── */
  const riskRankingOption = () => {
    const data = stats?.supplier_risk_ranking || []
    const names = data.map(d => {
      const short = d.name.replace(/[\n\r]/g, ' ').trim()
      return short.length > 12 ? short.slice(0, 12) + '...' : short
    })
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (p: any) => {
          const d = data[p[0].dataIndex]
          return `${d.name.replace(/\n/g, '<br/>')}<br/>总计: ${d.total} | 已完成: ${d.completed} | 未完成: ${d.pending}<br/>已延期: ${d.expired} | 30天内到期: ${d.due30}`
        },
      },
      legend: { bottom: 0 },
      grid: { left: 8, right: 8, top: 8, bottom: 36 },
      xAxis: { type: 'category', data: names, axisLabel: { rotate: 30, fontSize: 10 } },
      yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
      series: [
        { name: '已完成', type: 'bar', stack: 'total', data: data.map(d => d.completed), itemStyle: { color: C.success }, barWidth: 36 },
        { name: '未完成', type: 'bar', stack: 'total', data: data.map(d => d.pending), itemStyle: { color: '#fca5a5' } },
        { name: '已延期', type: 'bar', data: data.map(d => d.expired), itemStyle: { color: C.danger }, barWidth: 36, barGap: '-100%', z: 10 },
      ],
    }
  }

  /* ── 到期状态分布 环形图 ── */
  const expiryDonutOption = () => ({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    color: [C.danger, '#f59e0b', '#fb923c', '#84cc16', '#cbd5e1'],
    series: [{
      name: '到期状态', type: 'pie', radius: ['50%', '75%'],
      center: ['50%', '46%'],
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 3 },
      label: { show: true, formatter: '{b}\n{d}%' },
      data: [
        { name: '已延期', value: stats?.expired_count ?? 0 },
        { name: '30天内到期', value: stats?.due_30_count ?? 0 },
        { name: '60天内到期', value: stats?.due_60_count ?? 0 },
        { name: '90天内到期', value: stats?.due_90_count ?? 0 },
        { name: '正常', value: stats?.normal_count ?? 0 },
      ].filter(d => d.value > 0),
    }],
  })

  /* ── 到期时间线 ── */
  const timelineOption = () => {
    const data = stats?.expiry_timeline || []
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 8, right: 8, top: 12, bottom: 8 },
      xAxis: { type: 'category', data: data.map(d => d.month), axisLabel: { rotate: 45, fontSize: 10 } },
      yAxis: { type: 'value', splitLine: { lineStyle: { type: 'dashed' } } },
      series: [{
        type: 'bar',
        data: data.map(d => d.count),
        itemStyle: {
          color: C.primary,
          borderRadius: [3, 3, 0, 0],
        },
        barWidth: 16,
      }],
    }
  }

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', paddingBottom: 40 }}>
      {/* ── 标题 ── */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 4 }}>
          质量管理 / <span style={{ color: '#475569', fontWeight: 500 }}>供应商管理</span>
        </div>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: '#0f172a', margin: 0, letterSpacing: -0.5 }}>
          供应商资质仪表盘
        </h1>
        <p style={{ color: '#64748b', marginTop: 6, fontSize: 13 }}>
          基于供应商资质多维表格数据，实时监控 GMP 合规状态
        </p>
      </div>

      <Spin spinning={loading} size="large">
        {!hasData && !loading ? (
          <Empty description="暂无供应商资质数据" style={{ marginTop: 80 }} />
        ) : (
          <>
            {/* ── KPI 卡片 ── */}
            <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
              {/* 资质总数 */}
              <Col xs={12} sm={8} md={4}>
                <div style={{ background: '#fff', borderRadius: 12, padding: '20px 18px', border: '1px solid #e2e8f0', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', right: -16, top: -16, width: 64, height: 64, borderRadius: '50%', background: '#eff6ff' }} />
                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <SafetyCertificateOutlined style={{ fontSize: 22, color: C.primary, marginBottom: 10 }} />
                    <div style={{ fontSize: 12, color: '#64748b' }}>资质总数</div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: '#0f172a' }}>{stats?.total ?? 0}</div>
                  </div>
                </div>
              </Col>
              {/* 合规率 */}
              <Col xs={12} sm={8} md={4}>
                <div style={{ background: '#fff', borderRadius: 12, padding: '20px 18px', border: '1px solid #e2e8f0', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', right: -16, top: -16, width: 64, height: 64, borderRadius: '50%', background: '#ecfdf5' }} />
                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <CheckCircleOutlined style={{ fontSize: 22, color: C.success, marginBottom: 10 }} />
                    <div style={{ fontSize: 12, color: '#64748b' }}>合格率</div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: (stats?.completion_rate ?? 0) >= 80 ? C.success : C.warning }}>
                      {stats?.completion_rate ?? 0}
                      <span style={{ fontSize: 14, fontWeight: 500 }}>%</span>
                    </div>
                  </div>
                </div>
              </Col>
              {/* 已延期 */}
              <Col xs={12} sm={8} md={4}>
                <Tooltip title="资质已过截止日期，存在GMP合规风险">
                  <div style={{ background: '#fff', borderRadius: 12, padding: '20px 18px', border: `1px solid ${(stats?.expired_count ?? 0) > 0 ? '#fecaca' : '#e2e8f0'}`, position: 'relative', overflow: 'hidden', cursor: 'help' }}>
                    <div style={{ position: 'absolute', right: -16, top: -16, width: 64, height: 64, borderRadius: '50%', background: (stats?.expired_count ?? 0) > 0 ? '#fef2f2' : '#f8fafc' }} />
                    <div style={{ position: 'relative', zIndex: 1 }}>
                      <ExclamationCircleOutlined style={{ fontSize: 22, color: (stats?.expired_count ?? 0) > 0 ? C.danger : '#94a3b8', marginBottom: 10 }} />
                      <div style={{ fontSize: 12, color: '#64748b' }}>已延期</div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: (stats?.expired_count ?? 0) > 0 ? C.danger : '#0f172a' }}>{stats?.expired_count ?? 0}</div>
                    </div>
                  </div>
                </Tooltip>
              </Col>
              {/* 即将到期 */}
              <Col xs={12} sm={8} md={4}>
                <Tooltip title={`30天: ${stats?.due_30_count ?? 0} | 60天: ${stats?.due_60_count ?? 0} | 90天: ${stats?.due_90_count ?? 0}`}>
                  <div style={{ background: '#fff', borderRadius: 12, padding: '20px 18px', border: '1px solid #e2e8f0', position: 'relative', overflow: 'hidden', cursor: 'help' }}>
                    <div style={{ position: 'absolute', right: -16, top: -16, width: 64, height: 64, borderRadius: '50%', background: '#fffbeb' }} />
                    <div style={{ position: 'relative', zIndex: 1 }}>
                      <ClockCircleOutlined style={{ fontSize: 22, color: C.warning, marginBottom: 10 }} />
                      <div style={{ fontSize: 12, color: '#64748b' }}>即将到期</div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: C.warning }}>
                        {(stats?.due_30_count ?? 0) + (stats?.due_60_count ?? 0) + (stats?.due_90_count ?? 0)}
                      </div>
                    </div>
                  </div>
                </Tooltip>
              </Col>
              {/* 供应商数 */}
              <Col xs={12} sm={8} md={4}>
                <div style={{ background: '#fff', borderRadius: 12, padding: '20px 18px', border: '1px solid #e2e8f0', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', right: -16, top: -16, width: 64, height: 64, borderRadius: '50%', background: '#f5f3ff' }} />
                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <ShopOutlined style={{ fontSize: 22, color: C.info, marginBottom: 10 }} />
                    <div style={{ fontSize: 12, color: '#64748b' }}>供应商数</div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: '#0f172a' }}>{stats?.supplier_count ?? 0}</div>
                  </div>
                </div>
              </Col>
              {/* 未完成 */}
              <Col xs={12} sm={8} md={4}>
                <div style={{ background: '#fff', borderRadius: 12, padding: '20px 18px', border: '1px solid #e2e8f0', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', right: -16, top: -16, width: 64, height: 64, borderRadius: '50%', background: '#fff7ed' }} />
                  <div style={{ position: 'relative', zIndex: 1 }}>
                    <AlertOutlined style={{ fontSize: 22, color: '#f97316', marginBottom: 10 }} />
                    <div style={{ fontSize: 12, color: '#64748b' }}>待完成</div>
                    <div style={{ fontSize: 28, fontWeight: 700, color: '#0f172a' }}>{stats?.pending ?? 0}</div>
                  </div>
                </div>
              </Col>
            </Row>

            {/* ── 快捷入口 ── */}
            <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
              <Col xs={24} sm={8}>
                <Link href="/quality/suppliers/qualification" style={{ textDecoration: 'none' }}>
                  <div style={{ background: '#fff', borderRadius: 12, padding: '18px 20px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'all .2s', cursor: 'pointer' }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = '#93c5fd'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(37,99,235,.08)' }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.boxShadow = 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 40, height: 40, borderRadius: 10, background: 'linear-gradient(135deg, #2563eb, #6366f1)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 18 }}>
                        <SafetyCertificateOutlined />
                      </div>
                      <div>
                        <div style={{ fontWeight: 600, color: '#0f172a' }}>供应商资质台账</div>
                        <div style={{ fontSize: 12, color: '#94a3b8' }}>管理资质信息，实时同步飞书</div>
                      </div>
                    </div>
                    <RightOutlined style={{ color: '#94a3b8' }} />
                  </div>
                </Link>
              </Col>
            </Row>

            {/* ── 图表 第1行 ── */}
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} lg={14}>
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: 20 }}>
                  <h3 style={{ fontSize: 15, fontWeight: 600, color: '#0f172a', margin: '0 0 4px' }}>供应商风险排名 TOP10</h3>
                  <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 12px' }}>按逾期 + 待完成综合风险排序（红框 = 已延期项）</p>
                  <ReactECharts option={riskRankingOption()} style={{ height: 320 }} />
                </div>
              </Col>
              <Col xs={24} lg={10}>
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: 20 }}>
                  <h3 style={{ fontSize: 15, fontWeight: 600, color: '#0f172a', margin: '0 0 4px' }}>到期状态分布</h3>
                  <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 12px' }}>截止日期与当前时间对比分析</p>
                  <ReactECharts option={expiryDonutOption()} style={{ height: 320 }} />
                </div>
              </Col>
            </Row>

            {/* ── 图表 第2行 ── */}
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} lg={12}>
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: 20 }}>
                  <h3 style={{ fontSize: 15, fontWeight: 600, color: '#0f172a', margin: '0 0 4px' }}>物料类型合规分析</h3>
                  <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 12px' }}>固体 / 液体 / 包材 — 已完成 vs 未完成</p>
                  <ReactECharts option={materialComplianceOption()} style={{ height: 300 }} />
                </div>
              </Col>
              <Col xs={24} lg={12}>
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: 20 }}>
                  <h3 style={{ fontSize: 15, fontWeight: 600, color: '#0f172a', margin: '0 0 4px' }}>到期时间趋势</h3>
                  <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 12px' }}>各月截止的资质数量分布</p>
                  <ReactECharts option={timelineOption()} style={{ height: 300 }} />
                </div>
              </Col>
            </Row>

            {/* ── 图表 第3行：资质类型完成率 ── */}
            <Row gutter={[16, 16]}>
              <Col xs={24}>
                <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', padding: 20 }}>
                  <h3 style={{ fontSize: 15, fontWeight: 600, color: '#0f172a', margin: '0 0 4px' }}>资质类型完成率</h3>
                  <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 12px' }}>
                    各类资质的完成进度（绿≥80% / 黄≥50% / 红&lt;50%），未完成的需重点关注
                  </p>
                  {(stats?.qualification_compliance || []).length > 0 ? (
                    <ReactECharts option={qualComplianceOption()} style={{ height: 380 }} />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" style={{ margin: '40px 0' }} />
                  )}
                </div>
              </Col>
            </Row>
          </>
        )}
      </Spin>
    </div>
  )
}
