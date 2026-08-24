'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Space, Spin, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { applyDeviationAiSession as applyDeviationAiSessionAction, deleteDeviationAiSessionAttachment as deleteDeviationAiSessionAttachmentAction, regenerateDeviationAiSession as regenerateDeviationAiSessionAction, updateDeviationAiSession as updateDeviationAiSessionAction, uploadDeviationAiSessionAttachment as uploadDeviationAiSessionAttachmentAction } from '@/actions/quality-deviation'
import { fetchDeviationAiSession } from '@/lib/api/client/quality'

import type { DeviationAiSession, DeviationAiWorkbenchRecord } from '@/types/quality'
import { QualityAiAttachmentList } from './QualityAiAttachmentList'
import { QualityAiResultCard } from './QualityAiResultCard'
import { QualityAiSupplementForm } from './QualityAiSupplementForm'

interface DeviationAiConversationPanelProps {
  /** 工作台最小视图模型：面板只消费摘要字段与 id */
  deviation: DeviationAiWorkbenchRecord
  onApplied?: () => void
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export function DeviationAiConversationPanel({
  deviation,
  onApplied,
}: DeviationAiConversationPanelProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [applyingSection, setApplyingSection] = useState<string | null>(null)
  const [supplementText, setSupplementText] = useState('')

  const { data: session, isLoading: loading, error: sessionError } = useQuery<DeviationAiSession>({
    queryKey: ['quality-deviation-ai', 'session', deviation.id],
    queryFn: () => fetchDeviationAiSession(deviation.id),
  })

  const loadError = sessionError
    ? getErrorMessage(sessionError, '加载 AI 会话失败')
    : null

  useEffect(() => {
    if (sessionError) {
      message.error(getErrorMessage(sessionError, '加载 AI 会话失败'))
    }
  }, [sessionError, message])

  const sessionSupplementText = session?.supplement_text ?? ''
  useEffect(() => {
    setSupplementText(sessionSupplementText)
  }, [sessionSupplementText])

  const dirty = useMemo(
    () => supplementText.trim() !== (session?.supplement_text || '').trim(),
    [session?.supplement_text, supplementText]
  )

  const invalidateSession = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['quality-deviation-ai', 'session', deviation.id] })
  }, [queryClient, deviation.id])

  const handleSubmit = useCallback(async () => {
    try {
      setSaving(true)
      if (dirty) {
        await updateDeviationAiSessionAction(deviation.id, supplementText)
      }
      await regenerateDeviationAiSessionAction(deviation.id)
      message.success('AI 已根据当前上下文重新完善分析')
      invalidateSession()
      onApplied?.()
    } catch (error) {
      message.error(getErrorMessage(error, '重新完善分析失败'))
    } finally {
      setSaving(false)
    }
  }, [deviation.id, dirty, message, onApplied, supplementText, invalidateSession])

  const handleUpload = useCallback(
    async (file: File) => {
      try {
        setUploading(true)
        const formData = new FormData()
        formData.append('file', file)
        await uploadDeviationAiSessionAttachmentAction(deviation.id, formData)
        message.success('附件已上传')
        invalidateSession()
      } catch (error) {
        message.error(getErrorMessage(error, '附件上传失败'))
      } finally {
        setUploading(false)
      }
    },
    [deviation.id, invalidateSession, message]
  )

  const handleDeleteAttachment = useCallback(
    async (attachmentId: string) => {
      try {
        setDeletingId(attachmentId)
        await deleteDeviationAiSessionAttachmentAction(deviation.id, attachmentId)
        message.success('附件已删除')
        invalidateSession()
      } catch (error) {
        message.error(getErrorMessage(error, '删除附件失败'))
      } finally {
        setDeletingId(null)
      }
    },
    [deviation.id, invalidateSession, message]
  )

  const handleApply = useCallback(
    async (section: 'deviation_analysis' | 'capa_suggestion', fieldKeys: string[]) => {
      try {
        setApplyingSection(section)
        await applyDeviationAiSessionAction(deviation.id, {
          section,
          field_keys: fieldKeys,
        })
        message.success('AI 建议已应用到偏差字段')
        invalidateSession()
        onApplied?.()
      } catch (error) {
        message.error(getErrorMessage(error, '应用 AI 建议失败'))
      } finally {
        setApplyingSection(null)
      }
    },
    [deviation.id, invalidateSession, message, onApplied]
  )

  if (loading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: 240 }}>
        <Spin />
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* 偏差信息摘要由工作台页统一展示（spec：移除面板内重复摘要卡）；
          AI 会话加载失败时在面板区域提示，不影响页面上的偏差摘要 */}
      {loadError ? (
        <Typography.Text type="danger">{loadError}</Typography.Text>
      ) : null}

      <QualityAiSupplementForm
        value={supplementText}
        saving={saving}
        dirty={dirty}
        onChange={setSupplementText}
        onSubmit={() => void handleSubmit()}
      />

      <QualityAiAttachmentList
        attachments={session?.attachments || []}
        uploading={uploading}
        deletingId={deletingId}
        onUpload={handleUpload}
        onDelete={handleDeleteAttachment}
      />

      <Space orientation="vertical" style={{ width: '100%' }} size={16}>
        <QualityAiResultCard
          title="偏差分析"
          section="deviation_analysis"
          payload={session?.deviation_analysis_payload || null}
          loading={applyingSection === 'deviation_analysis'}
          onApply={handleApply}
        />
        <QualityAiResultCard
          title="CAPA建议"
          section="capa_suggestion"
          payload={session?.capa_suggestion_payload || null}
          loading={applyingSection === 'capa_suggestion'}
          onApply={handleApply}
        />
      </Space>
    </div>
  )
}
