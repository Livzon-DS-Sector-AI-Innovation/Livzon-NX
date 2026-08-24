'use client'
// FA 苯丙氨酸 — AI 分析与对话共享 Hook
// 从 203/traceability/page.tsx 提取，供 FATraceModal 和 traceability 页面共用

import { useState, useCallback, useRef, useEffect } from 'react'
import { App } from 'antd'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const BASE = '/api/v1/production/fa'

export interface UseFAChatOptions {
  stage: string
  batchNo: string
}

export function useFAChat({ stage, batchNo }: UseFAChatOptions) {
  const { message } = App.useApp()

  // ── AI 分析状态 ──
  const [aiLoading, setAiLoading] = useState(false)
  const [aiResult, setAiResult] = useState<any>(null)
  const aiResultRef = useRef<any>(null)
  const [thinkingSteps, setThinkingSteps] = useState<any[]>([])
  const [thinkingText, setThinkingText] = useState('')

  // ── 对话状态 ──
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // ── 历史状态 ──
  const [historyRecords, setHistoryRecords] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMessages])

  // ═══════════════ AI 分析 ═══════════════
  const doAiAnalysis = useCallback(async () => {
    if (!batchNo.trim()) return
    setAiLoading(true); setChatMessages([]); setAiResult(null)
    setThinkingSteps([]); setThinkingText('')

    try {
      const r = await fetch(
        `${API_BASE}${BASE}/lineage/ai-analysis-stream?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo.trim())}`,
        { signal: AbortSignal.timeout(240000) }
      )
      const reader = r.body?.getReader()
      if (!reader) throw new Error('No stream')
      const decoder = new TextDecoder()
      let buf = ''
      let gotResult = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'step') {
              setThinkingSteps(prev => {
                const idx = prev.findIndex(s => s.step === data.step)
                if (idx >= 0) { const copy = [...prev]; copy[idx] = data; return copy }
                return [...prev, data]
              })
            } else if (data.type === 'token') {
              setThinkingText(prev => prev + data.content)
            } else if (data.type === 'error') {
              message.error(data.msg || 'AI 分析失败')
            } else if (data.type === 'result') {
              gotResult = true
              const newResult = {
                ...data, analysis_text: data.analysis_text,
                causes: data.causes, suggestions: data.suggestions,
                severity: data.severity, summary: data.summary,
                session_id: data.session_id, anomalies: data.anomalies,
              }
              setAiResult(newResult)
              aiResultRef.current = newResult
            }
          } catch { /* skip malformed */ }
        }
      }
      if (!gotResult) {
        message.error('AI 分析未返回完整结果，请重试')
      }
    } catch {
      message.error('AI 分析失败，请重试')
    } finally {
      setAiLoading(false)
    }
  }, [batchNo, stage, message])

  // ═══════════════ 对话发送 ═══════════════
  const doChatSend = useCallback(async () => {
    const msg = chatInput.trim()
    if (!msg) return
    const currentResult = aiResultRef.current
    if (!currentResult?.session_id) {
      message.warning('会话已过期，请重新点击"AI 分析"')
      return
    }
    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', content: msg }, { role: 'assistant', content: '' }])
    setChatSending(true)
    try {
      const r = await fetch(`${API_BASE}${BASE}/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentResult.session_id, message: msg }),
      })
      const reader = r.body?.getReader()
      if (!reader) throw new Error('No stream')
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
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
            } catch { /* skip */ }
          }
        }
      }
    } catch {
      setChatMessages(prev => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last && last.role === 'assistant') {
          copy[copy.length - 1] = { ...last, content: '[网络错误] 发送失败，请重试' }
        }
        return copy
      })
    } finally {
      setChatSending(false)
    }
  }, [chatInput, message])

  // ═══════════════ 历史记录 ═══════════════
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const r = await fetch(`${API_BASE}${BASE}/lineage/ai-history?stage=${encodeURIComponent(stage)}&batch_no=${encodeURIComponent(batchNo.trim())}`)
      const json = await r.json()
      if (json.code === 200) setHistoryRecords(json.data.records || [])
    } catch { /* ignore */ }
    finally { setHistoryLoading(false) }
  }, [batchNo, stage])

  return {
    // 状态
    aiLoading, aiResult, thinkingSteps, thinkingText,
    chatMessages, chatInput, chatSending, chatEndRef,
    historyRecords, historyLoading,
    // 方法
    doAiAnalysis, doChatSend, loadHistory,
    setChatInput, setChatMessages, setAiResult, setHistoryRecords,
    aiResultRef,
  }
}
