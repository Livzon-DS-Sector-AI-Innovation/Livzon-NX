'use client'

/** 应急预案 AI 工作台。

左侧章节目录（含问题计数）、中部纸张视图编辑（封面/组织机构/章节正文）、
右侧 AI 助手（流式对话，可直接修改正文）、审核报告与修订记录三个页签；
AI 生成/审核任务运行时轮询进度并锁定编辑。数据形态见 emergencyPlanModel。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import {
  App,
  Button,
  Input,
  Modal,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
} from 'antd'
import {
  CheckCircleOutlined,
  FileWordOutlined,
  RollbackOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'

import {
  fetchEmergencyPlanChatMessages,
  fetchEmergencyPlanContent,
  fetchEmergencyPlanDocxBytes,
  fetchEmergencyPlanRevision,
  fetchEmergencyPlanRevisions,
  finalizeEmergencyPlan,
  restoreEmergencyPlanRevision,
  saveEmergencyPlanContent,
  submitEmergencyPlanReview,
} from '@/actions/safety'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import { streamEmergencyPlanChat } from '@/lib/api/safety-emergency-plan-chat'
import {
  normalizePlanContent,
  planDocumentToPayload,
  type PlanContentPayload,
  type PlanDocument,
} from './emergencyPlanModel'

const PAGE_KEY = 'safety:emergency-accident:emergency-mgmt'

const STATUS_META: Record<string, { color: string; label: string }> = {
  empty: { color: 'default', label: '无正文' },
  draft: { color: 'orange', label: '草稿' },
  reviewed: { color: 'blue', label: 'AI 已审核' },
  finalized: { color: 'green', label: '已定稿' },
}

const SOURCE_LABELS: Record<string, string> = {
  ai_generate: 'AI 生成',
  ai_fix: 'AI 审核修正',
  ai_chat: 'AI 对话修改',
  user_edit: '人工编辑',
  import: '导入',
  restore: '恢复修订',
}

const ISSUE_STATUS_META: Record<string, { color: string; label: string }> = {
  fixed: { color: 'green', label: '已自动修正' },
  needs_human: { color: 'red', label: '需人工补充' },
  unresolved: { color: 'orange', label: '提示' },
  info: { color: 'blue', label: '说明' },
}

interface ChatItem {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

const QUICK_ACTIONS = [
  { label: '改写本章', prefix: '请改写当前聚焦章节，使其更规范流畅，其他章节不变。' },
  { label: '扩写本章', prefix: '请扩写当前聚焦章节，补充必要细节，不得编造人员与数值。' },
  { label: '精简本章', prefix: '请精简当前聚焦章节，去除冗余表述。' },
  { label: '重新生成本章', prefix: '请重新生成当前聚焦章节的完整正文。' },
  { label: '检查本章', prefix: '请检查当前聚焦章节的问题并直接修正。' },
]

function downloadDocx(base64: string, fileName: string): void {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  const url = URL.createObjectURL(
    new Blob([bytes], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
  )
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

function formatTime(value: string | undefined): string {
  if (!value) return ''
  return value.replace('T', ' ').slice(0, 19)
}

export default function EmergencyPlanWorkbench({
  planId,
  planName,
  onBackHref,
}: {
  planId: string
  planName: string
  onBackHref?: string
}) {
  const { canOperate } = usePagePermissions(PAGE_KEY)
  const { message, modal } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<PlanContentPayload | null>(null)
  const [document, setDocument] = useState<PlanDocument | null>(null)
  const [activeSection, setActiveSection] = useState('preface')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [jobProgress, setJobProgress] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [submittingReview, setSubmittingReview] = useState(false)
  const [finalizeOpen, setFinalizeOpen] = useState(false)
  const [chat, setChat] = useState<ChatItem[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSending, setChatSending] = useState(false)
  const [lastChatRevision, setLastChatRevision] = useState<{
    revision: number
    previous: number
  } | null>(null)
  const [revisions, setRevisions] = useState<
    {
      id: string
      revision_no: number
      source: string
      summary: string
      created_at?: string
    }[]
  >([])
  const [revisionDetail, setRevisionDetail] = useState<{
    revision_no: number
    source: string
    summary: string
    changed_sections: string[]
    changes: { section: string; reason: string; before: string; after: string }[]
  } | null>(null)
  const chatEndRef = useRef<HTMLDivElement | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const applyPayload = useCallback((payload: PlanContentPayload) => {
    setData(payload)
    setDocument(payload.content)
    setDirty(false)
    if (payload.job?.state === 'running') {
      setJobProgress(payload.job.progress || '任务运行中…')
    } else {
      setJobProgress(null)
    }
  }, [])

  /** 重新拉取最新正文（保存冲突时由用户确认触发）。 */
  const loadContent = useCallback(async () => {
    const res = await fetchEmergencyPlanContent(planId)
    if (res.code !== 200) {
      message.error(res.message || '加载预案失败')
      return
    }
    applyPayload(normalizePlanContent(res.data) as PlanContentPayload)
  }, [planId, applyPayload, message])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchEmergencyPlanContent(planId),
      fetchEmergencyPlanChatMessages(planId),
    ]).then(([res, history]) => {
      if (cancelled) return
      if (res.code !== 200) {
        setError(res.message || '加载预案失败')
        setLoading(false)
        return
      }
      applyPayload(normalizePlanContent(res.data) as PlanContentPayload)
      setError(null)
      setLoading(false)
      if (history.code === 200 && history.data) {
        setChat(
          history.data.items.map((item) => ({
            role: item.role as 'user' | 'assistant',
            content: item.content,
          }))
        )
      }
    })
    return () => {
      cancelled = true
    }
  }, [planId, applyPayload])

  // 后台任务轮询：运行中每 2 秒查一次，结束/失败时刷新正文
  useEffect(() => {
    if (jobProgress === null) {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      return undefined
    }
    const timer = setInterval(async () => {
      const res = await fetchEmergencyPlanContent(planId)
      if (res.code !== 200) return
      const payload = normalizePlanContent(res.data) as PlanContentPayload
      if (payload.job?.state === 'running') {
        setJobProgress(payload.job.progress || '任务运行中…')
        return
      }
      if (payload.job?.state === 'failed') {
        message.error(payload.job.progress || 'AI 任务失败，请重试')
      } else if (payload.revision_no > (data?.revision_no ?? 0)) {
        message.success('AI 任务完成，已更新预案正文')
      }
      applyPayload(payload)
    }, 2000)
    pollRef.current = timer
    return () => {
      clearInterval(timer)
      pollRef.current = null
    }
  }, [jobProgress, planId, data?.revision_no, applyPayload, message])

  const chapters = document?.chapters ?? []
  const issueCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const issue of data?.last_review?.issues ?? []) {
      if (issue.status === 'fixed') continue
      counts[issue.section] = (counts[issue.section] ?? 0) + 1
    }
    return counts
  }, [data?.last_review])

  const updateDocument = (updater: (draft: PlanDocument) => PlanDocument) => {
    setDocument((prev) => (prev ? updater(prev) : prev))
    setDirty(true)
  }

  const handleSave = useCallback(async () => {
    if (!document || !data) return
    setSaving(true)
    try {
      const res = await saveEmergencyPlanContent(
        planId,
        planDocumentToPayload(document),
        data.revision_no
      )
      if (res.code === 200 && res.data) {
        applyPayload(normalizePlanContent(res.data) as PlanContentPayload)
        message.success('已保存')
      } else if (res.code === 409) {
        modal.confirm({
          title: '正文已被其他修改更新',
          content: '是否加载最新版本？未保存的修改将被覆盖。',
          okText: '加载最新',
          onOk: () => loadContent(),
        })
      } else {
        message.error(res.message || '保存失败')
      }
    } finally {
      setSaving(false)
    }
  }, [document, data, planId, applyPayload, loadContent, message, modal])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        if (dirty && !saving && canOperate && !jobProgress) handleSave()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [dirty, saving, canOperate, jobProgress, handleSave])

  const handleExport = async () => {
    setExporting(true)
    try {
      const result = await fetchEmergencyPlanDocxBytes(planId)
      downloadDocx(result.base64, result.fileName)
      message.success('已导出 Word')
    } catch (exportError) {
      message.error(exportError instanceof Error ? exportError.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  const handleReview = async () => {
    setSubmittingReview(true)
    try {
      const res = await submitEmergencyPlanReview(planId)
      if (res.code === 200 || res.code === 202) {
        setJobProgress('AI 正在审阅修正…')
      } else {
        message.error(res.message || '提交审核任务失败')
      }
    } finally {
      setSubmittingReview(false)
    }
  }

  const handleFinalize = async () => {
    const res = await finalizeEmergencyPlan(planId)
    if (res.code === 200 && res.data) {
      applyPayload(normalizePlanContent(res.data) as PlanContentPayload)
      message.success('已定稿')
    } else {
      message.error(res.message || '定稿失败')
    }
    setFinalizeOpen(false)
  }

  const loadRevisions = useCallback(async () => {
    const res = await fetchEmergencyPlanRevisions(planId)
    if (res.code === 200 && res.data) {
      setRevisions(
        res.data.items.map((item) => ({
          id: item.id,
          revision_no: item.revision_no,
          source: item.source,
          summary: item.summary,
          created_at: item.created_at,
        }))
      )
    }
  }, [planId])

  const handleRestore = async (revisionNo: number) => {
    const res = await restoreEmergencyPlanRevision(planId, revisionNo)
    if (res.code === 200 && res.data) {
      applyPayload(normalizePlanContent(res.data) as PlanContentPayload)
      message.success(`已恢复到修订 ${revisionNo}`)
      await loadRevisions()
    } else {
      message.error(res.message || '恢复失败')
    }
  }

  const sendChat = async (rawInput: string) => {
    const text = rawInput.trim()
    if (!text || chatSending) return
    setChatSending(true)
    setChatInput('')
    setChat((prev) => [
      ...prev,
      { role: 'user', content: text },
      { role: 'assistant', content: '', streaming: true },
    ])
    const currentRevision = data?.revision_no ?? 0
    let revisionApplied = false
    const replaceLast = (content: string) => {
      setChat((prev) => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', content }
        return next
      })
    }
    try {
      await streamEmergencyPlanChat(
        planId,
        text,
        activeSection === 'preface' ? null : activeSection,
        {
          onReply: replaceLast,
          onRevision: (revision) => {
            revisionApplied = true
            setLastChatRevision({ revision, previous: currentRevision })
          },
          onContent: (payload) => {
            const normalized = normalizePlanContent(payload)
            if (normalized) applyPayload(normalized)
          },
          onMessage: replaceLast,
        }
      )
    } catch (chatError) {
      replaceLast(
        chatError instanceof Error ? chatError.message : '对话失败，请重试'
      )
    } finally {
      setChatSending(false)
      setTimeout(
        () => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }),
        50
      )
      if (revisionApplied) await loadRevisions()
    }
  }

  const statusMeta =
    STATUS_META[data?.content_status ?? 'empty'] ?? STATUS_META.empty
  const readonly = !canOperate || jobProgress !== null

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin tip="加载预案中…" />
      </div>
    )
  }
  if (error || !data) {
    return (
      <div style={{ padding: 32, color: 'rgba(0,0,0,0.65)' }}>
        {error ?? '预案不存在'}
      </div>
    )
  }

  const sections = [
    { key: 'preface', title: '引言' },
    ...chapters.map((chapter) => ({ key: chapter.key, title: chapter.title })),
  ]

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 12 }}
    >
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}
      >
        {onBackHref && (
          <Link href={onBackHref}>
            <Button>返回列表</Button>
          </Link>
        )}
        <span style={{ fontSize: 16, fontWeight: 600 }}>{planName}</span>
        <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
        <Tag>修订 {data.revision_no}</Tag>
        {data.ai_generated && (
          <Tag color="purple">
            <ThunderboltOutlined /> AI 参与生成
          </Tag>
        )}
        <Space style={{ marginLeft: 'auto' }}>
          {dirty && <Tag color="orange">未保存</Tag>}
          <Button
            disabled={readonly || !dirty || saving}
            loading={saving}
            onClick={handleSave}
          >
            保存 (Ctrl+S)
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={submittingReview}
            disabled={readonly || !document}
            onClick={handleReview}
          >
            AI 审核修正
          </Button>
          <Button
            icon={<FileWordOutlined />}
            loading={exporting}
            disabled={!document}
            onClick={handleExport}
          >
            导出 Word
          </Button>
          <Button
            icon={<CheckCircleOutlined />}
            disabled={readonly || !document || data.content_status === 'finalized'}
            onClick={() => setFinalizeOpen(true)}
          >
            定稿
          </Button>
        </Space>
      </div>

      {jobProgress && (
        <div
          style={{
            padding: '8px 16px',
            borderRadius: 8,
            background: 'rgba(123, 92, 224, 0.08)',
            color: '#5b3fb0',
          }}
        >
          <Spin size="small" /> AI 任务运行中：{jobProgress}
          （生成约需 2-4 分钟，期间不可编辑）
        </div>
      )}

      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
        <div
          style={{
            width: 200,
            flexShrink: 0,
            border: '1px solid rgba(0,0,0,0.08)',
            borderRadius: 10,
            padding: 8,
            overflowY: 'auto',
          }}
        >
          {sections.map((item) => (
            <div
              key={item.key}
              role="button"
              tabIndex={0}
              data-section-item={item.key}
              onClick={() => setActiveSection(item.key)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') setActiveSection(item.key)
              }}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '6px 10px',
                borderRadius: 6,
                cursor: 'pointer',
                background:
                  activeSection === item.key
                    ? 'rgba(123, 92, 224, 0.12)'
                    : 'transparent',
                fontWeight: activeSection === item.key ? 600 : 400,
              }}
            >
              <span
                style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {item.title}
              </span>
              {issueCounts[item.key] ? (
                <Tag color="orange" style={{ marginRight: 0 }}>
                  {issueCounts[item.key]}
                </Tag>
              ) : null}
            </div>
          ))}
        </div>

        <div
          style={{
            flex: 1,
            minWidth: 0,
            overflowY: 'auto',
            background: '#fff',
            border: '1px solid rgba(0,0,0,0.08)',
            borderRadius: 10,
            padding: 24,
          }}
        >
          {!document ? (
            <div
              style={{ textAlign: 'center', padding: 60, color: 'rgba(0,0,0,0.5)' }}
            >
              该预案还没有正文内容。可返回列表使用「AI 生成预案」或
              「导入预案文档」。
            </div>
          ) : (
            <div style={{ maxWidth: 760, margin: '0 auto' }}>
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 15, fontWeight: 600 }}>
                  {document.cover.company}
                </div>
                <div style={{ fontSize: 14, marginTop: 4 }}>
                  {document.cover.title}
                  {document.cover.level ? `（${document.cover.level}）` : ''}
                </div>
              </div>
              {activeSection === 'preface' && (
                <section>
                  <h3>引言</h3>
                  <Input.TextArea
                    autoSize={{ minRows: 4 }}
                    value={document.preface}
                    disabled={readonly}
                    onChange={(event) =>
                      updateDocument((draft) => ({
                        ...draft,
                        preface: event.target.value,
                      }))
                    }
                  />
                </section>
              )}
              {activeSection === 'organization' && (
                <section>
                  <h3>组织机构（结构化，正文自动同步）</h3>
                  <Space direction="vertical" style={{ width: '100%' }} size={6}>
                    <Input
                      addonBefore="总指挥"
                      value={document.organization.commander}
                      disabled={readonly}
                      onChange={(event) =>
                        updateDocument((draft) => ({
                          ...draft,
                          organization: {
                            ...draft.organization,
                            commander: event.target.value,
                          },
                        }))
                      }
                    />
                    <Input
                      addonBefore="副总指挥"
                      value={document.organization.deputy_commanders.join('、')}
                      disabled={readonly}
                      onChange={(event) =>
                        updateDocument((draft) => ({
                          ...draft,
                          organization: {
                            ...draft.organization,
                            deputy_commanders: event.target.value
                              .split(/[、,，]/)
                              .map((item) => item.trim())
                              .filter(Boolean),
                          },
                        }))
                      }
                    />
                    {document.organization.groups.map((group, index) => (
                      <Space.Compact
                        key={group.name}
                        style={{ display: 'flex', width: '100%' }}
                      >
                        <Input
                          style={{ width: 170 }}
                          value={group.name}
                          disabled={readonly}
                          onChange={(event) =>
                            updateDocument((draft) => ({
                              ...draft,
                              organization: {
                                ...draft.organization,
                                groups: draft.organization.groups.map(
                                  (item, itemIndex) =>
                                    itemIndex === index
                                      ? { ...item, name: event.target.value }
                                      : item
                                ),
                              },
                            }))
                          }
                        />
                        <Input
                          placeholder="组长"
                          value={group.leader}
                          disabled={readonly}
                          onChange={(event) =>
                            updateDocument((draft) => ({
                              ...draft,
                              organization: {
                                ...draft.organization,
                                groups: draft.organization.groups.map(
                                  (item, itemIndex) =>
                                    itemIndex === index
                                      ? { ...item, leader: event.target.value }
                                      : item
                                ),
                              },
                            }))
                          }
                        />
                        <Input
                          placeholder="成员"
                          value={group.members}
                          disabled={readonly}
                          onChange={(event) =>
                            updateDocument((draft) => ({
                              ...draft,
                              organization: {
                                ...draft.organization,
                                groups: draft.organization.groups.map(
                                  (item, itemIndex) =>
                                    itemIndex === index
                                      ? { ...item, members: event.target.value }
                                      : item
                                ),
                              },
                            }))
                          }
                        />
                      </Space.Compact>
                    ))}
                  </Space>
                </section>
              )}
              {chapters
                .filter((chapter) => chapter.key === activeSection)
                .map((chapter) =>
                  chapter.key === 'organization' ||
                  chapter.key === 'workshop_organization' ? null : (
                    <section key={chapter.key} data-section={chapter.key}>
                      <h3>{chapter.title}</h3>
                      <Input.TextArea
                        autoSize={{ minRows: 10, maxRows: 40 }}
                        value={chapter.content}
                        disabled={readonly}
                        onChange={(event) =>
                          updateDocument((draft) => ({
                            ...draft,
                            chapters: draft.chapters.map((item) =>
                              item.key === chapter.key
                                ? { ...item, content: event.target.value }
                                : item
                            ),
                          }))
                        }
                      />
                    </section>
                  )
                )}
            </div>
          )}
        </div>

        <div
          style={{
            width: 400,
            flexShrink: 0,
            border: '1px solid rgba(0,0,0,0.08)',
            borderRadius: 10,
            padding: '8px 12px',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }}
        >
          <Tabs
            size="small"
            items={[
              {
                key: 'chat',
                label: 'AI 助手',
                children: (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      height: 520,
                      gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {QUICK_ACTIONS.map((action) => (
                        <Button
                          key={action.label}
                          size="small"
                          data-quick-action={action.label}
                          disabled={readonly || chatSending}
                          onClick={() => sendChat(action.prefix)}
                        >
                          {action.label}
                        </Button>
                      ))}
                    </div>
                    <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
                      {chat.length === 0 && (
                        <div style={{ color: 'rgba(0,0,0,0.45)', padding: 12 }}>
                          可让 AI 修改正文，例如：“把情景三改成夜班发生”“补充
                          李四为警戒疏散组组长”。修改会生成新修订，可撤销。
                        </div>
                      )}
                      {chat.map((item, index) => (
                        <div
                          key={`${item.role}-${index}`}
                          data-chat-role={item.role}
                          style={{
                            marginBottom: 8,
                            textAlign: item.role === 'user' ? 'right' : 'left',
                          }}
                        >
                          <div
                            style={{
                              display: 'inline-block',
                              maxWidth: '92%',
                              padding: '6px 10px',
                              borderRadius: 8,
                              textAlign: 'left',
                              whiteSpace: 'pre-wrap',
                              fontSize: 13,
                              background:
                                item.role === 'user'
                                  ? 'rgba(123, 92, 224, 0.12)'
                                  : 'rgba(0,0,0,0.04)',
                            }}
                          >
                            {item.content || (item.streaming ? '思考中…' : '')}
                          </div>
                        </div>
                      ))}
                      <div ref={chatEndRef} />
                    </div>
                    {lastChatRevision && (
                      <div
                        data-chat-undo
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '4px 8px',
                          borderRadius: 6,
                          background: 'rgba(82, 196, 26, 0.1)',
                          fontSize: 12,
                        }}
                      >
                        AI 已修改正文（修订 {lastChatRevision.revision}）
                        <Button
                          size="small"
                          icon={<RollbackOutlined />}
                          disabled={readonly}
                          onClick={() => {
                            const target = lastChatRevision.previous
                            setLastChatRevision(null)
                            handleRestore(target)
                          }}
                        >
                          撤销本次 AI 修改
                        </Button>
                      </div>
                    )}
                    <Space.Compact style={{ display: 'flex' }}>
                      <Input
                        value={chatInput}
                        disabled={readonly || chatSending}
                        placeholder={
                          readonly
                            ? 'AI 任务运行中或无操作权限'
                            : '输入修改指令，Enter 发送'
                        }
                        onChange={(event) => setChatInput(event.target.value)}
                        onPressEnter={() => sendChat(chatInput)}
                      />
                      <Button
                        type="primary"
                        icon={<SendOutlined />}
                        loading={chatSending}
                        disabled={readonly}
                        onClick={() => sendChat(chatInput)}
                      />
                    </Space.Compact>
                  </div>
                ),
              },
              {
                key: 'review',
                label: '审核报告',
                children: (
                  <div style={{ overflowY: 'auto', height: 520 }}>
                    {!data.last_review ? (
                      <div style={{ color: 'rgba(0,0,0,0.45)', padding: 12 }}>
                        还没有审核记录。点击顶部「AI 审核修正」让 AI 检查并自动
                        修正错误与前后不一致。
                      </div>
                    ) : (
                      <Space
                        direction="vertical"
                        size={10}
                        style={{ width: '100%' }}
                      >
                        <div>
                          <Tag color="purple">评分 {data.last_review.score}</Tag>
                          <span
                            style={{ fontSize: 12, color: 'rgba(0,0,0,0.55)' }}
                          >
                            {data.last_review.fixed_count} 处自动修正 ·{' '}
                            {data.last_review.needs_human_count} 处需人工
                          </span>
                        </div>
                        <div style={{ fontSize: 13 }}>
                          {data.last_review.summary}
                        </div>
                        {data.last_review.dimensions.map((dimension) => (
                          <div key={dimension.name} style={{ fontSize: 12 }}>
                            <Tag
                              color={
                                dimension.status === 'ok'
                                  ? 'green'
                                  : dimension.status === 'warn'
                                    ? 'orange'
                                    : 'red'
                              }
                            >
                              {dimension.name}
                            </Tag>
                            {dimension.note}
                          </div>
                        ))}
                        {data.last_review.issues.map((issue) => {
                          const meta =
                            ISSUE_STATUS_META[issue.status] ??
                            ISSUE_STATUS_META.unresolved
                          return (
                            <div
                              key={issue.id}
                              style={{
                                border: '1px solid rgba(0,0,0,0.08)',
                                borderRadius: 8,
                                padding: 8,
                                fontSize: 12,
                              }}
                            >
                              <div>
                                <Tag color={meta.color}>{meta.label}</Tag>
                                <span style={{ color: 'rgba(0,0,0,0.5)' }}>
                                  {issue.section}
                                </span>
                              </div>
                              <div style={{ marginTop: 4 }}>{issue.problem}</div>
                              {issue.status === 'fixed' && issue.after && (
                                <div style={{ marginTop: 4, color: '#389e0d' }}>
                                  修正为：{issue.after}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </Space>
                    )}
                  </div>
                ),
              },
              {
                key: 'revisions',
                label: '修订记录',
                children: (
                  <div style={{ overflowY: 'auto', height: 520 }}>
                    <Button
                      size="small"
                      onClick={loadRevisions}
                      style={{ marginBottom: 8 }}
                    >
                      刷新
                    </Button>
                    {revisions.length === 0 && (
                      <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>
                        暂无记录，点击“刷新”加载。
                      </div>
                    )}
                    {revisions.map((revision) => (
                      <div
                        key={revision.id}
                        style={{
                          border: '1px solid rgba(0,0,0,0.08)',
                          borderRadius: 8,
                          padding: 8,
                          marginBottom: 6,
                          fontSize: 12,
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            gap: 6,
                            alignItems: 'center',
                          }}
                        >
                          <Tag color="purple">#{revision.revision_no}</Tag>
                          <Tag>
                            {SOURCE_LABELS[revision.source] ?? revision.source}
                          </Tag>
                          <Tooltip title={formatTime(revision.created_at)}>
                            <span style={{ color: 'rgba(0,0,0,0.45)' }}>
                              {formatTime(revision.created_at).slice(5, 16)}
                            </span>
                          </Tooltip>
                        </div>
                        <div style={{ margin: '4px 0' }}>{revision.summary}</div>
                        <Space>
                          <Button
                            size="small"
                            onClick={async () => {
                              const res = await fetchEmergencyPlanRevision(
                                planId,
                                revision.revision_no
                              )
                              if (res.code === 200 && res.data) {
                                setRevisionDetail({
                                  revision_no: res.data.revision_no,
                                  source: res.data.source,
                                  summary: res.data.summary,
                                  changed_sections: res.data.changed_sections ?? [],
                                  changes: res.data.changes ?? [],
                                })
                              } else {
                                message.error(res.message || '加载修订详情失败')
                              }
                            }}
                          >
                            查看差异
                          </Button>
                          <Button
                            size="small"
                            icon={<RollbackOutlined />}
                            disabled={readonly}
                            onClick={() => handleRestore(revision.revision_no)}
                          >
                            恢复
                          </Button>
                        </Space>
                      </div>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        </div>
      </div>

      <Modal
        title={`修订 ${revisionDetail?.revision_no ?? ''} 详情`}
        open={revisionDetail !== null}
        onCancel={() => setRevisionDetail(null)}
        footer={null}
        width={760}
      >
        {revisionDetail && (
          <div style={{ fontSize: 13 }}>
            <p>
              {SOURCE_LABELS[revisionDetail.source] ?? revisionDetail.source} ·{' '}
              {revisionDetail.summary}
            </p>
            {revisionDetail.changed_sections[0] === '*' && (
              <div>首次生成完整正文。</div>
            )}
            {revisionDetail.changes.length > 0
              ? revisionDetail.changes.map((change, index) => (
                  <div
                    key={index}
                    style={{
                      border: '1px solid rgba(0,0,0,0.08)',
                      borderRadius: 8,
                      padding: 8,
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ color: 'rgba(0,0,0,0.5)' }}>
                      [{change.section}] {change.reason}
                    </div>
                    {change.before && <div>原：{change.before}</div>}
                    {change.after && (
                      <div style={{ color: '#389e0d' }}>新：{change.after}</div>
                    )}
                  </div>
                ))
              : revisionDetail.changed_sections.map((section) => (
                  <Tag key={section}>{section}</Tag>
                ))}
          </div>
        )}
      </Modal>

      <Modal
        title="定稿确认"
        open={finalizeOpen}
        onOk={handleFinalize}
        onCancel={() => setFinalizeOpen(false)}
        okText="确认定稿"
      >
        定稿表示当前正文经人工确认。定稿后仍可继续编辑，但状态会回到草稿。
      </Modal>
    </div>
  )
}
