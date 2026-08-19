'use client'
// FA 苯丙氨酸 — 全链路追溯页面（血缘流程图 + AI 分析 + 对话）

import { useState, useCallback, Suspense } from 'react'
import {
  Button, Input, Space, Card, Typography, App, Tag, Spin, Empty, Row, Col, Popover, Select
} from 'antd'
import {
  ArrowLeftOutlined, SearchOutlined, NodeIndexOutlined,
  BulbOutlined, SendOutlined, HistoryOutlined,
} from '@ant-design/icons'
import { useRouter, useSearchParams } from 'next/navigation'
import FA_BATCH_TYPES, { FA_STAGE_CFG, FA_STAGE_ORDER } from '@/components/production/faBatchTypes'
import { useFAChat } from '@/hooks/useFAChat'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/fa'

const STAGE_COLORS: Record<string, string> = {
  fermentation: '#52c41a', acidification: '#1890ff',
  decolor1: '#13c2c2', decolor_centrifuge: '#722ed1',
}

const STAGE_LABELS: Record<string, string> = {
  fermentation: '发酵放罐', acidification: '酸化过滤',
  decolor1: '一次脱色', decolor_centrifuge: '脱色离心',
}

interface FlowData { stages: any[]; target_batch: string; target_stage: string }

export default function FATraceabilityPage() {
  return (
    <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spin size="large" /></div>}>
      <FATraceabilityContent />
    </Suspense>
  )
}

function FATraceabilityContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { message } = App.useApp()

  // ── 搜索状态 ──
  const [stage, setStage] = useState(searchParams.get('stage') || 'fermentation')
  const [batchNo, setBatchNo] = useState(searchParams.get('batchNo') || '')
  const [loading, setLoading] = useState(false)
  const [flowData, setFlowData] = useState<FlowData | null>(null)

  // ── AI 分析 + 对话（共享 Hook）──
  const {
    aiLoading, aiResult, thinkingSteps, thinkingText,
    chatMessages, chatInput, chatSending, chatEndRef,
    historyRecords, historyLoading,
    doAiAnalysis, doChatSend, loadHistory,
    setChatInput, setChatMessages, setAiResult, setHistoryRecords, aiResultRef,
  } = useFAChat({ stage, batchNo })

  // ═══════════════ 搜索追溯 ═══════════════
  const handleSearch = useCallback(async () => {
    if (!batchNo.trim()) { message.warning('请输入批号'); return }
    setLoading(true); setAiResult(null); setChatMessages([]); setFlowData(null)
    try {
      const r = await fetch(`${API}${BASE}/lineage/trace?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo.trim())}`)
      const json = await r.json()
      if (json.code === 200) setFlowData(json.data)
      else message.error(json.message || '未找到批次数据')
    } catch {
      message.error('网络错误，请检查服务是否正常运行')
    } finally { setLoading(false) }
  }, [batchNo, stage, message, setAiResult, setChatMessages])

  // ── 血缘流程渲染 ──
  const renderFlow = () => {
    if (!flowData || !flowData.stages || flowData.stages.length === 0) return null

    const allNodes: { stage: string; label: string; batch_no: string; detail: string }[] = []
    flowData.stages.forEach((sg: any) => {
      (sg.nodes || []).forEach((n: any) => {
        allNodes.push({
          stage: sg.stage, label: sg.label,
          batch_no: n.batch_no, detail: n.detail || '',
        })
      })
    })

    return (
      <Card size="small" style={{ marginTop: 16, overflow: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 0, minWidth: allNodes.length * 220, padding: '16px 0' }}>
          {FA_STAGE_ORDER.map((sk, si) => {
            const nodes = allNodes.filter(n => n.stage === sk)
            if (nodes.length === 0) return null
            return (
              <div key={sk} style={{ display: 'flex', alignItems: 'center' }}>
                {si > 0 && (
                  <div style={{ width: 40, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <div style={{ width: 2, height: 20, background: '#d9d9d9' }} />
                    <div style={{ width: 0, height: 0, borderLeft: '8px solid #d9d9d9', borderTop: '6px solid transparent', borderBottom: '6px solid transparent', marginLeft: -2 }} />
                  </div>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ fontSize: 11, color: '#999', textAlign: 'center', marginBottom: 4, fontWeight: 500 }}>
                    {STAGE_LABELS[sk] || sk}
                  </div>
                  {nodes.map((n, ni) => (
                    <div key={ni} style={{
                      border: `2px solid ${STAGE_COLORS[sk] || '#999'}`,
                      borderRadius: 8, padding: '8px 12px',
                      minWidth: 160, background: '#fff',
                      boxShadow: n.batch_no === batchNo.trim() ? `0 0 0 2px ${STAGE_COLORS[sk]}40` : undefined,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: STAGE_COLORS[sk] }}>
                        {n.batch_no}
                        {n.batch_no === batchNo.trim() && <Tag color={STAGE_COLORS[sk]} style={{ fontSize: 10, marginLeft: 4 }}>当前</Tag>}
                      </div>
                      {n.detail && (
                        <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{n.detail}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </Card>
    )
  }

  return (
    <div className="p-6">
      {/* ── 标题栏 ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <Button type="link" icon={<ArrowLeftOutlined />}
            onClick={() => router.push('/production/batches/workshop/203?tab=workshop')}>
            返回车间
          </Button>
          <NodeIndexOutlined style={{ color: '#eb2f96', marginRight: 8 }} />
          FA 批次追溯
          <Text type="secondary" style={{ fontSize: 14, marginLeft: 12 }}>批次族谱 · 全链路追溯</Text>
        </Title>
      </div>

      {/* ── 搜索栏 ── */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space size={8} wrap>
          <Select
            size="small"
            value={stage}
            onChange={setStage}
            style={{ width: 140 }}
            options={FA_BATCH_TYPES}
          />
          <Input
            size="small"
            placeholder="输入批号，如 FA-EX25316"
            value={batchNo}
            onChange={e => setBatchNo(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 200 }}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={handleSearch}
            loading={loading}
          >
            追溯
          </Button>
        </Space>
      </Card>

      <Spin spinning={loading}>
        {flowData ? (
          <>
            {/* ── 血缘流程图 ── */}
            {renderFlow()}

            {/* ── 批次概要 ── */}
            <Card size="small" style={{ marginTop: 16 }}>
              <Space size={16} wrap>
                <Text strong>目标批次: {flowData.target_batch}</Text>
                <Tag color={STAGE_COLORS[flowData.target_stage]}>
                  {STAGE_LABELS[flowData.target_stage] || flowData.target_stage}
                </Tag>
                <Text type="secondary">
                  共 {flowData.stages?.reduce((s: number, sg: any) => s + (sg.nodes?.length || 0), 0) || 0} 个节点，
                  {flowData.stages?.length || 0} 个工段
                </Text>
              </Space>
            </Card>

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
                    <div style={{ width: 420, maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
                      {historyRecords.map((r: any) => (
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
                  <Button size="small" icon={<HistoryOutlined />}>分析历史</Button>
                </Popover>
              </Space>

              {/* 思考过程 */}
              {(thinkingSteps.length > 0 || aiLoading) && (
                <div style={{ marginTop: 12, padding: '8px 12px', background: '#fafafa', borderRadius: 6 }}>
                  {thinkingSteps.map((s: any, i: number) => (
                    <div key={i} style={{ fontSize: 12, color: s.done ? '#52c41a' : '#1677ff', marginBottom: 4 }}>
                      {s.done ? '✓' : '⏳'} {s.msg}
                    </div>
                  ))}
                  {thinkingText && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ cursor: 'pointer', color: '#999', fontSize: 12 }}>查看 LLM 原始输出</summary>
                      <pre style={{ fontSize: 11, color: '#999', whiteSpace: 'pre-wrap', marginTop: 4 }}>{thinkingText}</pre>
                    </details>
                  )}
                </div>
              )}
            </Card>

            {/* ── AI 分析结果 + 追问 ── */}
            {aiResult && (
              <Card size="small" style={{ marginTop: 16 }}>
                {/* 分析头 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Tag color={aiResult.severity === 'high' ? 'red' : aiResult.severity === 'medium' ? 'orange' : 'green'}>
                    {aiResult.severity === 'high' ? '🔴 严重' : aiResult.severity === 'medium' ? '🟡 中等' : '🟢 正常'}
                  </Tag>
                  <Text strong style={{ fontSize: 14 }}>{aiResult.summary || '分析完成'}</Text>
                  {aiResult.analysis_text && (
                    <Button size="small" onClick={() => navigator.clipboard.writeText(aiResult.analysis_text)}>复制</Button>
                  )}
                </div>

                {/* 异常列表 */}
                {(aiResult.anomalies || []).length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <Text strong style={{ fontSize: 12, color: '#999' }}>异常检测</Text>
                    <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {aiResult.anomalies.map((a: any, i: number) => (
                        <Tag key={i} color={a.severity === 'high' ? 'red' : a.severity === 'medium' ? 'orange' : 'blue'}>
                          {a.batch_no}: {a.detail}
                        </Tag>
                      ))}
                    </div>
                  </div>
                )}

                {/* 原因 */}
                {(aiResult.causes || []).length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <Text strong style={{ fontSize: 12, color: '#999' }}>原因分析</Text>
                    <ol style={{ margin: '4px 0', paddingLeft: 20 }}>
                      {aiResult.causes.map((c: string, i: number) => (
                        <li key={i} style={{ fontSize: 13, marginBottom: 2 }}>{c}</li>
                      ))}
                    </ol>
                  </div>
                )}

                {/* 建议 */}
                {(aiResult.suggestions || []).length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <Text strong style={{ fontSize: 12, color: '#999' }}>改进建议</Text>
                    <ol style={{ margin: '4px 0', paddingLeft: 20 }}>
                      {aiResult.suggestions.map((s: string, i: number) => (
                        <li key={i} style={{ fontSize: 13, marginBottom: 2 }}>{s}</li>
                      ))}
                    </ol>
                  </div>
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
              </Card>
            )}
          </>
        ) : (
          !loading && (
            <Card style={{ textAlign: 'center', padding: 60 }}>
              <Empty description="选择工段并输入批号，点击「追溯」查看完整生产链路" />
              <div style={{ marginTop: 16, fontSize: 13, color: '#999' }}>
                示例：工段选择「发酵液放罐」，批号输入「FA-EX25315」
              </div>
            </Card>
          )
        )}
      </Spin>
    </div>
  )
}
