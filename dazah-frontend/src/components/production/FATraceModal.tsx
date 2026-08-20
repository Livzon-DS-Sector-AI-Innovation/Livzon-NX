'use client'
// FA 苯丙氨酸 — 专用批次追溯弹窗（血缘 SVG + AI 分析 + 对话）

import { useEffect, useState, useRef } from 'react'
import { Modal, Typography, Tag, Spin, Empty, Button, Input, Space, Popover } from 'antd'
import { SendOutlined, HistoryOutlined, DownloadOutlined, BulbOutlined } from '@ant-design/icons'
import { useFAChat } from '@/hooks/useFAChat'

const { Text } = Typography
const API = (p: string) => `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/v1/production${p}`

interface StageGroup { stage: string; label: string; nodes: any[]; note?: string }
interface Props { stage: string; batchNo: string; onClose: () => void }

// ── FA 工段颜色 ──
const FA_STAGE_CFG: Record<string, { color: string }> = {
  fermentation: { color: '#52c41a' },
  acidification: { color: '#1890ff' },
  decolor1: { color: '#13c2c2' },
  decolor_centrifuge: { color: '#722ed1' },
}


const FA_STAGE_ORDER = ['fermentation', 'acidification', 'decolor1', 'decolor_centrifuge']

const COL_X = 200
const ROW_H = 56
const START_Y = 30
const BRANCH_GAP = 16


function buildLayout(stages: StageGroup[], targetBatch: string, targetStage: string) {
  const nodes: any[] = []; const lines: any[] = []; const notes: any[] = []
  const stageList = stages.filter(s => FA_STAGE_ORDER.includes(s.stage))
  if (stageList.length === 0) return { nodes, lines, notes }

  let nid = 0

  // 计算每列高度
  const colHeights: number[] = []
  stageList.forEach((sg) => {
    const mains = (sg.nodes || []).filter((n) => !n.is_sibling)
    const sibs = (sg.nodes || []).filter((n) => n.is_sibling)
    colHeights.push(mains.length * ROW_H + (sibs.length > 0 ? BRANCH_GAP + sibs.length * ROW_H : 0))
  })

  const maxH = Math.max(...colHeights)
  const colOffsets = colHeights.map(h => (maxH - h) / 2)

  // 分配坐标
  stageList.forEach((sg, col) => {
    const mains = (sg.nodes || []).filter((n) => !n.is_sibling)
    mains.forEach((n: any, row: number) => {
      const isTarget = n.batch_no === targetBatch && sg.stage === targetStage
      nodes.push({
        id: `n${nid++}`, x: col * COL_X + 4, y: START_Y + colOffsets[col] + row * ROW_H,
        w: 172, h: 52, stage: sg.stage, label: sg.label, batch_no: n.batch_no,
        detail: n.detail || '', yield_rate: n.yield_rate, quantity: n.quantity,
        is_target: isTarget, is_sibling: false, connects_to: n.connects_to || '', col, row
      })
    })
  })

  // 同级节点
  stageList.forEach((sg, col) => {
    const mainCount = (sg.nodes || []).filter((n) => !n.is_sibling).length
    const sibs = (sg.nodes || []).filter((n) => n.is_sibling)
    sibs.forEach((n: any, row: number) => {
      nodes.push({
        id: `n${nid++}`, x: col * COL_X + 4, y: START_Y + colOffsets[col] + mainCount * ROW_H + BRANCH_GAP + row * ROW_H,
        w: 172, h: 52, stage: sg.stage, label: sg.label, batch_no: n.batch_no,
        detail: n.detail || '', yield_rate: n.yield_rate, quantity: n.quantity,
        is_target: false, is_sibling: true, connects_to: n.connects_to || '', col, row: mainCount + row
      })
    })
  })

  // 连线：根据 connects_to 画真实连线
  for (let col = 0; col < stageList.length - 1; col++) {
    const curNodes = nodes.filter(n => n.col === col && !n.is_sibling)
    const nextNodes = nodes.filter(n => n.col === col + 1 && !n.is_sibling)
    const nextMap = new Map(nextNodes.map(n => [n.batch_no, n]))
    for (const a of curNodes) {
      const conns = (a.connects_to || '').split(', ').filter(Boolean)
      for (const conn of conns) {
        const tgt = nextMap.get(conn.split(' ')[0])
        if (tgt) {
          lines.push({ x1: a.x + a.w, y1: a.y + a.h / 2, x2: tgt.x, y2: tgt.y + a.h / 2,
            dashed: false, color: FA_STAGE_CFG[a.stage]?.color || '#999' })
        }
      }
    }
  }

  // 阶段注释
  stageList.forEach((sg, col) => {
    if (!sg.note) return
    const colNodes = nodes.filter(n => n.col === col).sort((a, b) => b.y - a.y)
    const last = colNodes[0]
    if (!last) return
    notes.push({ text: sg.note, x: last.x, y: last.y + last.h + 8,
      targetX: last.x + last.w / 2, targetY: last.y + last.h,
      color: FA_STAGE_CFG[sg.stage]?.color || '#999' })
  })

  return { nodes, lines, notes }
}


export default function FATraceModal({ stage, batchNo, onClose }: Props) {
  const [loading, setLoading] = useState(true)
  const [layout, setLayout] = useState<{ nodes: any[]; lines: any[]; notes: any[] }>({ nodes: [], lines: [], notes: [] })
  const [error, setError] = useState('')
  const svgRef = useRef<SVGSVGElement>(null)

  // ── AI 分析 + 对话（共享 Hook）──
  const {
    aiLoading, aiResult, thinkingSteps,
    chatMessages, chatInput, chatSending, chatEndRef,
    historyRecords, historyLoading,
    doAiAnalysis, doChatSend, loadHistory,
    setChatInput, setChatMessages, setAiResult, aiResultRef,
  } = useFAChat({ stage, batchNo })

  // 追溯查询
  useEffect(() => {
    if (!batchNo) return
    setLoading(true); setError('') // eslint-disable-line react-hooks/set-state-in-effect
    fetch(API(`/fa/lineage/trace?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo)}`))
      .then(r => r.json())
      .then(json => {
        if (json.code === 200) {
          setLayout(buildLayout(json.data.stages || [], json.data.target_batch, json.data.target_stage))
        } else setError(json.message || '未查到数据')
      })
      .catch(() => setError('网络错误'))
      .finally(() => setLoading(false))
  }, [stage, batchNo])

  // 导出 PNG
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
        a.download = `追溯_FA_${batchNo}_${new Date().toISOString().slice(0, 10)}.png`; a.click()
      }, 'image/png')
      URL.revokeObjectURL(url)
    }
    img.src = url
  }

  const maxX = layout.nodes.reduce((m, n) => Math.max(m, n.x + n.w), 0) + 40
  const maxY = Math.max(layout.nodes.reduce((m, n) => Math.max(m, n.y + n.h), 0),
    layout.notes.reduce((m, n) => Math.max(m, n.y + 20), 0)) + 40

  return (
    <Modal
      title={<span>FA 批次追溯：<Text strong style={{ color: '#eb2f96', margin: '0 8px' }}>{batchNo}</Text>
        <Button size="small" type="primary" icon={<BulbOutlined />} loading={aiLoading} onClick={doAiAnalysis} style={{ marginLeft: 12 }}>
          AI 分析
        </Button>
        <Button icon={<DownloadOutlined />} size="small" style={{ marginLeft: 8 }} onClick={exportPng}>导出</Button>
        <Popover
          trigger="click" onOpenChange={(open) => { if (open) loadHistory() }} placement="bottomLeft"
          title="分析历史"
          content={
            historyLoading ? <Spin size="small" /> :
            historyRecords.length === 0 ? <Text type="secondary">暂无历史分析</Text> :
            <div style={{ width: 480, maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
              {historyRecords.map((r) => (
                <div key={r.id}
                  style={{ display: 'flex', alignItems: 'center', padding: '4px 0', cursor: 'pointer', borderBottom: '1px solid #fafafa' }}
                  onClick={() => {
                    const rr = { ...r, analysis_text: null, session_id: r.session_id }
                    setAiResult(rr); aiResultRef.current = rr; setChatMessages([])
                  }}>
                  <Tag color={r.severity === 'high' ? 'red' : r.severity === 'medium' ? 'orange' : 'green'} style={{ fontSize: 10, margin: 0, width: 40 }}>
                    {r.severity === 'high' ? '严重' : r.severity === 'medium' ? '中等' : '正常'}
                  </Tag>
                  <Text style={{ width: 100 }} ellipsis>{(r.created_at || '').slice(0, 16)}</Text>
                  <Text style={{ flex: 1 }} ellipsis>{r.summary}</Text>
                </div>
              ))}
            </div>
          }
        >
          <Button icon={<HistoryOutlined />} size="small" style={{ marginLeft: 8 }}>历史</Button>
        </Popover>
      </span>}
      open onCancel={onClose} destroyOnHidden
      width={Math.min(window.innerWidth - 100, Math.max(960, maxX + 100))}
      styles={{ body: { minHeight: '50vh', padding: 0 } }}
      footer={null}
    >
      {loading && <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>}
      {error && <Empty description={error} />}
      {!loading && !error && layout.nodes.length > 0 && (
        <div style={{ overflow: 'auto', maxHeight: '75vh' }}>
          <svg width={maxX} height={maxY} style={{ display: 'block' }} ref={svgRef}>
            <defs>
              <marker id="fam" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#999" />
              </marker>
            </defs>
            {layout.lines.map((l, i) => (
              <path key={i}
                d={`M ${l.x1} ${l.y1} C ${(l.x1+l.x2)/2} ${l.y1}, ${(l.x1+l.x2)/2} ${l.y2}, ${l.x2} ${l.y2}`}
                fill="none" stroke={l.color} strokeWidth="1.5"
                strokeDasharray={l.dashed ? '5 3' : undefined}
                markerEnd="url(#fam)"
              />
            ))}
            {layout.notes.map((n, i) => (
              <g key={`fn${i}`}>
                <line x1={n.targetX} y1={n.targetY} x2={n.targetX} y2={n.y - 2}
                  stroke={n.color} strokeWidth="1" strokeDasharray="3 2" opacity="0.5" />
                <text x={n.x + 86} y={n.y + 12} fontSize="9" fill={n.color} opacity="0.8"
                  textAnchor="middle" fontStyle="italic">{n.text}</text>
              </g>
            ))}
            {layout.nodes.map(n => {
              const c = FA_STAGE_CFG[n.stage]?.color || '#999'
              const isTgt = n.is_target
              return (
                <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
                  <rect x="0" y="0" width={n.w} height={n.h} rx="6"
                    fill={isTgt ? '#fff0f6' : n.is_sibling ? '#fafafa' : '#fff'}
                    stroke={isTgt ? '#eb2f96' : n.is_sibling ? '#d9d9d9' : c + '60'}
                    strokeWidth={isTgt ? 2 : 1}
                    strokeDasharray={n.is_sibling ? '4 2' : undefined}
                  />
                  <text x="8" y="16" fontSize="10" fill={c} fontWeight="bold">{n.label}</text>
                  <text x="8" y="30" fontSize="11" fill={isTgt ? '#eb2f96' : '#333'} fontWeight={isTgt ? 'bold' : 'normal'}>
                    {n.batch_no}
                  </text>
                  {n.detail && <text x="8" y="44" fontSize="9" fill="#888">{n.detail}</text>}
                  {n.is_sibling && <text x="8" y={n.detail ? 54 : 44} fontSize="9" fill="#bbb">
                    {n.connects_to ? '汇入: ' + n.connects_to : '同级'}
                  </text>}
                </g>
              )
            })}
          </svg>

          {/* AI 分析思考过程 */}
          {thinkingSteps.length > 0 && (
            <div style={{ padding: '8px 16px', background: '#fafafa', fontSize: 12 }}>
              {thinkingSteps.map((s, i) => (
                <div key={i} style={{ color: s.done ? '#52c41a' : '#1677ff' }}>
                  {s.done ? '✓' : '⏳'} {s.msg}
                </div>
              ))}
            </div>
          )}

          {/* AI 分析结果 + 追问 */}
          {aiResult && (
            <div style={{ padding: '12px 16px', borderTop: '1px solid #f0f0f0' }}>
              <div style={{ marginBottom: 8 }}>
                <Tag color={aiResult.severity === 'high' ? 'red' : aiResult.severity === 'medium' ? 'orange' : 'green'}>
                  {aiResult.severity === 'high' ? '🔴 严重' : aiResult.severity === 'medium' ? '🟡 中等' : '🟢 正常'}
                </Tag>
                <Text style={{ marginLeft: 8 }}>{aiResult.summary}</Text>
              </div>
              {aiResult.causes?.length > 0 && (
                <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                  <Text strong style={{ color: '#999' }}>原因：</Text>
                  {aiResult.causes.join('；')}
                </div>
              )}
              {aiResult.suggestions?.length > 0 && (
                <div style={{ fontSize: 12, color: '#1677ff', marginTop: 4 }}>
                  <Text strong style={{ color: '#999' }}>建议：</Text>
                  {aiResult.suggestions.join('；')}
                </div>
              )}

              {/* 追问区域 */}
              <div style={{ marginTop: 12, borderTop: '1px dashed #e8e8e8', paddingTop: 8 }}>
                <Text strong style={{ fontSize: 12, color: '#999' }}>继续追问</Text>
                {chatMessages.map((m, i) => (
                  <div key={i} style={{
                    marginTop: 4, padding: '6px 10px', borderRadius: 8, fontSize: 13,
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
