'use client'
// 全链路追溯页面 — DR 多拉菌素批次血链横向流程图 + 收率递推 + 断链标注 + 分析面板
// 数据源：/api/v1/production/dr（六工段表隐式关联，无 batch_lineage 血链表）

import { useEffect, useState, useCallback, useRef, Suspense } from 'react'
import {
  Button, Input, Space, Card, Typography, App, Tag, Tabs, Table, Progress, Spin, Empty, Row, Col, Select, Tooltip
} from 'antd'
import {
  ArrowLeftOutlined, SearchOutlined, NodeIndexOutlined,
  ExperimentOutlined, FilterOutlined, BulbOutlined, CalculatorOutlined,
  CheckCircleOutlined, ArrowRightOutlined, DownloadOutlined, TrophyOutlined, ReloadOutlined, QuestionCircleOutlined
} from '@ant-design/icons'
import { useRouter, useSearchParams } from 'next/navigation'
import ReactECharts from 'echarts-for-react'
import { toPng } from 'html-to-image'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/dr'

const STAGES = [
  { key: 'crude', label: '过滤萃取', path: '/production/batches/workshop/201-3/crude-extraction' },
  { key: 'extraction', label: '层析及一次结晶岗位', path: '/production/batches/workshop/201-3/extraction' },
  { key: 'refinement', label: 'DR二次精制', path: '/production/batches/workshop/201-3/dr-refinement' },
  { key: 'blending', label: '二次精制', path: '/production/batches/workshop/201-3/blending' },
  { key: 'qc', label: '三次精制', path: '/production/batches/workshop/201-3/qc-inspection' },
  { key: 'ba', label: '四次精品', path: '/production/batches/workshop/201-3/butyl-acetate' },
  { key: 'traceability', label: '全链路追溯', path: '/production/batches/workshop/201-3/traceability', active: true },
]

// ── DR 工段颜色/图标映射 ──
const STAGE_CONFIG: Record<string, { color: string; icon: React.ReactNode; bg: string; label: string }> = {
  fermentation: { color: '#52c41a', bg: '#f6ffed', icon: <ExperimentOutlined />, label: '发酵批' },
  extraction: { color: '#1890ff', bg: '#e6f7ff', icon: <FilterOutlined />, label: '萃取批' },
  chromatography: { color: '#722ed1', bg: '#f9f0ff', icon: <FilterOutlined />, label: '层析及一次结晶' },
  first_refinement: { color: '#fa8c16', bg: '#fff7e6', icon: <BulbOutlined />, label: '一次精制' },
  second_refinement: { color: '#eb2f96', bg: '#fff0f6', icon: <CalculatorOutlined />, label: '二次精制' },
  third_refinement: { color: '#fa541c', bg: '#fff2e8', icon: <CheckCircleOutlined />, label: '三次精制' },
  fourth_refinement: { color: '#13c2c2', bg: '#e6fffb', icon: <TrophyOutlined />, label: '四次精制' },
  recovery: { color: '#999', bg: '#f5f5f5', icon: <ReloadOutlined />, label: '回收粉/母液' },
}

// ── 流程图节点组件 ──
function FlowNode({ node, isTarget }: { node: any; isTarget: boolean }) {
  const cfg = STAGE_CONFIG[node.stage] || { color: '#999', bg: '#f5f5f5', icon: null }
  const isSib = node.is_sibling
  // 投入明细（混批展开式）：全部兄弟批 + 投入合计 + 收率对账
  const feeds = node.feeds || []
  const showFeeds = feeds.length > 1
  const inputTotal = node.input_total || 0
  const outQty = node.quantity != null && node.quantity > 0 ? Number(node.quantity) : null
  const calcYr = showFeeds && inputTotal > 0 && outQty != null ? outQty / inputTotal * 100 : null
  const storedYr = node.yield_rate != null ? Number(node.yield_rate) : null
  const yieldDiff = calcYr != null && storedYr != null ? Math.abs(calcYr - storedYr) : null
  const yieldClosed = yieldDiff != null && yieldDiff < 1
  const showYrTag = node.yield_rate != null && !node.broken && !/(收率|%)/.test(node.detail || '')

  return (
    <div data-stage={node.stage} data-batch={node.batch_no} style={{
      display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
      minWidth: 150, maxWidth: 190, flexShrink: 0, opacity: 1,
    }}>
      <Card
        size="small"
        style={{
          border: node.broken ? '2px solid #ff4d4f' : isTarget ? `2px solid ${cfg.color}` : isSib ? `1px dashed ${cfg.color}60` : `1px solid ${cfg.color}40`,
          backgroundColor: node.broken ? '#fff1f0' : isTarget ? cfg.bg : isSib ? '#fafafa' : '#fff',
          borderRadius: 8, width: '100%',
        }}
        bodyStyle={{ padding: '10px 12px' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ color: node.broken ? '#ff4d4f' : cfg.color, fontSize: 16 }}>{cfg.icon}</span>
          <Text strong style={{ fontSize: 12, color: node.broken ? '#ff4d4f' : cfg.color }}>
            {node.broken ? '⚠ ' : ''}{node.label}
          </Text>
        </div>
        <Tag color={node.broken ? 'red' : cfg.color} style={{ marginBottom: 4, fontSize: 11 }}>{node.batch_no}</Tag>
        {isSib && (
          <Tag color="blue" style={{ marginBottom: 4, fontSize: 10 }}>同源</Tag>
        )}
        {node.detail && (
          <div style={{ fontSize: 11, color: '#666', lineHeight: '16px' }}>{node.detail}</div>
        )}
        {/* 本段损耗（精制/干燥段：投入折纯 − 产出折纯/干粉） */}
        {node.loss_kg != null && node.loss_rate != null && (
          <div style={{
            marginTop: 6, padding: '4px 6px', borderRadius: 4, fontSize: 11, lineHeight: '16px',
            background: node.loss_level === 'red' ? '#fff1f0' : node.loss_level === 'yellow' ? '#fffbe6' : '#f6ffed',
            border: node.loss_level === 'red' ? '1px solid #ffccc7' : node.loss_level === 'yellow' ? '1px solid #ffe58f' : '1px solid #b7eb8f',
            color: node.loss_level === 'red' ? '#cf1322' : node.loss_level === 'yellow' ? '#d46b08' : '#389e0d',
          }}>
            <span style={{ fontWeight: 600 }}>本段损耗 {Number(node.loss_kg).toFixed(2)}kg</span>
            <span style={{ marginLeft: 6 }}>
              {Number(node.loss_rate).toFixed(1)}%
              {node.stage === 'fourth_refinement' ? '（干粉口径）' : ''}
            </span>
            <Tooltip title={node.stage === 'fourth_refinement' ? '损耗 = 投入折纯 − 产出干粉（四次精制为干粉口径）' : '损耗 = 投入折纯 − 产出折纯'}>
              <QuestionCircleOutlined style={{ marginLeft: 5, fontSize: 11, cursor: 'help' }} />
            </Tooltip>
          </div>
        )}
        {/* 损耗去向明细（母液带走/回收粉/其他；精制段有记录或损耗时显示） */}
        {node.loss_breakdown && (node.loss_breakdown.recorded || node.loss_kg != null) && (
          <div style={{
            marginTop: 6, padding: '3px 6px', borderRadius: 4, fontSize: 10, lineHeight: '15px',
            background: '#fafafa', border: '1px solid #f0f0f0', color: '#888',
          }}>
            {node.loss_breakdown.recorded ? (
              <div>
                <span style={{ color: '#666' }}>损耗去向</span>
                {node.loss_breakdown.mother_liquor_kg != null && (
                  <span style={{ marginLeft: 6 }}>母液带走 {node.loss_breakdown.mother_liquor_kg}kg</span>
                )}
                {node.loss_breakdown.recovery_powder_kg != null && (
                  <span style={{ marginLeft: 6 }}>回收粉 {node.loss_breakdown.recovery_powder_kg}kg</span>
                )}
                {node.loss_breakdown.other_kg != null && (
                  <span style={{ marginLeft: 6 }}>其他 {node.loss_breakdown.other_kg}kg</span>
                )}
              </div>
            ) : (
              <span>损耗去向未录入（表无母液/回收粉记录）</span>
            )}
          </div>
        )}
        {/* 投入明细（混批展开式）：全部兄弟批 + 投入合计 + 收率对账 */}
        {showFeeds && (
          <div style={{ marginTop: 6, borderTop: '1px dashed #e8e8e8', paddingTop: 6, fontSize: 11, color: '#666' }}>
            <div style={{ fontWeight: 500, marginBottom: 2 }}>投入 {feeds.length} 批</div>
            {feeds.map((f: any) => (
              <div key={f.batch_no} style={{ display: 'flex', justifyContent: 'space-between', lineHeight: '18px' }}>
                <span>{f.label ? `${f.label} ${f.batch_no}` : f.batch_no}</span>
                {f.qty > 0 && <span>{f.qty.toFixed(2)}kg</span>}
              </div>
            ))}
            {inputTotal > 0 && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #f0f0f0', marginTop: 2, paddingTop: 2, fontWeight: 600 }}>
                  <span>投入合计</span><span>{inputTotal.toFixed(2)}kg</span>
                </div>
                {outQty != null && (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                      <span>产出</span><span>{outQty.toFixed(2)}kg</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2, color: yieldClosed ? '#52c41a' : '#fa8c16', fontWeight: 500 }}>
                      <span>对账收率</span>
                      <span>
                        {calcYr?.toFixed(1)}%
                        {yieldClosed
                          ? ' ✓ 对上了'
                          : storedYr != null
                            ? `（表存 ${storedYr.toFixed(1)}%${node.stage === 'fourth_refinement' ? '，干粉口径' : ''}）`
                            : ''}
                      </span>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        )}
        {showYrTag && (
          <div style={{ marginTop: 4 }}>
            <Tag color={node.yield_rate >= 90 ? 'green' : node.yield_rate >= 80 ? 'orange' : 'red'} style={{ fontSize: 11 }}>
              yr {Number(node.yield_rate).toFixed(1)}%
            </Tag>
          </div>
        )}
        {node.broken && node.broken_reason && (
          <div style={{ marginTop: 4 }}>
            <Tag color="red" style={{ fontSize: 10, whiteSpace: 'normal', height: 'auto', lineHeight: '16px' }}>
              {node.broken_reason}
            </Tag>
          </div>
        )}
        {node.connects_to && (
          <div style={{ marginTop: 4 }}>
            <Tag color="geekblue" style={{ fontSize: 10, borderStyle: 'dashed' }}>
              → {node.connects_to}
            </Tag>
          </div>
        )}
      </Card>
    </div>
  )
}

// ── 箭头连接线 ──
function ArrowConnector() {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: 50, flexShrink: 0, color: '#bbb', fontSize: 20, paddingTop: 10,
    }}>
      <ArrowRightOutlined />
    </div>
  )
}

// ── 按工段分组的横向流程图 ──
function groupBySib(nodes: any[]) {
  // 按 sib_group 把同源节点聚成组（连续同组归一段），其余单个成组
  const groups: { group: string; nodes: any[] }[] = []
  for (const n of nodes) {
    const g = n.sib_group || ''
    const last = groups[groups.length - 1]
    if (g && last && last.group === g) last.nodes.push(n)
    else groups.push({ group: g, nodes: [n] })
  }
  return groups
}

function StageFlowChart({ stages, targetBatch, targetStage }: { stages: any[]; targetBatch: string; targetStage: string }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [sibLines, setSibLines] = useState<any[]>([])

  // 跨列"同源"虚线：从源头节点（如发酵批 DR-24002）→ 同源组左侧竖虚线，表达"这几个兄弟源自哪个批"
  useEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return
    const draw = () => {
      const iRect = wrap.getBoundingClientRect()
      const lines: any[] = []
      for (const sg of stages || []) {
        for (const g of groupBySib(sg.nodes || [])) {
          if (!g.group) continue
          const groupEl = wrap.querySelector(`[data-sibgroup="${g.group}"]`) as HTMLElement | null
          if (!groupEl) continue                              // 组框不在视野跳过
          const gr = groupEl.getBoundingClientRect()
          // 单源头逐批画线；多源头（含顿号）各源头 → 组左缘中点
          for (const srcBatch of g.group.split('、')) {
            const sourceEl = wrap.querySelector(`[data-batch="${srcBatch}"]`) as HTMLElement | null
            if (!sourceEl) continue                            // 源头不在视野（如未展开）跳过
            const sr = sourceEl.getBoundingClientRect()
            lines.push({
              x1: sr.right - iRect.left,
              y1: sr.top + sr.height / 2 - iRect.top,
              x2: gr.left - iRect.left,
              y2: gr.top + gr.height / 2 - iRect.top,
            })
          }
        }
      }
      setSibLines(lines)
    }
    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(wrap)
    window.addEventListener('resize', draw)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', draw)
    }
  }, [stages])

  return (
    <div style={{ overflowX: 'auto' }}>
      <div ref={wrapRef} style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', padding: '16px 8px', gap: 0 }}>
        {/* 跨列同源虚线层：源头节点 → 同源组 */}
        <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 1, overflow: 'visible' }}>
          {sibLines.map((l, i) => (
            <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
              stroke="#1890ff" strokeWidth={1.5} strokeDasharray="5 4" />
          ))}
        </svg>
        {stages.map((sg: any, sgIdx: number) => (
          <span key={sg.stage} style={{ display: 'inline-flex', alignItems: 'flex-start' }}>
            {sgIdx > 0 && <ArrowConnector />}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 140 }}>
              <div style={{ textAlign: 'center', marginBottom: 4 }}>
                <Tag color={(STAGE_CONFIG[sg.stage] || {}).color || '#999'} style={{ fontSize: 11 }}>
                  {sg.label}
                </Tag>
              </div>
              {/* 同工段节点：同源组蓝竖虚线串联 + "同源"标签，源头经 SVG 虚线跨列连入 */}
              {groupBySib(sg.nodes).map((g, gi) => (
                <div key={`${sg.stage}-g${gi}`} data-sibgroup={g.group} style={{
                  display: 'flex', flexDirection: 'column', gap: 6,
                  ...(g.group ? { borderLeft: '3px dashed #1890ff', paddingLeft: 8, marginLeft: 2 } : {}),
                }}>
                  {g.group && (
                    <div style={{
                      alignSelf: 'flex-start', background: '#e6f7ff', color: '#1890ff',
                      borderRadius: 3, padding: '1px 6px', fontSize: 10, fontWeight: 500,
                    }}>
                      同源 {g.group}
                    </div>
                  )}
                  {g.nodes.map((node: any) => (
                    <FlowNode key={node.batch_no} node={node}
                      isTarget={node.batch_no === targetBatch && node.stage === targetStage} />
                  ))}
                </div>
              ))}
            </div>
          </span>
        ))}
      </div>
    </div>
  )
}

// ── 累积收率递推条（取每工段第一条节点） ──
function CumulativeYieldBar({ stages }: { stages: any[] }) {
  // 按工段顺序取每条第一个有收率的节点
  const chain: { stage: string; label: string; yr: number }[] = []
  for (const sg of stages) {
    for (const n of sg.nodes) {
      if (n.yield_rate != null && n.yield_rate > 0) {
        chain.push({ stage: sg.stage, label: sg.label, yr: Number(n.yield_rate) })
        break
      }
    }
  }
  if (chain.length === 0) return null

  let cumulative = 100
  return (
    <Card size="small" title="累计收率递推（主线）" style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'wrap' }}>
        <Tag color="blue" style={{ fontSize: 12 }}>100%</Tag>
        <ArrowRightOutlined style={{ color: '#bbb', fontSize: 12 }} />
        {chain.map((c, i) => {
          cumulative *= c.yr / 100
          return (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              <Tag color={c.yr >= 90 ? 'green' : c.yr >= 80 ? 'orange' : 'red'} style={{ fontSize: 12 }}>
                {c.label}: {c.yr.toFixed(1)}%
              </Tag>
              <ArrowRightOutlined style={{ color: '#bbb', fontSize: 12 }} />
              <Tag color="blue" style={{ fontSize: 12 }}>{cumulative.toFixed(1)}%</Tag>
              {i < chain.length - 1 && <ArrowRightOutlined style={{ color: '#bbb', fontSize: 12 }} />}
            </span>
          )
        })}
      </div>
    </Card>
  )
}

// ── 单批全程损耗漏斗（层析湿粉 → 干粉，逐段对账） ──
const LOSS_COLORS = { green: '#52c41a', yellow: '#faad14', red: '#f5222d' }

function LossFunnelCard({ data }: { data: any }) {
  if (!data || !data.layers || data.layers.length === 0) {
    return (
      <Card size="small" style={{ marginTop: 12, background: '#fffbe6', borderColor: '#ffe58f' }}>
        <Text type="secondary">未找到层析湿粉起点（数据未闭合或非 DR 批次）</Text>
      </Card>
    )
  }
  const layers = data.layers
  // 漏斗各层宽度按产出量缩放（层析湿粉为最宽基准）
  const maxOut = Math.max(...layers.map((l: any) => l.output_pure || 0))
  return (
    <Card size="small" title={`全程损耗漏斗 · ${data.target_batch}`} style={{ marginTop: 12 }}>
      <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>
        {data.overall_yield != null && (
          <Text strong style={{ color: LOSS_COLORS[data.overall_yield >= 95 ? 'green' : data.overall_yield >= 85 ? 'yellow' : 'red'] }}>
            全程收率 {data.overall_yield}%
          </Text>
        )}
        {data.overall_loss != null && (
          <Text style={{ marginLeft: 12 }}>全程损耗 {data.overall_loss}kg</Text>
        )}
        {data.notes?.map((n: string, i: number) => (
          <div key={i} style={{ color: '#fa8c16', marginTop: 4 }}>⚠ {n}</div>
        ))}
      </div>
      {layers.map((l: any, i: number) => {
        const width = maxOut > 0 ? Math.max(8, (l.output_pure || 0) / maxOut * 100) : 8
        const segColor = l.segment_yield == null ? '#999'
          : l.segment_yield >= 95 ? '#52c41a' : l.segment_yield >= 85 ? '#faad14' : '#f5222d'
        return (
          <div key={l.stage} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
              <Text strong>{i + 1}. {l.label} <Text type="secondary">({l.batch_count}批)</Text></Text>
              {l.segment_yield != null ? (
                <Text style={{ color: segColor, fontWeight: 600 }}>
                  段收率 {l.segment_yield}% {l.segment_loss != null && <Text type="secondary">损耗 {l.segment_loss}kg</Text>}
                </Text>
              ) : <Text type="secondary">起点</Text>}
            </div>
            <div style={{
              width: `${width}%`, background: l.stage === 'fourth_refinement' ? '#e6fffb' : l.stage === 'chromatography' ? '#f6ffed' : '#f0f0f0',
              border: '1px solid #d9d9d9', borderRadius: 4, padding: '2px 8px', fontSize: 11, color: '#666',
            }}>
              产出 {l.output_pure?.toFixed(2)}kg
              {l.input_pure != null && <span style={{ color: '#999' }}>（投入 {l.input_pure.toFixed(2)}kg）</span>}
              {l.note && <span style={{ marginLeft: 6, color: '#fa8c16' }}>· {l.note}</span>}
            </div>
          </div>
        )
      })}
    </Card>
  )
}

// ── 车间损耗统计（按工段×月平均收率 + 未闭合投料） ──
function LossStatsPanel({ data }: { data: any }) {
  const months = data?.by_segment_month || []
  const unclosed = data?.unclosed || []

  // 按工段分组
  const segKeys = ['second_refinement', 'third_refinement', 'fourth_refinement']
  const segNames: Record<string, string> = {
    second_refinement: '二次精制', third_refinement: '三次精制', fourth_refinement: '四次精制（干粉）',
  }
  const monthsList = [...new Set(months.map((m: any) => m.year_month))].sort()

  // 全链趋势：取三个月以上数据画折线
  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: segKeys.map((k) => segNames[k]), top: 0 },
    grid: { left: 10, right: 10, bottom: 0, top: 30, containLabel: true },
    xAxis: { type: 'category', data: monthsList },
    yAxis: { type: 'value', name: '平均收率(%)' },
    series: segKeys.map((k) => ({
      name: segNames[k], type: 'line', connectNulls: true,
      data: monthsList.map((mo) => {
        const it = months.find((m: any) => m.stage === k && m.year_month === mo)
        return it ? it.avg_yield : null
      }),
    })),
  }

  return (
    <div>
      <Title level={5}>DR 精制工段 · 按月平均收率（存小数×100）</Title>
      <Row gutter={16}>
        <Col span={14}>
          <Table
            dataSource={months}
            rowKey={(r: any) => `${r.stage}-${r.year_month}`}
            pagination={{ pageSize: 12 }}
            size="small"
            columns={[
              { title: '工段', dataIndex: 'stage', key: 'stage', width: 120,
                render: (v: string) => <Tag>{segNames[v] || v}</Tag> },
              { title: '月份', dataIndex: 'year_month', key: 'year_month', width: 90 },
              { title: '批次', dataIndex: 'count', key: 'count', width: 60 },
              { title: '平均收率', dataIndex: 'avg_yield', key: 'avg_yield', width: 90,
                render: (v: number) => (
                  <Text strong style={{ color: v >= 90 ? '#52c41a' : v >= 80 ? '#faad14' : '#f5222d' }}>
                    {v.toFixed(1)}%
                  </Text>
                ) },
              { title: 'Min', dataIndex: 'min_yield', key: 'min_yield', width: 60 },
              { title: 'Max', dataIndex: 'max_yield', key: 'max_yield', width: 60 },
            ]}
          />
        </Col>
        <Col span={10}>
          <Card size="small" title="收率趋势（逐月）">
            <ReactECharts option={trendOption} style={{ height: 320 }} />
          </Card>
        </Col>
      </Row>

      <Title level={5} style={{ marginTop: 16 }}>未闭合投料（上游查不到 → 损耗无法对账）</Title>
      {unclosed.length === 0 ? (
        <Text type="secondary">无未闭合投料，链上数据全部闭合 ✓</Text>
      ) : (
        <Table
          dataSource={unclosed}
          rowKey={(r: any) => `${r.stage}-${r.batch_no}-${r.feed_batch_no}`}
          pagination={{ pageSize: 10 }}
          size="small"
          columns={[
            { title: '工段', dataIndex: 'stage', key: 'stage', width: 100,
              render: (v: string) => <Tag color="orange">{segNames[v] || v}</Tag> },
            { title: '批次号', dataIndex: 'batch_no', key: 'batch_no', width: 150 },
            { title: '投料', dataIndex: 'feed_batch_no', key: 'feed_batch_no', width: 160,
              render: (v: string) => <Tag color="red">{v}</Tag> },
            { title: '原因', dataIndex: 'reason', key: 'reason' },
          ]}
        />
      )}
    </div>
  )
}

export default function TraceabilityPageWrapper() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><Spin size="large" /></div>}>
      <TraceabilityPage />
    </Suspense>
  )
}

function TraceabilityPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { message } = App.useApp()

  // URL 参数自动追溯
  const urlStage = searchParams.get('stage') || ''
  const urlBatch = searchParams.get('batch_no') || ''

  const [stage, setStage] = useState<string>(urlStage || 'second_refinement')
  const [batchNo, setBatchNo] = useState(urlBatch)
  const [loading, setLoading] = useState(false)
  const [traceData, setTraceData] = useState<any>(null)
  const [funnelData, setFunnelData] = useState<any>(null)
  const [distData, setDistData] = useState<any[]>([])
  const [reuseData, setReuseData] = useState<any[]>([])
  const [coverageData, setCoverageData] = useState<any>(null)
  const [lossStatsData, setLossStatsData] = useState<any>(null)

  const flowRef = useRef<HTMLDivElement>(null)

  // DR 工段下拉（追溯目标工段；DR-xxx 同名歧义时用于消歧）
  const STAGE_OPTIONS = [
    { value: 'fermentation', label: '发酵批' },
    { value: 'extraction', label: '萃取批' },
    { value: 'chromatography', label: '层析及一次结晶' },
    { value: 'first_refinement', label: '一次精制' },
    { value: 'second_refinement', label: '二次精制' },
    { value: 'third_refinement', label: '三次精制' },
    { value: 'fourth_refinement', label: '四次精制' },
  ]

  // ── 全链路追溯 ──
  const doTrace = useCallback(async () => {
    if (!batchNo.trim()) return
    setLoading(true)
    try {
      const [traceR, funnelR] = await Promise.all([
        fetch(`${API}${BASE}/lineage/trace?stage=${stage}&batch_no=${encodeURIComponent(batchNo.trim())}`),
        fetch(`${API}${BASE}/lineage/loss-funnel?stage=${stage}&batch_no=${encodeURIComponent(batchNo.trim())}`),
      ])
      const [traceJ, funnelJ] = await Promise.all([traceR.json(), funnelR.json()])
      if (traceJ.code === 200) {
        setTraceData(traceJ.data)
      } else {
        message.error(traceJ.message || '追溯失败')
      }
      if (funnelJ.code === 200) setFunnelData(funnelJ.data)
    } catch {
      message.error('网络错误，请检查服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [batchNo, stage, message])

  const exportFlow = useCallback(async () => {
    if (!flowRef.current) return
    try {
      const dataUrl = await toPng(flowRef.current, { backgroundColor: '#fff', pixelRatio: 2 })
      const a = document.createElement('a'); a.href = dataUrl
      a.download = `追溯_DR_${batchNo}_${new Date().toISOString().slice(0, 10)}.png`; a.click()
    } catch (e) { message.error('导出失败') }
  }, [batchNo, message])

  // ── URL 参数自动追溯 ──
  useEffect(() => {
    if (urlStage && urlBatch) {
      doTrace() // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── 加载分析数据 ──
  const loadAnalytics = useCallback(async () => {
    try {
      const [distR, reuseR, covR, lossR] = await Promise.all([
        fetch(`${API}${BASE}/lineage/yield-distribution`),
        fetch(`${API}${BASE}/lineage/material-reuse`),
        fetch(`${API}${BASE}/lineage/coverage`),
        fetch(`${API}${BASE}/lineage/loss-stats`),
      ])
      const [distJ, reuseJ, covJ, lossJ] = await Promise.all([distR.json(), reuseR.json(), covR.json(), lossR.json()])
      if (distJ.code === 200) setDistData(distJ.data)
      if (reuseJ.code === 200) setReuseData(reuseJ.data)
      if (covJ.code === 200) setCoverageData(covJ.data)
      if (lossJ.code === 200) setLossStatsData(lossJ.data)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadAnalytics() }, [loadAnalytics]) // eslint-disable-line react-hooks/set-state-in-effect

  // ── 工段均值（层析节点收率为结晶收率，对比结晶均值）──
  const distMean = (stageKey: string): number | null => {
    const key = stageKey === 'chromatography' ? 'crystallization' : stageKey
    return distData.find((d: any) => d.stage === key)?.mean ?? null
  }

  // ── 收率分布 ECharts 配置 ──
  const yieldBoxOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Min', 'Q1', '中位', '均值', 'Q3', 'Max'], top: 0 },
    grid: { left: 10, right: 10, bottom: 0, top: 25, containLabel: true },
    xAxis: { type: 'category', data: distData.map((d: any) => d.label) },
    yAxis: { type: 'value', name: '收率(%)' },
    series: [
      { name: 'Min', type: 'bar', data: distData.map((d: any) => d.min), itemStyle: { color: '#91d5ff' } },
      { name: 'Q1', type: 'bar', data: distData.map((d: any) => d.q1), itemStyle: { color: '#69c0ff' } },
      { name: '中位', type: 'bar', data: distData.map((d: any) => d.median), itemStyle: { color: '#1890ff' } },
      { name: '均值', type: 'bar', data: distData.map((d: any) => d.mean), itemStyle: { color: '#096dd9' } },
      { name: 'Q3', type: 'bar', data: distData.map((d: any) => d.q3), itemStyle: { color: '#0050b3' } },
      { name: 'Max', type: 'bar', data: distData.map((d: any) => d.max), itemStyle: { color: '#003a8c' } },
    ],
  }

  // ── 异常计数柱状图 ──
  const anomalyOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['<80%', '>110%'], top: 0 },
    grid: { left: 10, right: 10, bottom: 0, top: 25, containLabel: true },
    xAxis: { type: 'category', data: distData.map((d: any) => d.label) },
    yAxis: { type: 'value', name: '批次数量' },
    series: [
      { name: '<80%', type: 'bar', data: distData.map((d: any) => d.below_80), itemStyle: { color: '#ff7875' } },
      { name: '>110%', type: 'bar', data: distData.map((d: any) => d.above_110), itemStyle: { color: '#ff4d4f' } },
    ],
  }

  // ── 物料复用表格列 ──
  const reuseColumns = [
    { title: '来源工段', dataIndex: 'upstream_type', key: 'upstream_type', width: 100,
      render: (v: string) => <Tag>{STAGE_CONFIG[v]?.label || v}</Tag> },
    { title: '批次号', dataIndex: 'upstream_batch', key: 'upstream_batch', width: 160 },
    { title: '复用次数', dataIndex: 'usage_count', key: 'usage_count', width: 80,
      render: (v: number) => <Tag color={v >= 3 ? 'red' : 'orange'}>{v} 次</Tag> },
    { title: '被以下成品复用', dataIndex: 'used_by', key: 'used_by' },
  ]

  // ── 覆盖完整性（DR：分段批数 + 断链统计） ──
  const covSegments = coverageData?.segments || []
  const covBroken = coverageData?.broken || {}
  const maxSegCount = Math.max(1, ...covSegments.map((s: any) => s.count))

  return (
    <div style={{ paddingBottom: 24 }}>
      <style>{`
        .trace-flow-wrap { display: flex; align-items: flex-start; overflow-x: auto; padding: 16px 8px; gap: 0; }
        .trace-flow-wrap::-webkit-scrollbar { height: 6px; }
        .trace-flow-wrap::-webkit-scrollbar-thumb { background: #d9d9d9; border-radius: 3px; }
      `}</style>

      {/* ── 工段导航栏 ── */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          {STAGES.map(s => (
            <Button
              key={s.key}
              type={s.active ? 'primary' : 'default'}
              onClick={() => router.push(s.path)}
            >
              {s.label}
            </Button>
          ))}
        </Space>
      </Card>

      {/* ── 标题栏 ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />}
            onClick={() => router.push('/production/batches/workshop/201-3')}>
            返回车间
          </Button>
          <NodeIndexOutlined style={{ color: '#13c2c2', marginRight: 8 }} />
          全链路批次追溯 · DR 多拉菌素
          <Text type="secondary" style={{ fontSize: 14, marginLeft: 12 }}>六工段血链 · 断链标注 · 收率递推 · 分析面板</Text>
        </Title>
      </div>

      {/* ── 搜索区 ── */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <span style={{ fontSize: 13, color: '#666' }}>工段:</span>
          <Select
            value={stage}
            onChange={setStage}
            options={STAGE_OPTIONS}
            style={{ width: 150 }}
          />
          <span style={{ fontSize: 13, color: '#666' }}>批号:</span>
          <Input
            placeholder="如 DR-F2-24003-1/2"
            value={batchNo}
            onChange={e => setBatchNo(e.target.value)}
            onPressEnter={doTrace}
            style={{ width: 240 }}
            prefix={<SearchOutlined style={{ color: '#bbb' }} />}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={doTrace} loading={loading}>
            追溯
          </Button>
        </Space>
      </Card>

      {/* ── 横向流程图 ── */}
      <Spin spinning={loading}>
        {traceData && traceData.stages && traceData.stages.length > 0 ? (
          <>
            <Card
              size="small"
              ref={flowRef}
              title={
                <span>
                  全链路追溯结果
                  {traceData.max_loss_stage && (
                    <Tag color="red" style={{ marginLeft: 8 }}>
                      最大损失: {STAGE_CONFIG[traceData.max_loss_stage]?.label || traceData.max_loss_stage}
                    </Tag>
                  )}
                  {traceData.cumulative_yield != null && (
                    <Tag color="blue" style={{ marginLeft: 4 }}>
                      累计收率: {traceData.cumulative_yield}%
                    </Tag>
                  )}
                  <Button size="small" icon={<DownloadOutlined />} style={{ marginLeft: 8 }} onClick={exportFlow}>导出图片</Button>
                </span>
              }
            >
              <StageFlowChart
                stages={traceData.stages}
                targetBatch={traceData.target_batch}
                targetStage={traceData.target_stage}
              />
            </Card>
            {/* ── 断链清单 ── */}
            {traceData.broken_links && traceData.broken_links.length > 0 && (
              <Card size="small" style={{ marginTop: 12, borderColor: '#ffccc7', background: '#fff1f0' }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text strong style={{ color: '#cf1322' }}>
                    <ReloadOutlined /> 断链清单（{traceData.broken_links.length} 处）— 投料无源头 / 回收粉标签
                  </Text>
                  <Space wrap>
                    {traceData.broken_links.map((b: any, i: number) => (
                      <Tag key={i} color="red" style={{ fontSize: 11 }}>
                        {b.batch_no}（{b.reason}）
                      </Tag>
                    ))}
                  </Space>
                </Space>
              </Card>
            )}
            <CumulativeYieldBar stages={traceData.stages} />
            {/* ── 全程损耗漏斗（层析湿粉 → 干粉逐段对账） ── */}
            {funnelData && <LossFunnelCard data={funnelData} />}
            {/* ── 本批次 vs 工段均值对比 ── */}
            {distData.length > 0 && (
              <Card size="small" title={`批次 ${traceData.target_batch} 收率 vs 工段均值`} style={{ marginTop: 16 }}>
                <Table
                  dataSource={traceData.stages
                    .filter((sg: any) => sg.nodes.some((n: any) => n.yield_rate != null && !n.broken))
                    .map((sg: any) => {
                      const node = sg.nodes.find((n: any) => n.yield_rate != null && !n.broken)
                      const avg = distMean(sg.stage)
                      return {
                        stage: sg.label,
                        batch_no: node.batch_no,
                        batch_yield: Number(node.yield_rate),
                        avg_yield: avg ?? null,
                        median: distData.find((d: any) => d.stage === (sg.stage === 'chromatography' ? 'crystallization' : sg.stage))?.median ?? null,
                        diff: avg != null ? Number(node.yield_rate) - avg : null,
                      }
                    })}
                  rowKey="stage"
                  pagination={false}
                  size="small"
                  columns={[
                    { title: '工段', dataIndex: 'stage', width: 100 },
                    { title: '批号', dataIndex: 'batch_no', width: 140 },
                    { title: '本批收率', dataIndex: 'batch_yield', width: 90,
                      render: (v: number) => <Text strong>{v.toFixed(1)}%</Text> },
                    { title: '工段均值', dataIndex: 'avg_yield', width: 90,
                      render: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '-' },
                    { title: '工段中位', dataIndex: 'median', width: 90,
                      render: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '-' },
                    { title: '偏差', dataIndex: 'diff', width: 90,
                      render: (v: number | null) => v != null ? (
                        <Tag color={v >= 0 ? 'green' : 'red'}>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</Tag>
                      ) : '-' },
                  ]}
                />
                <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
                  {(() => {
                    const rows = traceData.stages
                      .filter((sg: any) => sg.nodes.some((n: any) => n.yield_rate != null && !n.broken))
                      .map((sg: any) => {
                        const node = sg.nodes.find((n: any) => n.yield_rate != null && !n.broken)
                        const avg = distMean(sg.stage)
                        return { label: sg.label, yr: Number(node.yield_rate), avg }
                      })
                    const belowAvg = rows.filter((r: any) => r.avg != null && r.yr < r.avg)
                    if (belowAvg.length === 0) return '✅ 所有工段收率均不低于均值'
                    return `⚠️ ${belowAvg.map((r: any) => r.label).join('、')} 低于工段均值，累计收率 ${traceData.cumulative_yield}%${traceData.max_loss_stage ? `，最大损失环节: ${STAGE_CONFIG[traceData.max_loss_stage]?.label || traceData.max_loss_stage}` : ''}`
                  })()}
                </div>
              </Card>
            )}
          </>
        ) : (
          !loading && (
            <Card style={{ textAlign: 'center', padding: 60 }}>
              <Empty description="选择工段并输入批号，点击「追溯」查看完整生产链路" />
            </Card>
          )
        )}
      </Spin>

      {/* ── 分析面板 Tabs ── */}
      <Card size="small" style={{ marginTop: 16 }}>
        <Tabs
          defaultActiveKey="yield"
          items={[
            {
              key: 'yield',
              label: '收率分布',
              children: (
                <div>
                  <Title level={5}>DR 六工段收率箱线数据（收率已 ×100 为百分数）</Title>
                  <Table
                    dataSource={distData}
                    rowKey="stage"
                    pagination={false}
                    size="small"
                    columns={[
                      { title: '工段', dataIndex: 'label', key: 'label', width: 100 },
                      { title: '样本数', dataIndex: 'count', key: 'count', width: 70 },
                      { title: 'Min', dataIndex: 'min', key: 'min', width: 60 },
                      { title: 'Q1', dataIndex: 'q1', key: 'q1', width: 60 },
                      { title: '中位', dataIndex: 'median', key: 'median', width: 60,
                        render: (v: number) => <Text strong>{v}</Text> },
                      { title: '均值', dataIndex: 'mean', key: 'mean', width: 60 },
                      { title: 'Q3', dataIndex: 'q3', key: 'q3', width: 60 },
                      { title: 'Max', dataIndex: 'max', key: 'max', width: 60 },
                      {
                        title: '<80%', dataIndex: 'below_80', key: 'below_80', width: 60,
                        render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <Text type="secondary">0</Text>,
                      },
                      {
                        title: '>110%', dataIndex: 'above_110', key: 'above_110', width: 60,
                        render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <Text type="secondary">0</Text>,
                      },
                    ]}
                  />
                  <Row gutter={16} style={{ marginTop: 16 }}>
                    <Col span={12}>
                      <Card size="small" title="收率箱线图">
                        <ReactECharts option={yieldBoxOption} style={{ height: 280 }} />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="异常值统计">
                        <ReactECharts option={anomalyOption} style={{ height: 280 }} />
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'reuse',
              label: '物料复用',
              children: (
                <div>
                  <Title level={5}>被多个下游批次复用的投料（跨批混料 / 回收粉共用）</Title>
                  <Table
                    dataSource={reuseData}
                    rowKey={(r: any) => `${r.upstream_type}-${r.upstream_batch}`}
                    columns={reuseColumns}
                    pagination={{ pageSize: 10 }}
                    size="small"
                  />
                </div>
              ),
            },
            {
              key: 'coverage',
              label: '覆盖完整性',
              children: (
                <div>
                  <Title level={5}>DR 六工段台账覆盖</Title>
                  {covSegments.map((s: any) => (
                    <div key={s.segment} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <Text>{s.segment}</Text>
                        <Text strong>{s.count} 个批号</Text>
                      </div>
                      <Progress percent={Math.round((s.count / maxSegCount) * 100)} showInfo={false}
                        strokeColor="#1890ff" size="small" />
                    </div>
                  ))}

                  <Title level={5} style={{ marginTop: 16 }}>断链清单统计（投料无源头）</Title>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Card size="small" style={{ background: '#fff1f0', borderColor: '#ffccc7' }}>
                        <Text strong style={{ color: '#cf1322' }}>层析投料萃取表查不到</Text>
                        <div style={{ fontSize: 22, fontWeight: 700, color: '#cf1322' }}>
                          {covBroken.extraction_feeds_not_in_extraction?.count ?? 0}
                        </div>
                        <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                          {(covBroken.extraction_feeds_not_in_extraction?.batches || []).slice(0, 6).map((b: string) => (
                            <Tag key={b} color="red" style={{ fontSize: 10, marginBottom: 2 }}>{b}</Tag>
                          ))}
                        </div>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" style={{ background: '#fff1f0', borderColor: '#ffccc7' }}>
                        <Text strong style={{ color: '#cf1322' }}>三次投料二次表查不到（DR-F2）</Text>
                        <div style={{ fontSize: 22, fontWeight: 700, color: '#cf1322' }}>
                          {covBroken.third_feeds_not_in_second?.count ?? 0}
                        </div>
                        <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                          {(covBroken.third_feeds_not_in_second?.batches || []).slice(0, 6).map((b: string) => (
                            <Tag key={b} color="red" style={{ fontSize: 10, marginBottom: 2 }}>{b}</Tag>
                          ))}
                        </div>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" style={{ marginTop: 12, background: '#fff1f0', borderColor: '#ffccc7' }}>
                        <Text strong style={{ color: '#cf1322' }}>四次投料三次表查不到（DR-F3）</Text>
                        <div style={{ fontSize: 22, fontWeight: 700, color: '#cf1322' }}>
                          {covBroken.fourth_feeds_not_in_third?.count ?? 0}
                        </div>
                        <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                          {(covBroken.fourth_feeds_not_in_third?.batches || []).slice(0, 6).map((b: string) => (
                            <Tag key={b} color="red" style={{ fontSize: 10, marginBottom: 2 }}>{b}</Tag>
                          ))}
                        </div>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" style={{ marginTop: 12, background: '#fffbe6', borderColor: '#ffe58f' }}>
                        <Text strong style={{ color: '#d46b08' }}>特殊投料标签（回收粉/母液/重结晶粉）</Text>
                        <div style={{ fontSize: 22, fontWeight: 700, color: '#d46b08' }}>
                          {covBroken.special_feeds?.count ?? 0}
                        </div>
                        <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                          {(covBroken.special_feeds?.batches || []).slice(0, 6).map((b: string) => (
                            <Tag key={b} color="orange" style={{ fontSize: 10, marginBottom: 2 }}>{b}</Tag>
                          ))}
                        </div>
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'loss',
              label: '损耗统计',
              children: <LossStatsPanel data={lossStatsData} />,
            },
          ]}
        />
      </Card>
    </div>
  )
}
