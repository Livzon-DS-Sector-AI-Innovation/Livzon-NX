'use client'
// 201二车间 MC（霉酚酸）— 首页（仪表盘 + 6宫格工段选择）— 按文档规格

import { useEffect, useState, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { Card, Row, Col, Typography, Statistic, Button, Tag, Space, Spin, Progress, DatePicker } from 'antd'
import {ExperimentOutlined, FilterOutlined, BulbOutlined,
  CalculatorOutlined, CheckCircleOutlined, DatabaseOutlined,
  ArrowRightOutlined, NodeIndexOutlined,} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs, { type Dayjs } from 'dayjs'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'

const { Title, Text } = Typography

const STAGES = [
  { key: 'crude', label: '粗提', desc: '发酵液→粗品', icon: <ExperimentOutlined style={{ fontSize: 40 }} />, color: '#52c41a', path: '/production/batches/workshop/201-2/crude-extraction' },
  { key: 'extraction', label: '提取', desc: '粗品→萃取液→湿粉', icon: <FilterOutlined style={{ fontSize: 40 }} />, color: '#1890ff', path: '/production/batches/workshop/201-2/extraction' },
  { key: 'refinement', label: '二次精制', desc: '湿粉→二次结晶→干粉 MC-F2', icon: <BulbOutlined style={{ fontSize: 40 }} />, color: '#13c2c2', path: '/production/batches/workshop/201-2/mc-refinement' },
  { key: 'blending', label: '混粉杂质计算', desc: '多批次干粉混合+5RRT精算', icon: <CalculatorOutlined style={{ fontSize: 40 }} />, color: '#fa8c16', path: '/production/batches/workshop/201-2/blending' },
  { key: 'qc', label: '混粉入库', desc: 'QC检验+成品入库', icon: <CheckCircleOutlined style={{ fontSize: 40 }} />, color: '#722ed1', path: '/production/batches/workshop/201-2/qc-inspection' },
  { key: 'ba', label: '丁酯盘点', desc: '乙酸丁酯库存管理', icon: <DatabaseOutlined style={{ fontSize: 40 }} />, color: '#f5222d', path: '/production/batches/workshop/201-2/butyl-acetate' },
]

const STAGE_MAP: Record<string, (typeof STAGES)[number]> = {}
STAGES.forEach(s => { STAGE_MAP[s.key] = s })

export default function Workshop2012Page() {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<'dashboard' | 'workshop'>('dashboard')
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<any>(null)
  const [selectedMonth, setSelectedMonth] = useState<Dayjs>(dayjs())

  const fetchData = useCallback(async (monthStr: string) => {
    setLoading(true)
    try {
      const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
      const r = await fetch(`${API}/api/v1/production/mc/dashboard/summary?month=${monthStr}`)
      const json = await r.json()
      if (json.code === 200) setData(json.data)
    } catch (e) { console.error('加载仪表盘失败', e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    fetchData(selectedMonth.format('YYYY-MM')) // eslint-disable-line react-hooks/set-state-in-effect
  }, [selectedMonth, fetchData])

  const handleMonthChange = (d: Dayjs | null) => {
    if (d) setSelectedMonth(d)
  }

  const d = data || {}
  const stages = d.stages || {}
  const statusDist = d.status_distribution || []
  const monthlyTrend: { month: number; output_kg: number }[] = d.monthly_trend || [] // eslint-disable-line react-hooks/exhaustive-deps
  const rrtPassRates: { label: string; field: string; limit: number; total: number; passed: number; rate: number }[] = d.rrt_pass_rates || []
  const currentMonth = selectedMonth.month() + 1

  const outputChartOption = useMemo(() => ({
    tooltip: { trigger: 'axis', formatter: (p: any) => `${p[0].name}月<br/>产量: ${p[0].value.toLocaleString()} kg` },
    xAxis: { type: 'category', data: monthlyTrend.map(t => `${t.month}月`) },
    yAxis: { type: 'value', name: 'kg', axisLabel: { formatter: (v: number) => (v / 1000).toFixed(0) + 't' } },
    series: [{
      type: 'bar', name: '产量', data: monthlyTrend.map(t => {
        const v = t.output_kg || 0
        return { value: v, itemStyle: { color: t.month === currentMonth ? '#1677ff' : '#91caff' } }
      }),
      barMaxWidth: 40,
    }],
    grid: { left: 50, right: 20, top: 10, bottom: 30 },
  }), [monthlyTrend, currentMonth])

  if (loading) return <div className="flex justify-center py-20"><Spin size="large" /></div>

  return (
    <div className="p-6">
      <div className="mb-4">
        <Title level={4} style={{ margin: 0 }}>
          霉酚酸提炼生产管理系统
        </Title>
        <Text type="secondary">201二车间 — MC（霉酚酸）粗提 → 提取 → 二次精制 → 混粉计算 → QC检验 → 入库</Text>
      </div>

      <Space className="mb-4" align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
        <Space align="center">
          <Button type={activeTab === 'dashboard' ? 'primary' : 'default'} size="large" onClick={() => setActiveTab('dashboard')}>📊 仪表盘</Button>
          <Button type={activeTab === 'workshop' ? 'primary' : 'default'} size="large" onClick={() => setActiveTab('workshop')}>🏭 车间工段</Button>
          <DatePicker
            picker="month"
            value={selectedMonth}
            onChange={handleMonthChange}
            allowClear={false}
            format="YYYY-MM"
            style={{ marginLeft: 16 }}
          />
        </Space>
        <Space size={8}>
          <SyncSettingsButton productName="霉酚酸" syncTarget="production_plan" />
          <Button size="large" icon={<NodeIndexOutlined />} onClick={() => router.push('/production/batches/workshop/201-2/traceability')}>
            全链路追溯
          </Button>
        </Space>
      </Space>

      {/* ═══════════ 仪表盘 ═══════════ */}
      {activeTab === 'dashboard' && (
        <>
          {/* KPI 卡片 */}
          <Row gutter={16} className="mb-4">
            <Col span={6}>
              <Card><Statistic title="本月产量" value={d.monthly_output_kg || 0} suffix="kg" styles={{ content: { color: '#1677ff', fontSize: 28 } }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="本月批次" value={d.monthly_batches || 0} suffix="批" styles={{ content: { color: '#52c41a', fontSize: 28 } }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="平均收率" value={d.avg_yield || 0} suffix="%" styles={{ content: { color: '#fa8c16', fontSize: 28 } }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="收率达标率" value={d.pass_rate || 0} suffix="%" styles={{ content: { color: d.pass_rate >= 80 ? '#52c41a' : '#fa8c16', fontSize: 28 } }} /></Card>
            </Col>
          </Row>

          {/* 产量趋势 */}
          <Row gutter={16} className="mb-4" style={{ minHeight: 280 }}>
            <Col span={14}>
              <Card title={`📈 ${selectedMonth.year()}年产量趋势`} style={{ height: '100%' }}>
                {monthlyTrend.length > 0 ? (
                  <ReactECharts option={outputChartOption} style={{ height: 220 }} />
                ) : <Text type="secondary">暂无数据</Text>}
              </Card>
            </Col>
            <Col span={10}>
              <Card title="🥧 批次状态" style={{ height: '100%' }}>
                <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                  {statusDist.map((item: any) => (
                    <Row key={item.status} justify="space-between" align="middle">
                      <Col>
                        <div style={{ width: 10, height: 10, borderRadius: 10, background: item.color, display: 'inline-block', marginRight: 8 }} />
                        <Text>{item.status}</Text>
                      </Col>
                      <Col><Text strong style={{ fontSize: 20, color: item.color }}>{item.count}</Text><Text type="secondary" style={{ marginLeft: 4 }}>批</Text></Col>
                    </Row>
                  ))}
                </Space>
              </Card>
            </Col>
          </Row>

          {/* 杂质合格趋势 + 溶剂库存预警 */}
          <Row gutter={16} className="mb-4">
            <Col span={14}>
              <Card title="🔬 本月 RRT 杂质合格率" style={{ height: '100%' }}>
                {rrtPassRates.length > 0 ? (
                  <Row gutter={[8, 8]} justify="center">
                    {rrtPassRates.map((item) => {
                      const color = item.rate >= 90 ? '#52c41a' : item.rate >= 70 ? '#fa8c16' : '#ff4d4f'
                      return (
                        <Col key={item.field} style={{ textAlign: 'center', padding: '0 4px' }}>
                          <Progress type="circle" percent={item.rate} size={85}
                            strokeColor={color}
                            format={(pct) => `${pct?.toFixed(0)}%`} />
                          <div style={{ marginTop: 4 }}>
                            <Text strong style={{ fontSize: 11 }}>{item.label}</Text>
                          </div>
                          <div>
                            <Text type="secondary" style={{ fontSize: 10 }}>≤{item.limit}% · {item.passed}/{item.total}批</Text>
                          </div>
                        </Col>
                      )
                    })}
                  </Row>
                ) : (
                  <Text type="secondary">暂无数据</Text>
                )}
              </Card>
            </Col>
            <Col span={10}>
              <Card title="🧴 溶剂库存预警" style={{ height: '100%' }}>
                <Statistic title="乙酸丁酯库存" value={d.ba_stock_kg || 0} suffix="kg"
                  styles={{ content: { color: (d.ba_stock_kg || 0) < 1000 ? '#f5222d' : '#52c41a', fontSize: 32 } }} />
                <div className="mt-2">
                  <Text type="secondary">在库批次：{d.ba_batches || 0} 批</Text><br />
                  <Text type="secondary">本月消耗：{d.ba_monthly_consume || 0} kg</Text>
                </div>
                {(d.ba_stock_kg || 0) < 1000 && (
                  <Tag color="red" className="mt-2">⚠️ 库存不足 — 剩余不足 7 天用量</Tag>
                )}
              </Card>
            </Col>
          </Row>

        </>
      )}

      {/* ═══════════ 车间 6 宫格 ═══════════ */}
      {activeTab === 'workshop' && (
        <>
          <Title level={5} className="mb-4">🏭 车间生产控制台 — 请选择生产工段</Title>
          <Row gutter={[16, 16]}>
            {STAGES.map(s => {
              const count = stages[s.key] || 0
              return (
                <Col span={8} key={s.key}>
                  <Card
                    hoverable
                    onClick={() => router.push(s.path)}
                    style={{ borderTop: `4px solid ${s.color}`, minHeight: 200, textAlign: 'center' }}
                  >
                    <div style={{ color: s.color, marginBottom: 8 }}>{s.icon}</div>
                    <Title level={5} style={{ color: s.color }}>{s.label}</Title>
                    <Text type="secondary">{s.desc}</Text>
                    <div className="mt-3">
                      {s.key === 'ba' ? (
                        <Text strong style={{ fontSize: 16, color: (d.ba_stock_kg || 0) < 1000 ? '#f5222d' : '#52c41a' }}>
                          {d.ba_stock_kg ? `${(d.ba_stock_kg / 1000).toFixed(2)} 吨` : '暂无数据'}
                        </Text>
                      ) : (
                        <Tag color={count > 0 ? 'processing' : 'default'} style={{ fontSize: 14, padding: '4px 12px' }}>
                          {count > 0 ? `${count} 批进行中` : '暂无批次'}
                        </Tag>
                      )}
                    </div>
                    {count > 0 && s.key === 'blending' && (
                      <div className="mt-1"><Text type="danger" style={{ fontSize: 11 }}>⚠️ 关注杂质超限</Text></div>
                    )}
                    <div className="mt-3">
                      <Button type="primary" size="small" icon={<ArrowRightOutlined />}>进入工段</Button>
                    </div>
                  </Card>
                </Col>
              )
            })}
          </Row>
        </>
      )}
    </div>
  )
}
