'use client'
// 203车间 FA（L-苯丙氨酸）— 首页（仪表盘 + 8宫格工段选择）

import { useEffect, useState, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Card, Row, Col, Typography, Statistic, Button, Space, Spin, DatePicker, Select, Input, Tag } from 'antd'
import {
  ExperimentOutlined, FilterOutlined, BulbOutlined,
  CloudOutlined, DropboxOutlined, ToolOutlined,
  ArrowRightOutlined, CompressOutlined, HddOutlined, NodeIndexOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import SyncSettingsButton from '@/components/production/SyncSettingsButton'

const { Title, Text } = Typography

const STAGES = [
  { key: 'fermentation', label: '发酵液放罐',       desc: '菌种培养→发酵液→放罐',         icon: <ExperimentOutlined style={{ fontSize: 40 }} />, color: '#52c41a', path: '/production/batches/workshop/203/fermentation' },
  { key: 'acidification', label: '酸化过滤',         desc: 'pH调节→酸化→过滤',             icon: <FilterOutlined style={{ fontSize: 40 }} />, color: '#1890ff', path: '/production/batches/workshop/203/acidification' },
  { key: 'decolor1',      label: '一次脱色过滤',     desc: '活性炭脱色→板框过滤',         icon: <BulbOutlined style={{ fontSize: 40 }} />, color: '#13c2c2', path: '/production/batches/workshop/203/decolor1' },
  { key: 'mvr',           label: 'MVR 浓缩',         desc: 'MVR 蒸发浓缩',                icon: <CompressOutlined style={{ fontSize: 40 }} />, color: '#fa8c16', path: '/production/batches/workshop/203/mvr' },
  { key: 'mother_liquor', label: '母液溶粉',         desc: '母液溶粉回收',                icon: <DropboxOutlined style={{ fontSize: 40 }} />, color: '#722ed1', path: '/production/batches/workshop/203/mother-liquor' },
  { key: 'plate_recovery',label: '板框回收',         desc: '板框滤渣回收',                icon: <ToolOutlined style={{ fontSize: 40 }} />, color: '#f5222d', path: '/production/batches/workshop/203/plate-recovery' },
  { key: 'decolor_centrifuge', label: '脱色离心',    desc: '二次脱色→离心',             icon: <HddOutlined style={{ fontSize: 40 }} />, color: '#eb2f96', path: '/production/batches/workshop/203/decolor-centrifuge' },
  { key: 'intermediate',  label: '母液中间体相关数据', desc: '母液/中间体检测数据汇总',      icon: <CloudOutlined style={{ fontSize: 40 }} />, color: '#2f54eb', path: '/production/batches/workshop/203/intermediate' },
]

const STAGE_MAP: Record<string, (typeof STAGES)[number]> = {}
STAGES.forEach(s => { STAGE_MAP[s.key] = s })

export default function Workshop203Page() {
  return (
    <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spin size="large" /></div>}>
      <Workshop203Content />
    </Suspense>
  )
}

function Workshop203Content() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<'dashboard' | 'workshop'>(
    searchParams.get('tab') === 'workshop' ? 'workshop' : 'dashboard'
  )
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<any>(null)
  const [selectedMonth, setSelectedMonth] = useState<Dayjs>(dayjs('2026-07'))

  const fetchData = useCallback(async (monthStr: string) => {
    setLoading(true)
    try {
      const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
      const r = await fetch(`${API}/api/v1/production/fa/dashboard/summary?month=${monthStr}`)
      const json = await r.json()
      if (json.code === 200) setData(json.data)
    } catch (e) { console.error('加载仪表盘失败', e) }
    finally { setLoading(false) }
  }, [])

  const [yieldData, setYieldData] = useState<any>(null)
  const [goldenData, setGoldenData] = useState<any>(null)
  const [goldenScore, setGoldenScore] = useState<string>('stability')
  const [compareBatch, setCompareBatch] = useState('')
  const [compareData, setCompareData] = useState<any>(null)
  const [compareLoading, setCompareLoading] = useState(false)

  useEffect(() => {
    fetchData(selectedMonth.format('YYYY-MM'))
  }, [selectedMonth, fetchData])

  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
    fetch(`${API}/api/v1/production/fa/dashboard/yield-chain?month=${selectedMonth.format('YYYY-MM')}`)
      .then(r => r.json())
      .then(json => { if (json.code === 200) setYieldData(json.data) })
      .catch(() => {})
  }, [selectedMonth])

  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
    fetch(`${API}/api/v1/production/fa/dashboard/golden-batches?limit=5&score=${goldenScore}`)
      .then(r => r.json())
      .then(json => { if (json.code === 200) setGoldenData(json.data) })
      .catch(() => {})
  }, [goldenScore])

  const handleMonthChange = (d: Dayjs | null) => {
    if (d) setSelectedMonth(d)
  }

  const doCompare = useCallback(async () => {
    if (!compareBatch.trim()) return
    setCompareLoading(true); setCompareData(null)
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/v1/production/fa/dashboard/batch-params?batch_no=${encodeURIComponent(compareBatch.trim())}&score=${goldenScore}`)
      const json = await r.json()
      if (json.code === 200) setCompareData(json.data)
      else setCompareData({ error: json.message || '未找到数据' })
    } catch { setCompareData({ error: '网络错误' }) }
    finally { setCompareLoading(false) }
  }, [compareBatch, goldenScore])

  const d = data || {}

  if (loading) return <div className="flex justify-center py-20"><Spin size="large" /></div>

  return (
    <div className="p-6">
      <div className="mb-4">
        <Title level={4} style={{ margin: 0 }}>
          L-苯丙氨酸（FA）生产管理系统
        </Title>
        <Text type="secondary">203车间 — 发酵液放罐 → 酸化过滤 → 脱色 → MVR浓缩 → 母液溶粉 → 板框回收 → 脱色离心</Text>
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
          <SyncSettingsButton productName="L-苯丙氨酸" syncTarget="production_plan" />
          <Button size="large" icon={<NodeIndexOutlined />} onClick={() => router.push('/production/batches/workshop/203/traceability')}>
            批次追踪
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

          {/* ── 左右分栏：收率+黄金 | 批次对比 ── */}
          <Row gutter={16} style={{ alignItems: 'stretch' }}>
            {/* 左侧 */}
            <Col span={12} style={{ display: 'flex', flexDirection: 'column' }}>
              {/* ── 收率全链路 ── */}
              {yieldData?.stages?.length > 0 && (
                <Card size="small" style={{ marginBottom: 16 }} title="📊 收率全链路">
                  <Row gutter={[8, 8]}>
                    {yieldData.stages.map((s: any) => (
                      <Col span={12} key={s.stage}>
                        <Statistic title={s.label} value={s.avg_yield} suffix="%"
                          styles={{ content: { color: s.avg_yield >= 90 ? '#52c41a' : '#fa8c16', fontSize: 20 } }} />
                        <div style={{ fontSize: 10, color: '#999' }}>{s.count}批 | {s.min_yield}%~{s.max_yield}%</div>
                      </Col>
                    ))}
                  </Row>
                  {yieldData.summary && (
                    <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f0f0f0', fontSize: 12 }}>
                      <Text>累计：<Text strong style={{ color: '#fa8c16' }}>{yieldData.summary.avg_cumulative_yield}%</Text></Text>
                      <Text style={{ marginLeft: 12 }}>最大损失：<Text type="danger">{yieldData.summary.max_loss_stage}</Text></Text>
                    </div>
                  )}
                </Card>
              )}

              {/* ── 黄金批次 ── */}
              {goldenData?.reference && (
                <Card size="small" style={{ marginTop: 16 }} title={<Space><span>🏆 黄金批次</span>
                  <Select size="small" value={goldenScore} onChange={setGoldenScore} style={{ width: 130 }}
                    options={[{ value: 'stability', label: '🎯 操作稳定性' }, { value: 'quality', label: '⚖️ 产量+质量' }, { value: 'filtered', label: '📊 纯收率' }]} />
                </Space>}>
                  <div style={{ fontSize: 11 }}>
                    <div style={{ display: 'flex', marginBottom: 1, gap: 4 }}>
                      <div style={{ width: 80, flexShrink: 0 }} />
                      <div style={{ flex: 1 }} />
                      <div style={{ width: 140, flexShrink: 0, display: 'flex', justifyContent: 'space-between', color: '#bbb' }}>
                        <span>min</span><span>均值</span><span>max</span>
                      </div>
                    </div>
                    {Object.entries(goldenData.reference).map(([key, ref]: any) => {
                      const range = ref.max - ref.min || 0
                      const leftPct = range === 0 ? 50 : ((ref.avg - ref.min) / range) * 100
                      const barColor = range / (ref.avg || 1) < 0.15 ? '#fa8c16' : '#91caff'
                      return (
                        <div key={key} style={{ display: 'flex', alignItems: 'center', marginBottom: 2, gap: 4 }}>
                          <div style={{ width: 80, textAlign: 'right', color: '#999', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ref.label}</div>
                          <div style={{ flex: 1, position: 'relative', height: 14 }}>
                            <div style={{ position: 'absolute', left: 0, right: 0, top: 5, height: 4, borderRadius: 2, background: '#f0f0f0' }} />
                            <div style={{ position: 'absolute', left: `${leftPct}%`, top: 1, width: 6, height: 12, borderRadius: 3, background: barColor, transform: 'translateX(-50%)' }} />
                          </div>
                          <div style={{ width: 140, flexShrink: 0, display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary" style={{ fontSize: 10 }}>{ref.min}</Text>
                            <Text strong style={{ fontSize: 10, color: barColor }}>{ref.avg}</Text>
                            <Text type="secondary" style={{ fontSize: 10 }}>{ref.max}</Text>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px dashed #e8e8e8', fontSize: 10, color: '#bbb', lineHeight: 1.5 }}>
                    💡 近3个月最优5批的参数范围，柱状图圆点为均值，橙色窗口需严控。供参考，非强制标准。
                  </div>
                </Card>
              )}
            </Col>

            {/* 右侧：批次对比诊断 */}
            <Col span={12} style={{ position: 'relative' }}>
              <Card size="small" title="📡 批次对比诊断"
                extra={<Space.Compact>
                  <Input size="small" placeholder="发酵罐号" value={compareBatch}
                    onChange={e => setCompareBatch(e.target.value)} onPressEnter={doCompare} style={{ width: 140 }} />
                  <Button size="small" type="primary" loading={compareLoading} onClick={doCompare}>对比</Button>
                </Space.Compact>}
                styles={{ body: { position: 'absolute', top: 42, bottom: 0, left: 0, right: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' } }}
                style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, display: 'flex', flexDirection: 'column' }}>
                {compareLoading ? <Spin /> :
                 compareData?.error ? <Text type="secondary">{compareData.error}</Text> :
                 compareData?.stages ? (
                  <div style={{ flex: 1, overflow: 'auto', fontSize: 12 }}>
                    {Object.entries(compareData.stages).map(([stageName, params]: any) => (
                      <Card key={stageName} size="small" className="mb-2" title={stageName}
                        styles={{ header: { fontSize: 12, fontWeight: 500, background: '#fafafa' } }}>
                        {params.map((p: any) => {
                          const sevColors: any = { normal: '#52c41a', warn: '#fa8c16', danger: '#f5222d' }
                          const dirLabels: any = { high: '偏高', low: '偏低', normal: '正常' }
                          return (
                            <div key={p.label} style={{ marginBottom: 6 }}>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <Text style={{ fontSize: 11 }}>{p.label}</Text>
                                <Space size={4}>
                                  <Text strong>{p.value}</Text>
                                  {p.golden_avg != null && <Text type="secondary" style={{ fontSize: 10 }}>黄金 {p.golden_avg}</Text>}
                                  {p.deviation !== undefined && (
                                    <Tag color={sevColors[p.severity]} style={{ fontSize: 10, margin: 0 }}>
                                      {dirLabels[p.direction]} {Math.abs(p.deviation)}%
                                    </Tag>
                                  )}
                                </Space>
                              </div>
                              {p.suggestion && (
                                <details style={{ marginTop: 4, cursor: 'pointer' }}>
                                  <summary style={{ fontSize: 11, color: '#1677ff', padding: '4px 0' }}>💡 展开纠正建议（偏离 {Math.abs(p.deviation)}%）</summary>
                                  <div style={{ padding: '6px 8px', background: '#fffbe6', borderRadius: 4, fontSize: 11, lineHeight: 1.5 }}>
                                    <div>❌ {p.suggestion.happened}</div>
                                    <div style={{ color: '#1677ff' }}>🔧 {p.suggestion.remedy}</div>
                                    <div style={{ color: '#52c41a' }}>📉 {p.suggestion.impact}</div>
                                    <div style={{ color: '#999' }}>🛡 {p.suggestion.prevent}</div>
                                  </div>
                                </details>
                              )}
                            </div>
                          )
                        })}
                      </Card>
                    ))}
                  </div>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>输入发酵罐号（如 FA-EX25316），与黄金批次参数对比诊断</Text>
                )}
              </Card>
            </Col>
          </Row>

        </>
      )}

      {/* ═══════════ 车间工段 ═══════════ */}
      {activeTab === 'workshop' && (
        <>
          <Title level={5} className="mb-4">🏭 车间生产控制台 — 请选择生产工段</Title>
          <Row gutter={[16, 16]}>
            {STAGES.map(s => {
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
