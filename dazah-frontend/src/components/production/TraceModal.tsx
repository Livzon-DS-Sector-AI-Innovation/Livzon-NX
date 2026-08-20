'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import {Modal, Typography, Tag, Spin, Empty, App, Button, Input, Space, Popover,} from 'antd'
import { SendOutlined, HistoryOutlined, DownloadOutlined } from '@ant-design/icons'

const { Text } = Typography
const API = (p: string) => `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/v1/production${p}`

const COL_X = 180
const ROW_H = 56
const START_Y = 30
const BRANCH_GAP = 16

const STAGE_CFG: Record<string, { color: string }> = {
  fermentation: { color: '#52c41a' }, refining: { color: '#1890ff' },
  sub_tank: { color: '#13c2c2' }, extraction: { color: '#fa8c16' },
  refinement: { color: '#722ed1' }, blending: { color: '#eb2f96' },
  qc: { color: '#fa541c' },
  acidification: { color: '#1890ff' }, decolor1: { color: '#13c2c2' },
  decolor_centrifuge: { color: '#722ed1' },
}

const STAGE_ORDER = ['fermentation', 'refining', 'sub_tank', 'extraction', 'refinement', 'blending', 'qc']

interface StageGroup { stage: string; label: string; nodes: any[]; note?: string }
interface Props {
  stage: string; batchNo: string; onClose: () => void;
  stageConfig?: Record<string, { color: string }>;
  stageOrder?: string[];
  apiPrefix?: string;
}

function buildLayout(stages: StageGroup[], targetBatch: string, targetStage: string, cfg: Record<string, { color: string }>, order: string[]) {
  const nodes: any[] = []; const lines: any[] = []; const notes: any[] = []
  const stageList = stages.filter(s => order.includes(s.stage))
  if (stageList.length === 0) return { nodes, lines, notes }

  const colMap: Record<string, number> = {}
  stageList.forEach((s, i) => { colMap[s.stage] = i })

  let nid = 0

  // 第一阶段：计算每列节点数量（先不分配 y）
  const colHeights: number[] = []
  const colNodes: any[][] = []
  stageList.forEach((sg, col) => {
    const mains = (sg.nodes || []).filter((n: any) => !n.is_sibling)
    const sibs = (sg.nodes || []).filter((n: any) => n.is_sibling)
    colHeights.push(mains.length * ROW_H + (sibs.length > 0 ? BRANCH_GAP + sibs.length * ROW_H : 0))
    colNodes.push([])
  })

  // 第二阶段：计算每列的垂直偏移量以居中于相邻列
  const colOffsets: number[] = []
  for (let col = 0; col < colHeights.length; col++) {
  }

  // 第三阶段：分配 y 坐标
  stageList.forEach((sg, col) => {
    const mains = (sg.nodes || []).filter((n: any) => !n.is_sibling)
    mains.forEach((n: any, row: number) => {
      const isTarget = n.batch_no === targetBatch && sg.stage === targetStage
      nodes.push({
        id: `n${nid++}`, x: col * COL_X + 4, y: START_Y + colOffsets[col] + row * ROW_H, w: 152, h: 52,
        stage: sg.stage, label: sg.label, batch_no: n.batch_no,
        detail: n.detail || '', yield_rate: n.yield_rate, quantity: n.quantity,
        is_target: isTarget, is_sibling: false, connects_to: n.connects_to || '', col, row
      })
    })
  })

  // 同级节点排在同列底部
  stageList.forEach((sg, col) => {
    const mainCount = (sg.nodes || []).filter((n: any) => !n.is_sibling).length
    const sibs = (sg.nodes || []).filter((n: any) => n.is_sibling)
    sibs.forEach((n: any, row: number) => {
      nodes.push({
        id: `n${nid++}`, x: col * COL_X + 4, y: START_Y + colOffsets[col] + mainCount * ROW_H + BRANCH_GAP + row * ROW_H, w: 152, h: 52,
        stage: sg.stage, label: sg.label, batch_no: n.batch_no,
        detail: n.detail || '', yield_rate: n.yield_rate, quantity: n.quantity,
        is_target: false, is_sibling: true, connects_to: n.connects_to || '', col, row: mainCount + row
      })
    })
  })

  // 同列竖线
  for (let col = 0; col < stageList.length; col++) {
    const colNodes = nodes.filter(n => n.col === col).sort((a, b) => a.row - b.row)
    const mains = colNodes.filter(n => !n.is_sibling)
    for (let i = 0; i < mains.length - 1; i++) {
      const a = mains[i]; const b = mains[i + 1]
      lines.push({ x1: a.x + a.w / 2, y1: a.y + a.h, x2: b.x + b.w / 2, y2: b.y, dashed: false, color: '#ccc' })
    }
    const sibs = colNodes.filter(n => n.is_sibling)
    for (let i = 0; i < sibs.length - 1; i++) {
      const a = sibs[i]; const b = sibs[i + 1]
      lines.push({ x1: a.x + a.w / 2, y1: a.y + a.h, x2: b.x + b.w / 2, y2: b.y, dashed: true, color: '#ccc' })
    }
  }

  // 根据节点 connects_to 字段画真实连线
  for (let col = 0; col < stageList.length - 1; col++) {
    const curNodes = nodes.filter(n => n.col === col && !n.is_sibling)
    const nextNodes = nodes.filter(n => n.col === col + 1 && !n.is_sibling)
    const nextMap = new Map(nextNodes.map(n => [n.batch_no, n]))
    for (const a of curNodes) {
      const conns = (a.connects_to || '').split(', ').filter(Boolean)
      for (const conn of conns) {
        const targetBatch = conn.split(' ')[0]
        const b = nextMap.get(targetBatch)
        if (b) {
          lines.push({ x1: a.x + a.w, y1: a.y + a.h / 2, x2: b.x, y2: b.y + b.h / 2, dashed: false, color: cfg[a.stage]?.color || '#999' })
        }
      }
    }
  }

  // 同级节点到下一列主线的虚线贝塞尔
  nodes.filter(n => n.is_sibling && n.connects_to).forEach(sib => {
    const targetBatch = sib.connects_to.split(' ')[0]
    const tgt = nodes.find(n => !n.is_sibling && n.col === sib.col + 1 && n.batch_no === targetBatch)
    if (tgt) {
      lines.push({ x1: sib.x + sib.w, y1: sib.y + sib.h / 2, x2: tgt.x, y2: tgt.y + tgt.h / 2, dashed: true, color: '#bbb' })
    }
  })

  // 阶段注释：放在每列所有节点下方
  stageList.forEach((sg, col) => {
    if (!sg.note) return
    const colNodes = nodes.filter(n => n.col === col).sort((a, b) => b.y - a.y)
    const lastNode = colNodes[0]
    if (!lastNode) return
    const nx = lastNode.x
    const ny = lastNode.y + lastNode.h + 8
    notes.push({ text: sg.note, x: nx, y: ny, targetX: lastNode.x + lastNode.w / 2, targetY: lastNode.y + lastNode.h,
      color: cfg[sg.stage]?.color || '#999' })
  })

  return { nodes, lines, notes }
}


export default function TraceModal({ stage, batchNo, onClose, stageConfig, stageOrder, apiPrefix }: Props) {
  const cfg = stageConfig || STAGE_CFG
  const order = stageOrder || STAGE_ORDER
  const apiPath = apiPrefix || '/mc/lineage'
  const [loading, setLoading] = useState(true)
  const [layout, setLayout] = useState<{ nodes: any[]; lines: any[]; notes: any[] }>({ nodes: [], lines: [], notes: [] })
  const [error, setError] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiResult, setAiResult] = useState<any>(null)
  const { message } = App.useApp()

  // 追问聊天
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMessages])

  // AI 分析历史
  const [historyRecords, setHistoryRecords] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true); setHistoryRecords([])
    try {
      const r = await fetch(API(`${apiPath}/ai-history?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo)}`))
      const json = await r.json()
      if (json.code === 200) setHistoryRecords(json.data.records || [])
    } catch { /* ignore */ }
    finally { setHistoryLoading(false) }
  }, [stage, batchNo])

  useEffect(() => {
    if (!batchNo) return
    setLoading(true); setError('')
    fetch(API(`${apiPath}/trace?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo)}`))
      .then(r => r.json())
      .then(json => {
        if (json.code === 200) {
          setLayout(buildLayout(json.data.stages || [], json.data.target_batch, json.data.target_stage, cfg, order))
        } else setError(json.message || '未查到数据')
      })
      .catch(() => setError('网络错误'))
      .finally(() => setLoading(false))
  }, [stage, batchNo])

  const exportPng = () => {
    const svg = svgRef.current
    if (!svg) return
    const clone = svg.cloneNode(true) as SVGSVGElement
    const w = parseInt(svg.getAttribute('width') || '800')
    const h = parseInt(svg.getAttribute('height') || '400')
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    const data = new XMLSerializer().serializeToString(clone)
    const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>' + data], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas'); canvas.width = w * 2; canvas.height = h * 2
      const ctx = canvas.getContext('2d')!; ctx.scale(2, 2); ctx.fillStyle = '#fff'
      ctx.fillRect(0, 0, w, h); ctx.drawImage(img, 0, 0)
      canvas.toBlob(b => {
        if (!b) return
        const a = document.createElement('a'); a.href = URL.createObjectURL(b)
        a.download = `追溯_MC_${batchNo}_${new Date().toISOString().slice(0, 10)}.png`; a.click()
      }, 'image/png')
      URL.revokeObjectURL(url)
    }
    img.src = url
  }

  const doAiAnalysis = async () => {
    setAiLoading(true); setChatMessages([])
    try {
      const r = await fetch(API(`${apiPath}/ai-analysis?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo)}`),
        { signal: AbortSignal.timeout(180000) })
      const json = await r.json()
      if (json.code === 200) setAiResult(json.data)
      else message.error(json.message || 'AI 分析失败')
    } catch { message.error('AI 分析超时') }
    finally { setAiLoading(false) }
  }

  const doChatSend = useCallback(async () => {
    const msg = chatInput.trim()
    if (!msg || !aiResult?.session_id) return
    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', content: msg }])
    setChatSending(true)

    // 添加占位 AI 消息
    setChatMessages(prev => [...prev, { role: 'assistant', content: '' }])

    try {
      const r = await fetch(API('/mc/chat/send'), {
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
    } catch (e: any) {
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

  const maxX = layout.nodes.reduce((m, n) => Math.max(m, n.x + n.w), 0) + 40
  const maxY = Math.max(layout.nodes.reduce((m, n) => Math.max(m, n.y + n.h), 0),
    layout.notes.reduce((m, n) => Math.max(m, n.y + 20), 0)) + 40

  return (
    <Modal
      title={<span>批次追溯：<Text strong style={{ color: '#f5222d', margin: '0 8px' }}>{batchNo}</Text>
        <Button size="small" type="primary" loading={aiLoading} onClick={doAiAnalysis} style={{ marginLeft: 12 }}>
          AI 分析
        </Button>
        <Button icon={<DownloadOutlined />} size="small" style={{ marginLeft: 8 }} onClick={exportPng}>导出</Button>
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
          <Button icon={<HistoryOutlined />} size="small" style={{ marginLeft: 8 }}>历史记录</Button>
        </Popover>
      </span>}
      open onCancel={onClose} destroyOnHidden
      width={Math.min(window.innerWidth - 100, Math.max(1100, maxX + 100))}
      styles={{ body: { minHeight: '60vh', padding: 0 } }}
      footer={null}
    >
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {error && <Empty description={error} />}
      {!loading && !error && layout.nodes.length > 0 && (
        <div style={{ overflow: 'auto', maxHeight: '75vh' }}>
          <svg width={maxX} height={maxY} style={{ display: 'block' }} ref={svgRef}>
            <defs>
              <marker id="am" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#999" />
              </marker>
              <marker id="ad" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#bbb" />
              </marker>
            </defs>
            {layout.lines.map((l, i) => {
              const mx = (l.x1 + l.x2) / 2
              return (
                <path key={i}
                  d={`M ${l.x1} ${l.y1} C ${mx} ${l.y1}, ${mx} ${l.y2}, ${l.x2} ${l.y2}`}
                  fill="none" stroke={l.color} strokeWidth="1.5"
                  strokeDasharray={l.dashed ? '5 3' : undefined}
                  markerEnd={l.dashed ? 'url(#ad)' : 'url(#am)'}
                />
              )
            })}
            {/* 阶段注释：虚线连到列底部 */}
            {layout.notes.map((n, i) => (
              <g key={`note${i}`}>
                <line x1={n.targetX} y1={n.targetY} x2={n.targetX} y2={n.y - 2}
                  stroke={n.color} strokeWidth="1" strokeDasharray="3 2" opacity="0.5" />
                <text x={n.x + 76} y={n.y + 12} fontSize="9" fill={n.color} opacity="0.8"
                  textAnchor="middle" style={{ fontStyle: 'italic' }}>{n.text}</text>
              </g>
            ))}
            {layout.nodes.map(n => {
              const c = cfg[n.stage]?.color || '#999'
              const isTgt = n.is_target
              return (
                <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
                  <rect x="0" y="0" width={n.w} height={n.h} rx="6"
                    fill={isTgt ? '#fff2f0' : n.is_sibling ? '#fafafa' : '#fff'}
                    stroke={isTgt ? '#f5222d' : n.is_sibling ? '#d9d9d9' : c + '60'}
                    strokeWidth={isTgt ? 2 : 1}
                    strokeDasharray={n.is_sibling ? '4 2' : undefined}
                  />
                  <text x="8" y="16" fontSize="10" fill={c} fontWeight="bold">{n.label}</text>
                  <text x="8" y="30" fontSize="11" fill={isTgt ? '#f5222d' : '#333'} fontWeight={isTgt ? 'bold' : 'normal'}>
                    {n.batch_no}
                  </text>
                  {n.detail && <text x="8" y="44" fontSize="9" fill="#888">{n.detail}</text>}
                  {n.is_sibling && (
                    <text x="8" y={n.detail ? 54 : 44} fontSize="9" fill="#bbb">
                      {n.connects_to ? '汇入: ' + n.connects_to : '同级'}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>

          {/* ── AI 分析结果 ── */}
          {aiResult && (
            <div style={{ padding: '12px 16px', borderTop: '1px solid #f0f0f0' }}>
              <div style={{ marginBottom: 8 }}>
                <Tag color={aiResult.severity === 'high' ? 'red' : aiResult.severity === 'medium' ? 'orange' : 'green'}>
                  {aiResult.severity === 'high' ? '严重' : aiResult.severity === 'medium' ? '中等' : '正常'}
                </Tag>
                <Text style={{ marginLeft: 8 }}>{aiResult.summary}</Text>
              </div>
              {aiResult.causes?.length > 0 && <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>原因：{aiResult.causes.join('；')}</div>}
              {aiResult.suggestions?.length > 0 && <div style={{ fontSize: 12, color: '#1677ff', marginTop: 4 }}>建议：{aiResult.suggestions.join('；')}</div>}

              {/* ── 追问区域 ── */}
              <div style={{ marginTop: 12, borderTop: '1px dashed #e8e8e8', paddingTop: 8 }}>
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

                <Space.Compact style={{ width: '100%', marginTop: 4 }}>
                  <Input
                    size="small"
                    placeholder="继续追问..."
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
        </div>
      )}
      {!loading && !error && layout.nodes.length === 0 && <Empty description="未查到相关批次" />}
    </Modal>
  )
}
