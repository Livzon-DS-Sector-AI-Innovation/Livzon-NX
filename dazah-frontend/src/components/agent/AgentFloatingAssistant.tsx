"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  FileImageOutlined,
  FileTextOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  HistoryOutlined,
  LoadingOutlined,
  MessageOutlined,
  MinusOutlined,
  PaperClipOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from "@ant-design/icons"
import { Alert, App, Badge, Button, Drawer, Empty, Input, List, Skeleton, Tag, Tooltip } from "antd"
import { BusinessMessageContent } from "@/components/agent/BusinessMessageContent"
import type { AgentArtifact } from "@/components/agent/AutomationArtifacts"
import {
  archiveAgentSession,
  cancelAgentConfirmation,
  executeAgentConfirmation,
  fetchAgentSession,
  fetchAgentSessions,
  streamAgentMessage,
  type AgentAttachmentInput,
  type AgentChatData,
  type AgentConfirmation,
  type AgentMessage,
  type AgentSessionItem,
} from "@/lib/api/agent"
import { useAgentStore } from "@/stores/agent"

const suggestions = [
  "查询质量偏差报告记录",
  "查看飞书同步状态",
  "查询原辅料库存",
  "查看待审批采购申请",
]

const ASSISTANT_EXIT_ANIMATION_MS = 180
const MAX_ATTACHMENT_COUNT = 5
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
const MAX_ATTACHMENTS_TOTAL_BYTES = 20 * 1024 * 1024
const ATTACHMENT_ACCEPT =
  ".pdf,.docx,.xlsx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp,.gif"

const attachmentContentTypes: Record<string, string> = {
  ".pdf": "application/pdf",
  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ".txt": "text/plain",
  ".md": "text/markdown",
  ".csv": "text/csv",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
}

type SelectedAttachment = AgentAttachmentInput & {
  kind: "image" | "document"
}

type AttachmentDescriptor = Omit<SelectedAttachment, "data_base64">

type AgentFileArtifact = {
  kind: "file"
  filename: string
  content_type: string
  base64: string
}

function riskColor(risk: string) {
  if (risk === "high") return "red"
  if (risk === "low") return "green"
  return "orange"
}

function humanizeConfirmationError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "")
  if (/Internal Server Error/i.test(message)) {
    return "操作执行后返回结果失败，请刷新确认状态；如果仍未完成，请稍后重试。"
  }
  if (/confirmation has expired/i.test(message)) return "该确认已过期，请重新发起操作。"
  if (/confirmation is not pending/i.test(message)) return "该操作已处理，无需重复确认。"
  return message || "确认执行失败，请稍后重试。"
}

function confirmationExpiryLabel(expiresAt: string) {
  const expiry = new Date(expiresAt)
  if (Number.isNaN(expiry.getTime())) return "待确认"
  return `有效至 ${expiry.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function fileArtifactFromResult(data: unknown): AgentFileArtifact | null {
  if (!isRecord(data) || !isRecord(data.artifact)) return null
  const artifact = data.artifact
  if (
    artifact.kind !== "file" ||
    typeof artifact.filename !== "string" ||
    typeof artifact.content_type !== "string" ||
    typeof artifact.base64 !== "string"
  ) {
    return null
  }
  return {
    kind: "file",
    filename: artifact.filename,
    content_type: artifact.content_type,
    base64: artifact.base64,
  }
}

function confirmationFromRecord(confirmation: Record<string, unknown>): AgentConfirmation | null {
  if (
    typeof confirmation.id !== "string" ||
    typeof confirmation.operation !== "string" ||
    typeof confirmation.summary !== "string" ||
    typeof confirmation.risk_level !== "string" ||
    typeof confirmation.status !== "string" ||
    typeof confirmation.expires_at !== "string"
  ) {
    return null
  }
  return {
    id: confirmation.id,
    operation: confirmation.operation,
    summary: confirmation.summary,
    risk_level: confirmation.risk_level,
    status: confirmation.status,
    expires_at: confirmation.expires_at,
    request_payload: isRecord(confirmation.request_payload)
      ? confirmation.request_payload
      : undefined,
  }
}

function formatFileSize(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
}

function attachmentExtension(filename: string) {
  const index = filename.lastIndexOf(".")
  return index >= 0 ? filename.slice(index).toLowerCase() : ""
}

function attachmentDescriptors(metadata?: Record<string, unknown>): AttachmentDescriptor[] {
  const value = metadata?.attachments
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (
      !isRecord(item) ||
      typeof item.filename !== "string" ||
      typeof item.content_type !== "string" ||
      typeof item.size !== "number" ||
      (item.kind !== "image" && item.kind !== "document")
    ) {
      return []
    }
    return [{
      filename: item.filename,
      content_type: item.content_type,
      size: item.size,
      kind: item.kind,
    }]
  })
}

async function fileToBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer())
  const chunkSize = 32_768
  let binary = ""
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
  }
  return window.btoa(binary)
}

function collectConfirmations(value: unknown): AgentConfirmation[] {
  const confirmations: AgentConfirmation[] = []
  const seen = new Set<string>()

  function add(confirmation: AgentConfirmation) {
    if (seen.has(confirmation.id)) return
    seen.add(confirmation.id)
    confirmations.push(confirmation)
  }

  function visit(item: unknown) {
    if (typeof item === "string") {
      try {
        visit(JSON.parse(item) as unknown)
      } catch {
        return
      }
      return
    }
    if (Array.isArray(item)) {
      for (const child of item) visit(child)
      return
    }
    if (!isRecord(item)) return

    const direct = confirmationFromRecord(item)
    if (direct) add(direct)

    for (const key of [
      "confirmation",
      "confirmations",
      "pending_confirmation",
      "pending_confirmations",
      "data",
      "result",
      "meta",
    ]) {
      visit(item[key])
    }
  }

  visit(value)
  return confirmations
}

function downloadBase64File(artifact: AgentFileArtifact) {
  const binary = window.atob(artifact.base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  const blob = new Blob([bytes], { type: artifact.content_type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = artifact.filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function MessageBubble({
  message,
  streaming = false,
  onArtifactAction,
}: {
  message: AgentMessage
  streaming?: boolean
  onArtifactAction?: (artifact: AgentArtifact) => void
}) {
  const isUser = message.role === "user"
  const attachments = attachmentDescriptors(message.metadata)
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          "rounded-xl px-3 py-2 text-sm leading-6 shadow-sm",
          isUser
            ? "max-w-[86%] bg-[var(--color-primary)] text-white"
            : "agent-assistant-bubble max-w-[min(94%,720px)] border border-[var(--color-border)] bg-white text-[var(--color-text-primary)]",
        ].join(" ")}
      >
        {isUser ? (
          <div>
            {attachments.length > 0 && (
              <div className="mb-2 space-y-1.5">
                {attachments.map((attachment) => (
                  <div
                    key={`${attachment.filename}-${attachment.size}`}
                    className="flex items-center gap-2 rounded-lg bg-white/15 px-2 py-1.5"
                  >
                    {attachment.kind === "image" ? <FileImageOutlined /> : <FileTextOutlined />}
                    <span className="min-w-0 flex-1 truncate text-xs">{attachment.filename}</span>
                    <span className="shrink-0 text-[11px] text-white/75">
                      {formatFileSize(attachment.size)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        ) : (
          <BusinessMessageContent
            content={message.content}
            metadata={message.metadata}
            streaming={streaming}
            onArtifactAction={onArtifactAction}
          />
        )}
      </div>
    </div>
  )
}

function ConfirmationCard({
  confirmation,
  onExecute,
  onCancel,
}: {
  confirmation: AgentConfirmation
  onExecute: (confirmation: AgentConfirmation) => void
  onCancel: (confirmation: AgentConfirmation) => void
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-[var(--color-text-primary)]">
            {confirmation.summary}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Tag color={riskColor(confirmation.risk_level)}>
            {confirmation.risk_level === "high" ? "高风险" : confirmation.risk_level === "low" ? "低风险" : "中风险"}
          </Tag>
          <Tag color="warning">{confirmationExpiryLabel(confirmation.expires_at)}</Tag>
        </div>
      </div>
      <div className="mt-3 rounded-lg bg-[var(--color-bg-secondary)] px-3 py-2.5 text-sm leading-6 text-[var(--color-text-secondary)]">
        {confirmationNarrative(confirmation)}
      </div>
      <div className="mt-2 text-xs text-[var(--color-text-tertiary)]">
        请在有效期内完成确认；过期后需重新发起操作
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <Button
          size="small"
          icon={<StopOutlined />}
          onClick={() => onCancel(confirmation)}
        >
          取消
        </Button>
        <Button
          size="small"
          type="primary"
          icon={<CheckOutlined />}
          onClick={() => onExecute(confirmation)}
        >
          确认执行
        </Button>
      </div>
    </div>
  )
}

function businessPayloadOf(confirmation: AgentConfirmation) {
  const payload = confirmation.request_payload
  if (!payload) return {}
  if (isRecord(payload.body)) return payload.body
  if (isRecord(payload.params)) return payload.params
  return payload
}

function shortenedText(value: unknown, limit = 140) {
  if (typeof value !== "string") return ""
  const text = value.replace(/\s+/g, " ").trim()
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

function confirmationNarrative(confirmation: AgentConfirmation) {
  const payload = businessPayloadOf(confirmation)
  const recipientCount = Array.isArray(payload.user_ids) ? payload.user_ids.length : 0
  const title = shortenedText(payload.title, 60)
  const content = shortenedText(payload.markdown || payload.text)

  if (confirmation.operation === "identity.send_feishu_card_message") {
    return `将向 ${recipientCount || 1} 位已同步飞书用户发送卡片${title ? `《${title}》` : ""}${content ? `，内容：${content}` : ""}。`
  }
  if (confirmation.operation === "identity.send_feishu_text_message") {
    return `将向 ${recipientCount || 1} 位已同步飞书用户发送消息${content ? `：${content}` : ""}。`
  }
  if (confirmation.operation === "identity.send_feishu_message") {
    return `将向 ${recipientCount || 1} 位已同步飞书用户发送通知${title ? `《${title}》` : ""}${content ? `，内容：${content}` : ""}。`
  }
  if (confirmation.operation === "agent.run_automation") return "确认后将立即运行该自动化流程，并记录本次运行结果。"
  if (confirmation.operation === "agent.create_automation") return "确认后将创建并启用不含时间触发的自动化流程。"
  if (confirmation.operation === "agent.create_scheduled_task") return "确认后将按指定时间创建并启用定时任务。"
  if (confirmation.operation === "agent.set_automation_enabled") {
    return `确认后将${payload.enabled ? "启用" : "禁用"}该自动化流程。`
  }
  if (confirmation.operation === "agent.update_automation") return "确认后将保存该自动化流程的修改，并记录新版本。"
  return "确认后系统将执行上述操作，并保留完整审计记录。"
}

export function AgentFloatingAssistant() {
  const { message: toast } = App.useApp()
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const messageSequenceRef = useRef(0)
  const streamBufferRef = useRef("")
  const streamTimerRef = useRef<number | null>(null)
  const closeTimerRef = useRef<number | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [closing, setClosing] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [sessions, setSessions] = useState<AgentSessionItem[]>([])
  const [attachments, setAttachments] = useState<SelectedAttachment[]>([])
  const [attachmentReading, setAttachmentReading] = useState(false)
  const pendingStreamDoneRef = useRef<{
    messageId: string
    result: AgentChatData
    resolve: () => void
  } | null>(null)
  const {
    open,
    minimized,
    expanded,
    sessionId,
    messages,
    draft,
    pendingConfirmations,
    loading,
    error,
    setOpen,
    setMinimized,
    setExpanded,
    setSessionId,
    setDraft,
    setLoading,
    setError,
    addMessage,
    appendMessageContent,
    updateMessage,
    removeMessage,
    upsertConfirmation,
    removeConfirmation,
    setPendingConfirmations,
    loadConversation,
    startNewConversation,
  } = useAgentStore()

  const clearStreamTimer = useCallback(() => {
    if (streamTimerRef.current !== null) {
      window.clearTimeout(streamTimerRef.current)
      streamTimerRef.current = null
    }
  }, [])

  function completePendingStreamDone() {
    const pending = pendingStreamDoneRef.current
    if (!pending || streamBufferRef.current) return
    setSessionId(pending.result.session_id)
    updateMessage(pending.messageId, pending.result.message)
    pending.resolve()
    pendingStreamDoneRef.current = null
  }

  function scheduleStreamFlush(messageId: string, onDisplay?: () => void) {
    if (streamTimerRef.current !== null) return

    const flush = () => {
      const queued = streamBufferRef.current
      if (!queued) {
        streamTimerRef.current = null
        completePendingStreamDone()
        return
      }

      const take = queued.length > 120 ? 8 : queued.length > 48 ? 4 : 2
      const nextText = queued.slice(0, take)
      streamBufferRef.current = queued.slice(take)
      appendMessageContent(messageId, nextText)
      onDisplay?.()

      const delay = queued.length > 120 ? 18 : queued.length > 48 ? 22 : 26
      streamTimerRef.current = window.setTimeout(flush, delay)
    }

    streamTimerRef.current = window.setTimeout(flush, 24)
  }

  const resetStreamBuffer = useCallback((resolvePending = false) => {
    clearStreamTimer()
    streamBufferRef.current = ""
    if (resolvePending && pendingStreamDoneRef.current) {
      pendingStreamDoneRef.current.resolve()
      pendingStreamDoneRef.current = null
    }
  }, [clearStreamTimer])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, pendingConfirmations.length, loading])

  useEffect(() => {
    return () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current)
      }
      abortControllerRef.current?.abort()
      resetStreamBuffer(true)
    }
  }, [resetStreamBuffer])

  useEffect(() => {
    if (!open || !sessionId || loading) return
    const refresh = async () => {
      try {
        const detail = await fetchAgentSession(sessionId)
        setPendingConfirmations((detail.confirmations ?? []) as AgentConfirmation[])
      } catch {
        // Keep the current conversation usable during a transient refresh failure.
      }
    }
    const intervalId = window.setInterval(() => void refresh(), 15000)
    return () => window.clearInterval(intervalId)
  }, [loading, open, sessionId, setPendingConfirmations])

  useEffect(() => {
    const timeoutIds = pendingConfirmations.map((confirmation) => window.setTimeout(
      () => removeConfirmation(confirmation.id),
      Math.max(0, new Date(confirmation.expires_at).getTime() - Date.now()),
    ))
    return () => timeoutIds.forEach((timeoutId) => window.clearTimeout(timeoutId))
  }, [pendingConfirmations, removeConfirmation])

  function hideAssistant(nextState: "closed" | "minimized") {
    if (closing) return
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches

    if (prefersReducedMotion) {
      if (nextState === "closed") {
        setOpen(false)
      } else {
        setMinimized(true)
      }
      return
    }

    setClosing(true)
    closeTimerRef.current = window.setTimeout(() => {
      closeTimerRef.current = null
      setClosing(false)
      if (nextState === "closed") {
        setOpen(false)
      } else {
        setMinimized(true)
      }
    }, ASSISTANT_EXIT_ANIMATION_MS)
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) {
        hideAssistant("minimized")
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  })

  function stopStreaming() {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    resetStreamBuffer(true)
    setStreaming(false)
    setLoading(false)
  }

  async function handleAttachmentSelection(files: FileList | null) {
    if (!files?.length) return
    setAttachmentReading(true)
    try {
      const next = [...attachments]
      let totalBytes = next.reduce((sum, attachment) => sum + attachment.size, 0)
      for (const file of Array.from(files)) {
        if (next.length >= MAX_ATTACHMENT_COUNT) {
          toast.warning(`每次最多添加 ${MAX_ATTACHMENT_COUNT} 个附件`)
          break
        }
        const extension = attachmentExtension(file.name)
        const contentType = attachmentContentTypes[extension]
        if (!contentType) {
          toast.error(`不支持 ${file.name}，请选择文档或 PNG、JPG、WebP 图片`)
          continue
        }
        if (file.size > MAX_ATTACHMENT_BYTES) {
          toast.error(`${file.name} 超过单个文件 10 MB 限制`)
          continue
        }
        if (totalBytes + file.size > MAX_ATTACHMENTS_TOTAL_BYTES) {
          toast.error("附件总大小不能超过 20 MB")
          break
        }
        if (next.some((item) => item.filename === file.name && item.size === file.size)) {
          toast.info(`${file.name} 已添加`)
          continue
        }
        next.push({
          filename: file.name,
          content_type: contentType,
          size: file.size,
          data_base64: await fileToBase64(file),
          kind: contentType.startsWith("image/") ? "image" : "document",
        })
        totalBytes += file.size
      }
      setAttachments(next)
    } catch {
      toast.error("读取附件失败，请重新选择")
    } finally {
      setAttachmentReading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  async function handleNewConversation() {
    if (loading && !streaming) return
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    resetStreamBuffer(true)
    setStreaming(false)
    setAttachments([])
    if (sessionId) {
      try {
        await archiveAgentSession(sessionId)
      } catch {
        // Archiving is best effort; starting a fresh session must remain available.
      }
    }
    startNewConversation()
    window.requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: 0 })
    })
  }

  async function submit(text?: string) {
    const content = (text ?? draft).trim() || (attachments.length ? "请分析这些附件" : "")
    if (!content || loading || attachmentReading) return
    const submittedAttachments = attachments
    abortControllerRef.current?.abort()
    const abortController = new AbortController()
    abortControllerRef.current = abortController
    setStreaming(true)
    setError(null)
    setDraft("")
    setAttachments([])
    addMessage({
      role: "user",
      content,
      metadata: {
        attachments: submittedAttachments.map((attachment) => ({
          filename: attachment.filename,
          content_type: attachment.content_type,
          size: attachment.size,
          kind: attachment.kind,
        })),
      },
    })
    messageSequenceRef.current += 1
    const assistantMessageId = `stream-${messageSequenceRef.current}`
    let hasReceivedContent = false
    let hasDisplayedContent = false
    let doneFlushPromise: Promise<void> | null = null
    resetStreamBuffer(true)
    addMessage({ id: assistantMessageId, role: "assistant", content: "" })
    setLoading(true)
    try {
      await streamAgentMessage(
        {
          session_id: sessionId,
          message: content,
          context: { entry: "floating-assistant", scope: ["identity", "warehouse", "procurement", "quality"] },
          attachments: submittedAttachments.map((attachment) => ({
            filename: attachment.filename,
            content_type: attachment.content_type,
            size: attachment.size,
            data_base64: attachment.data_base64,
          })),
        },
        {
          onStart: (data) => {
            if (data.session_id) setSessionId(data.session_id)
          },
          onDelta: (text) => {
            if (!text) return
            hasReceivedContent = true
            streamBufferRef.current += text
            scheduleStreamFlush(assistantMessageId, () => {
              hasDisplayedContent = true
            })
          },
          onDone: (result) => {
            for (const confirmation of collectConfirmations(result)) {
              upsertConfirmation(confirmation)
            }
            doneFlushPromise = new Promise((resolve) => {
              pendingStreamDoneRef.current = {
                messageId: assistantMessageId,
                result,
                resolve,
              }
              scheduleStreamFlush(assistantMessageId, () => {
                hasDisplayedContent = true
              })
              completePendingStreamDone()
            })
          },
        },
        { signal: abortController.signal },
      )
      if (doneFlushPromise) {
        await doneFlushPromise
      }
    } catch (err) {
      if (abortController.signal.aborted) {
        resetStreamBuffer(true)
        if (!hasReceivedContent || !hasDisplayedContent) {
          removeMessage(assistantMessageId)
        }
        return
      }
      resetStreamBuffer(true)
      if (!hasReceivedContent || !hasDisplayedContent) {
        removeMessage(assistantMessageId)
      }
      setError(err instanceof Error ? err.message : "中枢助手请求失败")
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null
      }
      setStreaming(false)
      setLoading(false)
    }
  }

  async function executeConfirmation(confirmation: AgentConfirmation) {
    setLoading(true)
    setError(null)
    try {
      const result = await executeAgentConfirmation(confirmation.id)
      upsertConfirmation(result.confirmation)
      const artifact = fileArtifactFromResult(result.result.data)
      const nextConfirmations = collectConfirmations(result.result)
      const nextPendingConfirmation = nextConfirmations.find(
        (item) => item.status === "pending",
      )
      if (artifact) {
        downloadBase64File(artifact)
      }
      for (const nextConfirmation of nextConfirmations) {
        upsertConfirmation(nextConfirmation)
      }
      addMessage({
        role: "assistant",
        content: artifact
          ? `已生成合同：${artifact.filename}，已开始下载。`
          : nextPendingConfirmation
            ? `已执行：${result.confirmation.summary}。自动化流程已暂停，等待确认：${nextPendingConfirmation.summary}`
            : `已执行：${result.confirmation.summary}`,
        metadata: { result: result.result },
      })
    } catch (err) {
      setError(humanizeConfirmationError(err))
    } finally {
      setLoading(false)
    }
  }

  async function cancelConfirmation(confirmation: AgentConfirmation) {
    setLoading(true)
    setError(null)
    try {
      const result = await cancelAgentConfirmation(confirmation.id)
      upsertConfirmation(result)
      addMessage({ role: "assistant", content: `已取消：${result.summary}` })
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消确认失败")
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <Button
        aria-label="打开中枢助手"
        title="Livzon助手"
        type="primary"
        shape="circle"
        icon={<RobotOutlined />}
        onClick={() => setOpen(true)}
        className="agent-floating-entry-button !fixed !bottom-6 !right-6 !z-50 !h-14 !w-14 !shadow-lg"
      />
    )
  }

  async function openHistory() {
    setHistoryOpen(true)
    setHistoryLoading(true)
    try {
      const result = await fetchAgentSessions()
      setSessions(result.items ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载历史会话失败")
    } finally {
      setHistoryLoading(false)
    }
  }

  async function restoreSession(id: string) {
    setHistoryLoading(true)
    try {
      const detail = await fetchAgentSession(id)
      loadConversation({
        sessionId: detail.session.id,
        messages: (detail.messages ?? []) as AgentMessage[],
        confirmations: (detail.confirmations ?? []) as AgentConfirmation[],
      })
      setHistoryOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "恢复历史会话失败")
    } finally {
      setHistoryLoading(false)
    }
  }

  function handleArtifactAction(artifact: AgentArtifact) {
    const prompt = artifact.type === "automation_list"
      ? "刷新并展示我的自动化列表"
      : artifact.type === "automation_detail"
        ? `查看自动化 ${artifact.automationId} 的详情`
        : artifact.type === "run_timeline"
          ? `查看运行 ${artifact.runId ?? "最近一次"} 的进度和失败原因`
          : artifact.type === "push_delivery_list"
            ? "查看这组自动化的投递记录"
            : artifact.type === "audit_diff"
              ? `查看自动化 ${artifact.auditId} 的修改记录`
              : `查看确认项 ${artifact.confirmationId} 的参数和状态`
    void submit(prompt)
  }

  if (minimized) {
    return (
      <Button
        aria-label="展开中枢助手"
        title="Livzon助手"
        type="primary"
        shape="circle"
        icon={<MessageOutlined />}
        onClick={() => setMinimized(false)}
        className="agent-floating-entry-button !fixed !bottom-6 !right-6 !z-50 !h-14 !w-14 !shadow-lg"
      />
    )
  }

  return (
    <section
      className={[
        "agent-floating-assistant",
        expanded ? "agent-floating-assistant-expanded" : "",
        closing ? "agent-floating-assistant-closing" : "",
      ].join(" ")}
    >
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] px-4">
        <div className="flex items-center gap-3">
          <Badge status="success" />
          <div>
            <div className="text-sm font-semibold text-[var(--color-text-primary)]">Livzon助手</div>
          </div>
        </div>
        <div className="flex gap-1">
          <Tooltip title="历史会话">
            <Button
              aria-label="查看历史会话"
              type="text"
              icon={<HistoryOutlined />}
              onClick={() => void openHistory()}
            />
          </Tooltip>
          <Tooltip title="新对话">
            <Button
              aria-label="开启新对话"
              title="新对话"
              type="text"
              icon={<PlusOutlined />}
              disabled={loading && !streaming}
              onClick={() => void handleNewConversation()}
            />
          </Tooltip>
          <Tooltip title={expanded ? "还原" : "放大"}>
            <Button
              aria-label={expanded ? "还原 Livzon助手" : "放大 Livzon助手"}
              type="text"
              icon={expanded ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={() => setExpanded(!expanded)}
            />
          </Tooltip>
          <Button aria-label="最小化中枢助手" type="text" icon={<MinusOutlined />} onClick={() => hideAssistant("minimized")} />
          <Button aria-label="关闭中枢助手" type="text" icon={<CloseOutlined />} onClick={() => hideAssistant("closed")} />
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="space-y-3">
            <div className="rounded-xl border border-[var(--color-border)] bg-white p-3 text-sm text-[var(--color-text-secondary)] shadow-sm">
              Livzon 助手可查询业务数据、同步状态与流程进展；创建、同步、发送等写操作会先生成确认卡。
            </div>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((item) => (
                <Button key={item} size="small" onClick={() => submit(item)}>
                  {item}
                </Button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id ?? `${message.role}-${index}`}
            message={message}
            streaming={loading && message.id?.startsWith("stream-")}
            onArtifactAction={handleArtifactAction}
          />
        ))}
        {pendingConfirmations.map((confirmation) => (
          <ConfirmationCard
            key={confirmation.id}
            confirmation={confirmation}
            onExecute={executeConfirmation}
            onCancel={cancelConfirmation}
          />
        ))}
        {loading && messages[messages.length - 1]?.role !== "assistant" && (
          <div className="rounded-xl border border-[var(--color-border)] bg-white p-3">
            <Skeleton active paragraph={{ rows: 2 }} title={false} />
          </div>
        )}
        {error && <Alert type="error" showIcon title={error} />}
      </div>

      <footer className="shrink-0 border-t border-[var(--color-border)] bg-white p-3">
        <input
          ref={fileInputRef}
          className="hidden"
          type="file"
          multiple
          accept={ATTACHMENT_ACCEPT}
          onChange={(event) => void handleAttachmentSelection(event.target.files)}
        />
        {attachments.length > 0 && (
          <div className="mb-2 space-y-1.5" aria-label="待发送附件">
            {attachments.map((attachment, index) => (
              <div
                key={`${attachment.filename}-${attachment.size}`}
                className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] px-2 py-1.5"
              >
                {attachment.kind === "image" ? <FileImageOutlined /> : <FileTextOutlined />}
                <span className="min-w-0 flex-1 truncate text-xs text-[var(--color-text-primary)]">
                  {attachment.filename}
                </span>
                <span className="shrink-0 text-[11px] text-[var(--color-text-tertiary)]">
                  {formatFileSize(attachment.size)}
                </span>
                <Button
                  aria-label={`移除附件 ${attachment.filename}`}
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  disabled={loading}
                  onClick={() => setAttachments((items) => items.filter((_, itemIndex) => itemIndex !== index))}
                />
              </div>
            ))}
          </div>
        )}
        <Input.TextArea
          aria-label="中枢助手输入框"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          autoSize={{ minRows: 2, maxRows: 5 }}
          placeholder="请输入您的需求，Shift + Enter 换行"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between gap-2">
          <Tooltip title="支持 PDF、DOCX、XLSX、TXT、Markdown、CSV 和图片；单个 10 MB，合计 20 MB">
            <Button
              icon={attachmentReading ? <LoadingOutlined /> : <PaperClipOutlined />}
              disabled={loading || attachmentReading || attachments.length >= MAX_ATTACHMENT_COUNT}
              onClick={() => fileInputRef.current?.click()}
            >
              添加文件
            </Button>
          </Tooltip>
          <div className="flex gap-2">
            {loading && (
              <Button
                danger
                icon={<StopOutlined />}
                onClick={stopStreaming}
              >
                停止
              </Button>
            )}
            <Button
              type="primary"
              icon={loading || attachmentReading ? <LoadingOutlined /> : <SendOutlined />}
              disabled={(!draft.trim() && attachments.length === 0) || loading || attachmentReading}
              onClick={() => submit()}
            >
              发送
            </Button>
          </div>
        </div>
      </footer>
      <Drawer
        title="历史会话"
        placement="right"
        size={420}
        open={historyOpen}
        loading={historyLoading}
        onClose={() => setHistoryOpen(false)}
      >
        {sessions.length ? (
          <List
            dataSource={sessions}
            renderItem={(item) => (
              <List.Item
                className="!items-start"
                actions={[
                  <Button key="restore" type="link" onClick={() => void restoreSession(item.id)}>
                    继续对话
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={item.title || "未命名对话"}
                  description={(
                    <div className="space-y-1">
                      <div className="line-clamp-2">{item.last_message_preview || "暂无消息摘要"}</div>
                      <div className="text-xs text-[var(--color-text-tertiary)]">
                        {item.channel === "feishu" ? "飞书" : "Web"} · {item.message_count} 条消息 · {new Date(item.updated_at).toLocaleString()}
                      </div>
                      {item.pending_confirmation_count > 0 && (
                        <Tag color="warning">{item.pending_confirmation_count} 项待确认</Tag>
                      )}
                    </div>
                  )}
                />
              </List.Item>
            )}
          />
        ) : (
          !historyLoading && <Empty description="还没有历史会话" />
        )}
      </Drawer>
    </section>
  )
}
