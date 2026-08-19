'use client'
// 全链路追溯页面 — 批次血链表横向流程图 + 收率递推 + 分析面板

import { useEffect, useState, useCallback, useRef, Suspense } from 'react'
import {
  Button, Input, Space, Card, Typography, App, Tag, Tabs, Table, Progress, Spin, Empty, Row, Col, Select, Popover, List
} from 'antd'
import {
  ArrowLeftOutlined, SearchOutlined, NodeIndexOutlined,
  ExperimentOutlined, FilterOutlined, BulbOutlined, CalculatorOutlined,
  CheckCircleOutlined, ArrowRightOutlined, SendOutlined, HistoryOutlined, DownloadOutlined
} from '@ant-design/icons'
import { useRouter, useSearchParams } from 'next/navigation'
import ReactECharts from 'echarts-for-react'
import { toPng } from 'html-to-image'
import BATCH_TYPES from '@/components/production/batchTypes'

const { Title, Text } = Typography
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/mc'

const STAGES = [
  { key: 'crude', label: '粗提', path: '/production/batches/workshop/201-2/crude-extraction' },
  { key: 'extraction', label: '提取', path: '/production/batches/workshop/201-2/extraction' },
  { key: 'refinement', label: 'MC二次精制', path: '/production/batches/workshop/201-2/mc-refinement' },
  { key: 'blending', label: '混粉杂质计算', path: '/production/batches/workshop/201-2/blending' },
  { key: 'qc', label: '混粉入库', path: '/production/batches/workshop/201-2/qc-inspection' },
  { key: 'ba', label: '丁酯盘点', path: '/production/batches/workshop/201-2/butyl-acetate' },
  { key: 'traceability', label: '全链路追溯', path: '/production/batches/workshop/201-2/traceability', active: true },
]

// ── 工段颜色/图标映射 ──
const STAGE_CONFIG: Record<string, { color: string; icon: React.ReactNode; bg: string; label: string }> = {
  fermentation: { color: '#52c41a', bg: '#f6ffed', icon: <ExperimentOutlined />, label: '发酵液' },
  refining: { color: '#1890ff', bg: '#e6f7ff', icon: <FilterOutlined />, label: '提炼放罐' },
  sub_tank: { color: '#13c2c2', bg: '#e6fffb', icon: <ExperimentOutlined />, label: '钠化批号' },
  extraction: { color: '#fa8c16', bg: '#fff7e6', icon: <FilterOutlined />, label: '萃取批号' },
  refinement: { color: '#722ed1', bg: '#f9f0ff', icon: <BulbOutlined />, label: '精制MC-F2' },
  blending: { color: '#eb2f96', bg: '#fff0f6', icon: <CalculatorOutlined />, label: '混粉成品' },
  qc: { color: '#fa541c', bg: '#fff2e8', icon: <CheckCircleOutlined />, label: '入库' },
}

// ── 流程图节点组件 ──
function FlowNode({ node, isTarget }: { node: any; isTarget: boolean }) {
  const cfg = STAGE_CONFIG[node.stage] || { color: '#999', bg: '#f5f5f5', icon: null }
  const isSib = node.is_sibling

  return (
    <div style={{
      display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
      minWidth: 140, maxWidth: 180, flexShrink: 0, opacity: isSib ? 0.65 : 1,
    }}>
      <Card
        size="small"
        style={{
          border: isTarget ? `2px solid ${cfg.color}` : isSib ? `1px dashed ${cfg.color}60` : `1px solid ${cfg.color}40`,
          backgroundColor: isTarget ? cfg.bg : isSib ? '#fafafa' : '#fff',
          borderRadius: 8, width: '100%',
        }}
        bodyStyle={{ padding: '10px 12px' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ color: cfg.color, fontSize: 16 }}>{cfg.icon}</span>
          <Text strong style={{ fontSize: 12, color: cfg.color }}>{node.label}</Text>
        </div>
        <Tag color={cfg.color} style={{ marginBottom: 4, fontSize: 11 }}>{node.batch_no}</Tag>
        {node.detail && (
          <div style={{ fontSize: 11, color: '#666', lineHeight: '16px' }}>{node.detail}</div>
        )}
        {node.yield_rate != null && (
          <div style={{ marginTop: 4 }}>
            <Tag color={node.yield_rate >= 90 ? 'green' : node.yield_rate >= 80 ? 'orange' : 'red'} style={{ fontSize: 11 }}>
              yr {Number(node.yield_rate).toFixed(1)}%
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
function StageFlowChart({ stages, targetBatch, targetStage }: { stages: any[]; targetBatch: string; targetStage: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', overflowX: 'auto', padding: '16px 8px', gap: 0 }}>
      {stages.map((sg: any, sgIdx: number) => {
        const mainNodes = sg.nodes.filter((n: any) => !n.is_sibling)
        const sibNodes = sg.nodes.filter((n: any) => n.is_sibling)
        return (
        <span key={sg.stage} style={{ display: 'inline-flex', alignItems: 'flex-start' }}>
          {sgIdx > 0 && <ArrowConnector />}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 140 }}>
            <div style={{ textAlign: 'center', marginBottom: 4 }}>
              <Tag color={(STAGE_CONFIG[sg.stage] || {}).color || '#999'} style={{ fontSize: 11 }}>
                {sg.label}
              </Tag>
            </div>
            {/* 主线节点 */}
            {mainNodes.map((node: any) => (
              <FlowNode key={node.batch_no} node={node}
                isTarget={node.batch_no === targetBatch && node.stage === targetStage} />
            ))}
            {/* 分割线 + 同级节点 */}
            {sibNodes.length > 0 && (
              <>
                <div style={{ borderTop: '1px dashed #d9d9d9', margin: '2px 4px' }}>
                  <span style={{ fontSize: 10, color: '#999', background: '#fff', padding: '0 4px', position: 'relative', top: -8 }}>同级</span>
                </div>
                {sibNodes.map((node: any) => (
                  <FlowNode key={node.batch_no} node={node} isTarget={false} />
                ))}
              </>
            )}
          </div>
        </span>
      )})}
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

  const [stage, setStage] = useState<string>(urlStage || 'sub_tank')
  const [batchNo, setBatchNo] = useState(urlBatch)
  const [loading, setLoading] = useState(false)
  const [traceData, setTraceData] = useState<any>(null)
  const [distData, setDistData] = useState<any[]>([])
  const [reuseData, setReuseData] = useState<any[]>([])
  const [coverageData, setCoverageData] = useState<any>(null)

  // AI 分析
  const [aiLoading, setAiLoading] = useState(false)
  const [aiResult, setAiResult] = useState<any>(null)
  const [thinkingSteps, setThinkingSteps] = useState<{ step: string; msg: string; done?: boolean }[]>([])
  const [thinkingText, setThinkingText] = useState('')  // LLM 实时输出

  // 追问聊天
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const flowRef = useRef<HTMLDivElement>(null)
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMessages])

  // AI 分析历史
  const [historyRecords, setHistoryRecords] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const loadHistory = useCallback(async () => {
    if (!batchNo.trim()) return
    setHistoryLoading(true); setHistoryRecords([])
    try {
      const r = await fetch(`${API}${BASE}/lineage/ai-history?stage=${stage}&batch_no=${encodeURIComponent(batchNo.trim())}`)
      const json = await r.json()
      if (json.code === 200) setHistoryRecords(json.data.records || [])
    } catch { /* ignore */ }
    finally { setHistoryLoading(false) }
  }, [batchNo, stage])

  // 批号类型下拉选项（12种，含中转类型）
  const STAGE_OPTIONS = [
    { value: 'fermentation', label: '发酵液批号' },
    { value: 'refining', label: '提炼生产批号' },
    { value: 'na_batch', label: '钠化批号' },
    { value: 'crude_product', label: '粗品批号' },
    { value: 'extraction', label: '萃取批号' },
    { value: 'wet_powder', label: '一次精品批号' },
    { value: 'refinement', label: '二次结晶批号' },
    { value: 'single_batch_blend', label: '单批批号(混粉)' },
    { value: 'single_batch_qc', label: '单批批号(入库)' },
    { value: 'blending', label: '混合批号' },
    { value: 'front_batch', label: '前台批号' },
    { value: 'qc', label: '成品后台批号' },
  ]

  // ── 全链路追溯 ──
  const doTrace = useCallback(async () => {
    if (!batchNo.trim()) return
        setLoading(true)
    try {
      const r = await fetch(`${API}${BASE}/lineage/trace?stage=${stage}&batch_no=${encodeURIComponent(batchNo.trim())}`)
      const json = await r.json()
      if (json.code === 200) {
        setTraceData(json.data)
      } else {
        message.error(json.message || '追溯失败')
      }
    } catch {
      message.error('网络错误，请检查服务是否正常运行')
    } finally {
      setLoading(false)
    }
  }, [batchNo, stage, message])

  // ── AI 分析 ──
  const doAiAnalysis = useCallback(async () => {
    if (!batchNo.trim()) return
    setAiLoading(true); setChatMessages([]); setAiResult(null)
    setThinkingSteps([]); setThinkingText('')

    try {
      const r = await fetch(
        `${API}${BASE}/lineage/ai-analysis-stream?stage=${stage}&batch_no=${encodeURIComponent(batchNo.trim())}`,
        { signal: AbortSignal.timeout(240000) }
      )
      const reader = r.body?.getReader()
      if (!reader) throw new Error('No stream')
      const decoder = new TextDecoder()
      let buffer = ''
      let gotResult = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'step') {
              setThinkingSteps(prev => prev.map(s => s.step === data.step ? { ...s, ...data } : s).length
                ? prev.map(s => s.step === data.step ? { ...s, ...data } : s)
                : [...prev, data])
            } else if (data.type === 'token') {
              setThinkingText(prev => prev + data.content)
            } else if (data.type === 'result') {
              gotResult = true
              setAiResult({
                ...data, analysis_text: data.analysis_text,
                causes: data.causes, suggestions: data.suggestions,
                severity: data.severity, summary: data.summary,
                session_id: data.session_id, anomalies: data.anomalies,
              })
            }
          } catch { /* skip malformed */ }
        }
      }
      // 流结束后检查是否收到完整结果
      if (!gotResult) {
        message.error('AI 分析未返回完整结果，请重试')
      }
    } catch {
      message.error('AI 分析失败，请重试')
    } finally {
      setAiLoading(false)
    }
  }, [batchNo, stage, message])

  // ── 追问发送（SSE）──
  const doChatSend = useCallback(async () => {
    const msg = chatInput.trim()
    if (!msg) return
    if (!aiResult?.session_id) {
      message.warning('会话已过期，请重新点击"AI 分析"')
      return
    }
    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', content: msg }, { role: 'assistant', content: '' }])
    setChatSending(true)
    try {
      const r = await fetch(`${API}${BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: aiResult.session_id, message: msg }),
      })
      const reader = r.body?.getReader()
      if (!reader) throw new Error('No stream')
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.token) {
                setChatMessages(prev => {
                  const copy = [...prev]
                  const last = copy[copy.length - 1]
                  if (last && last.role === 'assistant') {
                    copy[copy.length - 1] = { ...last, content: last.content + data.token }
                  }
                  return copy
                })
              }
            } catch {}
          }
        }
      }
    } catch {
      setChatMessages(prev => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last && last.role === 'assistant' && !last.content) {
          copy[copy.length - 1] = { ...last, content: '网络错误，请重试' }
        }
        return copy
      })
    } finally {
      setChatSending(false)
    }
  }, [chatInput, aiResult, message])

  const exportFlow = useCallback(async () => {
    if (!flowRef.current) return
    try {
      const dataUrl = await toPng(flowRef.current, { backgroundColor: '#fff', pixelRatio: 2 })
      const a = document.createElement('a'); a.href = dataUrl
      a.download = `追溯_MC_${batchNo}_${new Date().toISOString().slice(0, 10)}.png`; a.click()
    } catch (e) { message.error('导出失败') }
  }, [batchNo, message])

  // ── URL 参数自动追溯 ──
  useEffect(() => {
    if (urlStage && urlBatch) {
      doTrace()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── 加载分析数据 ──
  const loadAnalytics = useCallback(async () => {
    try {
      const [distR, reuseR, covR] = await Promise.all([
        fetch(`${API}${BASE}/lineage/yield-distribution`),
        fetch(`${API}${BASE}/lineage/material-reuse`),
        fetch(`${API}${BASE}/lineage/coverage`),
      ])
      const [distJ, reuseJ, covJ] = await Promise.all([distR.json(), reuseR.json(), covR.json()])
      if (distJ.code === 200) setDistData(distJ.data)
      if (reuseJ.code === 200) setReuseData(reuseJ.data)
      if (covJ.code === 200) setCoverageData(covJ.data)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadAnalytics() }, [loadAnalytics])

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

  // ── 覆盖完整性 ──
  const covSegments = coverageData?.segments || []

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
            onClick={() => router.push('/production/batches/workshop/201-2')}>
            返回车间
          </Button>
          <NodeIndexOutlined style={{ color: '#eb2f96', marginRight: 8 }} />
          全链路批次追溯
          <Text type="secondary" style={{ fontSize: 14, marginLeft: 12 }}>批次血链表 · 收率递推 · 物料复用</Text>
        </Title>
      </div>

      {/* ── 搜索区 ── */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <span style={{ fontSize: 13, color: '#666' }}>工段:</span>
          <Select
            value={stage}
            onChange={setStage}
            options={BATCH_TYPES}
            style={{ width: 130 }}
          />
          <span style={{ fontSize: 13, color: '#666' }}>批号:</span>
          <Input
            placeholder="输入批号"
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
            <CumulativeYieldBar stages={traceData.stages} />
            {/* ── 本批次 vs 工段均值对比 ── */}
            {distData.length > 0 && (
              <Card size="small" title={`批次 ${traceData.target_batch} 收率 vs 工段均值`} style={{ marginTop: 16 }}>
                <Table
                  dataSource={traceData.stages
                    .filter((sg: any) => sg.nodes.some((n: any) => n.yield_rate != null))
                    .map((sg: any) => {
                      const node = sg.nodes.find((n: any) => n.yield_rate != null)
                      const avg = distData.find((d: any) => d.stage === sg.stage)
                      return {
                        stage: sg.label,
                        batch_no: node.batch_no,
                        batch_yield: Number(node.yield_rate),
                        avg_yield: avg?.mean ?? null,
                        median: avg?.median ?? null,
                        diff: avg ? Number(node.yield_rate) - avg.mean : null,
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
                    const stages = traceData.stages.filter((sg: any) => sg.nodes.some((n: any) => n.yield_rate != null))
                    const belowAvg = stages.filter((sg: any) => {
                      const node = sg.nodes.find((n: any) => n.yield_rate != null)
                      const avg = distData.find((d: any) => d.stage === sg.stage)
                      return avg && Number(node.yield_rate) < avg.mean
                    })
                    if (belowAvg.length === 0) return '✅ 所有工段收率均不低于均值'
                    return `⚠️ ${belowAvg.map((s: any) => s.label).join('、')} 低于工段均值，累计收率 ${traceData.cumulative_yield}%${traceData.max_loss_stage ? `，最大损失环节: ${STAGE_CONFIG[traceData.max_loss_stage]?.label || traceData.max_loss_stage}` : ''}`
                  })()}
                </div>
              </Card>
            )}

            {/* ── AI 分析 ── */}
            <Card size="small" style={{ marginTop: 16 }}>
              <Space>
                <Button
                  type="primary"
                  icon={<BulbOutlined />}
                  onClick={doAiAnalysis}
                  loading={aiLoading}
                >
                  AI 分析
                </Button>
                <Popover
                  trigger="click"
                  onOpenChange={(open) => { if (open) loadHistory() }}
                  placement="bottomLeft"
                  title="分析历史"
                  content={
                    historyLoading ? <Spin size="small" /> :
                    historyRecords.length === 0 ? <Text type="secondary">暂无历史分析</Text> :
                    <div style={{ width: 520, maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
                      <div style={{ display: 'flex', fontWeight: 600, borderBottom: '1px solid #f0f0f0', paddingBottom: 6, marginBottom: 4, color: '#999' }}>
                        <span style={{ width: 56 }}>状态</span>
                        <span style={{ width: 110 }}>日期</span>
                        <span style={{ width: 80 }}>批号名称</span>
                        <span style={{ width: 110 }}>批号</span>
                        <span style={{ flex: 1 }}>分析</span>
                      </div>
                      {historyRecords.map((r: any) => (
                        <div key={r.id} style={{ display: 'flex', alignItems: 'center', padding: '4px 0', cursor: 'pointer', borderBottom: '1px solid #fafafa' }}
                          onClick={() => { setAiResult({...r, analysis_text: null, session_id: r.session_id}); setChatMessages([]) }}>
                          <Tag color={r.severity === 'high' ? 'red' : r.severity === 'medium' ? 'orange' : 'green'} style={{ fontSize: 10, margin: 0, width: 48 }}>
                            {r.severity === 'high' ? '严重' : r.severity === 'medium' ? '中等' : '正常'}
                          </Tag>
                          <Text style={{ width: 110 }} ellipsis>{(r.created_at || '').slice(0, 16)}</Text>
                          <Text style={{ width: 80 }} ellipsis>{r.stage_label || r.stage}</Text>
                          <Text style={{ width: 110 }} ellipsis>{r.batch_no}</Text>
                          <Text style={{ flex: 1, color: '#666' }} ellipsis={{ tooltip: r.summary }}>{r.summary}</Text>
                        </div>
                      ))}
                    </div>
                  }
                >
                  <Button icon={<HistoryOutlined />} size="small">历史记录</Button>
                </Popover>
              </Space>

              {/* 思考过程 — Space 外面，独立块 */}
              {(thinkingSteps.length > 0 || aiLoading) && (
                <div style={{
                  marginTop: 12, padding: '10px 14px', background: '#f9fafb', borderRadius: 8,
                  border: '1px solid #e5e7eb', fontSize: 13, maxWidth: 560,
                }}>
                  <Text strong style={{ fontSize: 12, color: '#6b7280' }}>🤔 思考过程</Text>
                  {thinkingSteps.map((s, i) => (
                    <div key={i} style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>{s.done ? '✅' : '⏳'}</span>
                      <Text style={{ color: s.done ? '#374151' : '#9ca3af', fontSize: 12 }}>{s.msg}</Text>
                    </div>
                  ))}
                  {thinkingText && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ cursor: 'pointer', fontSize: 12, color: '#6b7280' }}>查看模型原始输出</summary>
                      <pre style={{ fontSize: 11, color: '#9ca3af', whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto', margin: '4px 0' }}>
                        {thinkingText}
                      </pre>
                    </details>
                  )}
                </div>
              )}

              <Space>
                {aiResult && (
                  <Button size="small" onClick={() => navigator.clipboard.writeText(aiResult.analysis_text || aiResult.summary)}>
                    复制结果
                  </Button>
                )}
              </Space>
              {aiResult && (
                <div style={{ marginTop: 12 }}>
                  <Row gutter={16}>
                    <Col span={18}>
                      <Text strong style={{ fontSize: 14 }}>
                        {aiResult.severity === 'high' ? '🔴' : aiResult.severity === 'medium' ? '🟡' : '🟢'} {aiResult.summary}
                      </Text>
                    </Col>
                    <Col span={6} style={{ textAlign: 'right' }}>
                      <Tag color={aiResult.severity === 'high' ? 'red' : aiResult.severity === 'medium' ? 'orange' : 'green'}>
                        {aiResult.severity === 'high' ? '严重' : aiResult.severity === 'medium' ? '中等' : '正常'}
                      </Tag>
                    </Col>
                  </Row>

                  {(aiResult.anomalies || []).length > 0 && (
                    <Card size="small" title="异常标记" style={{ marginTop: 8, background: '#fff7e6' }}>
                      {aiResult.anomalies.map((a: any, i: number) => (
                        <Tag key={i} color="warning" style={{ marginBottom: 4 }}>
                          {a.stage} {a.batch_no}: {a.value}% ({a.detail})
                        </Tag>
                      ))}
                    </Card>
                  )}

                  {(aiResult.causes || []).length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text strong>可能原因：</Text>
                      <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                        {aiResult.causes.map((c: string, i: number) => (
                          <li key={i} style={{ fontSize: 13, color: '#666' }}>{c}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {(aiResult.suggestions || []).length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text strong>优化建议：</Text>
                      <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                        {aiResult.suggestions.map((s: string, i: number) => (
                          <li key={i} style={{ fontSize: 13, color: '#1677ff' }}>{s}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {aiResult.analysis_text && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ cursor: 'pointer', color: '#999', fontSize: 12 }}>查看 LLM 原始输出</summary>
                      <pre style={{ fontSize: 11, color: '#999', whiteSpace: 'pre-wrap', marginTop: 4 }}>
                        {aiResult.analysis_text}
                      </pre>
                    </details>
                  )}

                  {/* ── 追问区域 ── */}
                  <div style={{ marginTop: 16, borderTop: '1px dashed #e8e8e8', paddingTop: 12 }}>
                    <Text strong style={{ fontSize: 12, color: '#999' }}>继续追问</Text>
                    <div style={{ marginTop: 8 }}>
                      {chatMessages.map((m, i) => (
                        <div key={i} style={{
                          marginBottom: 8, padding: '6px 10px', borderRadius: 8, fontSize: 13,
                          background: m.role === 'user' ? '#e6f4ff' : '#f6f6f6',
                          maxWidth: '90%', marginLeft: m.role === 'user' ? 'auto' : 0,
                          marginRight: m.role === 'assistant' ? 'auto' : 0,
                        }}>
                          <div style={{ color: m.role === 'user' ? '#1677ff' : '#333', whiteSpace: 'pre-wrap' }}>
                            {m.content || (m.role === 'assistant' && chatSending ? <span style={{ color: '#999' }}>思考中...</span> : '')}
                          </div>
                        </div>
                      ))}
                      <div ref={chatEndRef} />
                    </div>
                    <Space.Compact style={{ width: '100%' }}>
                      <Input
                        size="small"
                        placeholder="继续追问：为什么收率偏低？"
                        value={chatInput}
                        onChange={e => setChatInput(e.target.value)}
                        onPressEnter={doChatSend}
                        disabled={chatSending}
                      />
                      <Button size="small" type="primary" icon={<SendOutlined />} loading={chatSending} onClick={doChatSend} />
                    </Space.Compact>
                  </div>
                </div>
              )}
            </Card>
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
                  <Title level={5}>三工段收率箱线数据</Title>
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
                  <Title level={5}>被多个成品批次复用的物料</Title>
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
                  <Title level={5}>血链表各段关联覆盖</Title>
                  {covSegments.map((s: any) => (
                    <div key={s.segment} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <Text>{s.segment}</Text>
                        <Text strong>{s.count} 条</Text>
                      </div>
                      <Progress percent={Math.min(s.count / 5, 100)} showInfo={false}
                        strokeColor="#1890ff" size="small" />
                    </div>
                  ))}
                  {coverageData && (
                    <Card size="small" style={{ marginTop: 16, backgroundColor: '#f6ffed' }}>
                      <Text>
                        提取段覆盖率: <Text strong style={{ color: '#52c41a' }}>{coverageData.extraction_coverage_pct}%</Text>
                        （{coverageData.extraction_total - coverageData.extraction_missing}/{coverageData.extraction_total} 条已覆盖，
                        <Text type="danger">{coverageData.extraction_missing} 条未覆盖</Text>，可能是旧批号/乱码）
                      </Text>
                    </Card>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
