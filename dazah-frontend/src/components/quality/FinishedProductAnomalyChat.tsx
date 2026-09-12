'use client'

import { useEffect, useRef, useState } from 'react'
import { App, Button, Drawer, Input } from 'antd'
import { RobotOutlined, SendOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'

interface ChatMessageItem {
  role: 'user' | 'assistant'
  content: string
}

interface FinishedProductAnomalyChatProps {
  open: boolean
  year?: number | null
  onClose: () => void
}

/** SSE 事件解析：与后端 _sse 输出（data: {...}）对应 */
async function streamAnomalyChat(
  messages: ChatMessageItem[],
  year: number | null,
  onEvent: (event: {
    status?: string
    content?: string
    reasoning_content?: string
  }) => void,
): Promise<void> {
  const res = await fetch('/api/v1/quality/finished-product-anomaly/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: messages.map((item) => ({ role: item.role, content: item.content })),
      year: year ?? null,
    }),
  })
  if (!res.ok || !res.body) {
    let detail = `请求失败: ${res.status}`
    try {
      const errJson = await res.json()
      if (errJson?.message) detail = errJson.message
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  while (!finished) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      try {
        const payload = JSON.parse(trimmed.slice(5).trim())
        if (payload.done) {
          finished = true
        } else {
          onEvent(payload)
        }
      } catch {
        /* 忽略不完整行 */
      }
    }
  }
}

/** 成品异常 AI 助手聊天抽屉：查询全部成品异常数据 + 不合格项 AI 分析。 */
export function FinishedProductAnomalyChat({ open, year, onClose }: FinishedProductAnomalyChatProps) {
  const { message } = App.useApp()
  const [messages, setMessages] = useState<ChatMessageItem[]>([
    {
      role: 'assistant',
      content:
        '你好，我是成品异常 AI 助手（资深现场 QA 视角）。\n\n你可以直接问我，例如：\n- 2026 年哪个产品杂质异常最多？\n- 列出色氨酸 2025 年的残渣超标记录\n- 帮我分析 TY-2502004-3 残渣不合格这条记录',
    },
  ])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamStatus, setStreamStatus] = useState('')
  const [thinking, setThinking] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages, streamStatus, thinking])

  const send = async () => {
    const text = input.trim()
    if (!text || streaming) return
    const nextMessages: ChatMessageItem[] = [...messages, { role: 'user', content: text }]
    setMessages([...nextMessages, { role: 'assistant', content: '' }])
    setInput('')
    setStreaming(true)
    setStreamStatus('')
    setThinking('')
    try {
      let assistantText = ''
      await streamAnomalyChat(nextMessages, year ?? null, (event) => {
        if (event.status) {
          setStreamStatus(event.status)
        } else if (event.reasoning_content) {
          // 完整累积思考过程，实时可见（复杂问题整体约需 1-3 分钟）
          setThinking((prev) => prev + event.reasoning_content)
        }
        if (event.content) {
          assistantText += event.content
          setStreamStatus('')
          setMessages((prev) => {
            const copy = [...prev]
            copy[copy.length - 1] = { role: 'assistant', content: assistantText }
            return copy
          })
        }
      })
      if (!assistantText) {
        setMessages((prev) => {
          const copy = [...prev]
          copy[copy.length - 1] = {
            role: 'assistant',
            content: '（AI 未返回内容，请稍后重试或检查 AI 模型配置）',
          }
          return copy
        })
      }
    } catch (error: unknown) {
      const text = error instanceof Error && error.message ? error.message : 'AI 服务调用失败'
      message.error(text)
      setMessages((prev) => {
        const copy = [...prev]
        copy[copy.length - 1] = { role: 'assistant', content: `调用失败：${text}` }
        return copy
      })
    } finally {
      setStreaming(false)
      setStreamStatus('')
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={
        <span style={{ fontSize: 15 }}>
          <RobotOutlined style={{ marginRight: 8 }} />
          成品异常 AI 助手
        </span>
      }
      size={720}
      destroyOnHidden
      styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', height: '100%' } }}
    >
      <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: 16, background: 'var(--color-bg, #fafaf9)' }}>
        {messages.map((item, index) => (
          <div
            key={index}
            style={{
              display: 'flex',
              justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 12,
            }}
          >
            <div
              className={item.role === 'assistant' ? 'agent-markdown' : undefined}
              style={
                item.role === 'user'
                  ? {
                      background: 'var(--color-primary, #5645d4)',
                      color: '#fff',
                      borderRadius: 12,
                      padding: '8px 12px',
                      maxWidth: '80%',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }
                  : {
                      background: '#fff',
                      border: '1px solid #eee',
                      borderRadius: 12,
                      padding: '8px 12px',
                      maxWidth: '88%',
                      wordBreak: 'break-word',
                    }
              }
            >
              {item.role === 'assistant' ? (
                <ReactMarkdown>{item.content || '…'}</ReactMarkdown>
              ) : (
                item.content
              )}
            </div>
          </div>
        ))}
        {streaming && (streamStatus || thinking) && (
          <div
            style={{
              border: '1px dashed #d9d9d9',
              borderRadius: 8,
              background: '#fff',
              padding: '8px 12px',
              marginBottom: 8,
              fontSize: 12,
              color: 'var(--color-steel)',
            }}
          >
            {streamStatus && <div style={{ marginBottom: thinking ? 6 : 0 }}>{streamStatus}</div>}
            {thinking && (
              <details open>
                <summary style={{ cursor: 'pointer', userSelect: 'none' }}>思考过程（点击收起）</summary>
                <div
                  style={{
                    marginTop: 4,
                    maxHeight: 140,
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    lineHeight: 1.6,
                  }}
                >
                  {thinking}
                </div>
              </details>
            )}
          </div>
        )}
      </div>
      <div style={{ borderTop: '1px solid #eee', padding: 12 }}>
        <Input.TextArea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="向 AI 助手提问，例如：2026年哪个产品杂质异常最多？"
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={streaming}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault()
              void send()
            }
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={streaming}
            onClick={() => void send()}
          >
            发送
          </Button>
        </div>
      </div>
    </Drawer>
  )
}
