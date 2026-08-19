'use client'

// DR 多拉菌素批次追溯弹窗（血链流程图，数据源 /dr/lineage）
// 适配自 MC TraceModal：工段配置改为 DR 七工段，无 AI 分析（第一版不做），支持断链标注

import { useEffect, useState, useRef } from 'react'
import { Modal, Typography, Tag, Spin, Empty, App, Button, Tooltip } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'

const { Text } = Typography
const API = (p: string) => `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/v1/production${p}`

const COL_X = 180
const ROW_H = 72   // 卡片加高到 66（容纳损耗行）后行距同步加大
const START_Y = 30

// DR 工段颜色（与 201-3 traceability 页 STAGE_CONFIG 一致）
const STAGE_CFG: Record<string, { color: string }> = {
  fermentation: { color: '#52c41a' },
  extraction: { color: '#1890ff' },
  chromatography: { color: '#722ed1' },
  first_refinement: { color: '#fa8c16' },
  second_refinement: { color: '#eb2f96' },
  third_refinement: { color: '#fa541c' },
  fourth_refinement: { color: '#13c2c2' },
  recovery: { color: '#999' },
}

const STAGE_ORDER = [
  'fermentation', 'extraction', 'chromatography',
  'first_refinement', 'second_refinement', 'third_refinement', 'fourth_refinement',
  'recovery',
]

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
    colHeights.push((mains.length + sibs.length) * ROW_H)
    colNodes.push([])
  })

  // 第二阶段：计算每列的垂直偏移量以居中于相邻列
  const colOffsets: number[] = []
  for (let col = 0; col < colHeights.length; col++) {
    const prevH = col > 0 ? colHeights[col - 1] : 0
    const nextH = col < colHeights.length - 1 ? colHeights[col + 1] : 0
    const maxNeighbor = Math.max(...colHeights, 0)
    const myH = colHeights[col]
    colOffsets.push(myH < maxNeighbor ? (maxNeighbor - myH) / 2 : 0)
  }

  // 第三阶段：分配 y 坐标
  stageList.forEach((sg, col) => {
    const mains = (sg.nodes || []).filter((n: any) => !n.is_sibling)
    mains.forEach((n: any, row: number) => {
      const isTarget = n.batch_no === targetBatch && sg.stage === targetStage
      nodes.push({
        id: `n${nid++}`, x: col * COL_X + 4, y: START_Y + colOffsets[col] + row * ROW_H, w: 152, h: 66,
        stage: sg.stage, label: sg.label, batch_no: n.batch_no,
        detail: n.detail || '', yield_rate: n.yield_rate, quantity: n.quantity,
        is_target: isTarget, is_sibling: false, connects_to: n.connects_to || '',
        sib_group: n.sib_group || '',
        broken: n.broken, broken_reason: n.broken_reason || '', col, row,
        loss_kg: n.loss_kg, loss_rate: n.loss_rate, loss_level: n.loss_level || ''
      })
    })
  })

  // 同级节点排在同列底部
  stageList.forEach((sg, col) => {
    const mainCount = (sg.nodes || []).filter((n: any) => !n.is_sibling).length
    const sibs = (sg.nodes || []).filter((n: any) => n.is_sibling)
    sibs.forEach((n: any, row: number) => {
      nodes.push({
        id: `n${nid++}`, x: col * COL_X + 4, y: START_Y + colOffsets[col] + mainCount * ROW_H + row * ROW_H, w: 152, h: 66,
        stage: sg.stage, label: sg.label, batch_no: n.batch_no,
        detail: n.detail || '', yield_rate: n.yield_rate, quantity: n.quantity,
        is_target: false, is_sibling: true, connects_to: n.connects_to || '',
        sib_group: n.sib_group || '',
        broken: n.broken, broken_reason: n.broken_reason || '', col, row: mainCount + row,
        loss_kg: n.loss_kg, loss_rate: n.loss_rate, loss_level: n.loss_level || ''
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
    // 主节点 → 第一个兄弟批：虚线竖线衔接（兄弟批与主批连续同源）
    if (mains.length > 0 && sibs.length > 0) {
      const a = mains[mains.length - 1]; const b = sibs[0]
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

  // 同源组蓝色虚线：源头节点（sib_group 批号，如发酵批）→ 同源组各成员，
  // 表达"这几个兄弟批源自同一个批"。
  // 单源头（sib_group 单个批号）逐成员画线；多源头共享（含顿号，如层析共享 2 个萃取）
  // 各源头 → 组左缘中点（组内竖虚线已串联成员）。
  const sibGroups: Record<string, any[]> = {}
  for (const n of nodes) {
    if (n.sib_group) {
      (sibGroups[n.sib_group] ||= []).push(n)
    }
  }
  for (const [groupKey, members] of Object.entries(sibGroups)) {
    const srcList = groupKey.split('、')
    const srcNodes = srcList.map(b => nodes.find(n => n.batch_no === b)).filter(Boolean) as any[]
    if (!srcNodes.length) continue
    if (srcList.length === 1) {
      // 单源头：源头 → 组内每个成员
      const src = srcNodes[0]
      for (const m of members) {
        if (m.col === src.col) continue   // 同列（列内虚线已表达）跳过
        lines.push({ x1: src.x + src.w, y1: src.y + src.h / 2, x2: m.x, y2: m.y + m.h / 2, dashed: true, color: '#1890ff' })
      }
    } else {
      // 多源头：各源头 → 组左缘中点
      const ys = members.map(m => m.y + m.h / 2)
      const midY = (Math.min(...ys) + Math.max(...ys)) / 2
      const minX = Math.min(...members.map(m => m.x))
      for (const src of srcNodes) {
        if (src.col === members[0].col) continue
        lines.push({ x1: src.x + src.w, y1: src.y + src.h / 2, x2: minX, y2: midY, dashed: true, color: '#1890ff' })
      }
    }
  }

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


export default function DRTraceModal({ stage, batchNo, onClose, stageConfig, stageOrder, apiPrefix }: Props) {
  const cfg = stageConfig || STAGE_CFG
  const order = stageOrder || STAGE_ORDER
  const apiPath = apiPrefix || '/dr/lineage'
  const [loading, setLoading] = useState(true)
  const [layout, setLayout] = useState<{ nodes: any[]; lines: any[]; notes: any[] }>({ nodes: [], lines: [], notes: [] })
  const [error, setError] = useState('')
  const { message } = App.useApp()
  const svgRef = useRef<SVGSVGElement>(null)

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
        a.download = `追溯_DR_${batchNo}_${new Date().toISOString().slice(0, 10)}.png`; a.click()
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
      title={<span>批次追溯：<Text strong style={{ color: '#f5222d', margin: '0 8px' }}>{batchNo}</Text>
        <Button icon={<DownloadOutlined />} size="small" onClick={exportPng}>导出</Button>
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
              <marker id="ab" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#1890ff" />
              </marker>
            </defs>
            {layout.lines.map((l, i) => {
              const mx = (l.x1 + l.x2) / 2
              return (
                <path key={i}
                  d={`M ${l.x1} ${l.y1} C ${mx} ${l.y1}, ${mx} ${l.y2}, ${l.x2} ${l.y2}`}
                  fill="none" stroke={l.color} strokeWidth="1.5"
                  strokeDasharray={l.dashed ? '5 3' : undefined}
                  markerEnd={l.dashed ? (l.color === '#1890ff' ? 'url(#ab)' : 'url(#ad)') : 'url(#am)'}
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
              const isBroken = n.broken
              return (
                <g key={n.id} transform={`translate(${n.x}, ${n.y})`}>
                  <rect x="0" y="0" width={n.w} height={n.h} rx="6"
                    fill={isBroken ? '#fff1f0' : isTgt ? '#fff2f0' : n.is_sibling ? '#fafafa' : '#fff'}
                    stroke={isBroken ? '#ff4d4f' : isTgt ? '#f5222d' : n.is_sibling ? '#d9d9d9' : c + '60'}
                    strokeWidth={isBroken || isTgt ? 2 : 1}
                    strokeDasharray={n.is_sibling ? '4 2' : undefined}
                  />
                  <text x="8" y="16" fontSize="10" fill={isBroken ? '#ff4d4f' : c} fontWeight="bold">
                    {isBroken ? '⚠ ' : ''}{n.label}
                  </text>
                  <text x="8" y="30" fontSize="11" fill={isBroken ? '#ff4d4f' : isTgt ? '#f5222d' : '#333'} fontWeight={isTgt ? 'bold' : 'normal'}>
                    {n.batch_no}
                  </text>
                  {n.detail && !isBroken && <text x="8" y="42" fontSize="9" fill="#888">{n.detail}</text>}
                  {isBroken && (
                    <text x="8" y="42" fontSize="9" fill="#ff4d4f">
                      {n.broken_reason || '断链'}
                    </text>
                  )}
                  {!isBroken && n.loss_kg != null && n.loss_rate != null && (
                    <Tooltip title={(() => {
                      const bd = n.loss_breakdown
                      if (bd && bd.recorded) {
                        const parts: string[] = []
                        if (bd.mother_liquor_kg != null) parts.push(`母液带走 ${bd.mother_liquor_kg}kg`)
                        if (bd.recovery_powder_kg != null) parts.push(`回收粉 ${bd.recovery_powder_kg}kg`)
                        if (bd.other_kg != null) parts.push(`其他 ${bd.other_kg}kg`)
                        return `损耗 ${Number(n.loss_kg).toFixed(2)}kg = ${parts.join(' + ')}`
                      }
                      return n.stage === 'fourth_refinement' ? '损耗 = 投入折纯 − 产出干粉（四次精制为干粉口径）' : '损耗 = 投入折纯 − 产出折纯'
                    })()}>
                      <g style={{ cursor: 'help' }}>
                        <rect x="6" y={45} width={n.w - 12} height={14} rx="3"
                          fill={n.loss_level === 'red' ? '#fff1f0' : n.loss_level === 'yellow' ? '#fffbe6' : '#f6ffed'}
                          stroke={n.loss_level === 'red' ? '#ffccc7' : n.loss_level === 'yellow' ? '#ffe58f' : '#b7eb8f'}
                          strokeWidth="1"
                        />
                        <text x="10" y={55} fontSize="9" fontWeight="bold"
                          fill={n.loss_level === 'red' ? '#cf1322' : n.loss_level === 'yellow' ? '#d46b08' : '#389e0d'}>
                          损耗 {Number(n.loss_kg).toFixed(2)}kg · {Number(n.loss_rate).toFixed(1)}%
                          {n.stage === 'fourth_refinement' ? '(干粉)' : ''}
                        </text>
                      </g>
                    </Tooltip>
                  )}
                  {!isBroken && n.yield_rate != null && (
                    <text x="8" y={n.loss_kg != null ? 64 : (n.detail ? 54 : 44)} fontSize="9" fill="#666">
                      yr {Number(n.yield_rate).toFixed(1)}%
                    </text>
                  )}
                  {n.is_sibling && !isBroken && (
                    <text x="8" y={n.loss_kg != null ? 64 : (n.detail ? 54 : 44)} fontSize="9" fill="#bbb">
                      {n.connects_to ? '汇入: ' + n.connects_to : '同级'}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>
      )}
      {!loading && !error && layout.nodes.length === 0 && <Empty description="未查到相关批次" />}
    </Modal>
  )
}
