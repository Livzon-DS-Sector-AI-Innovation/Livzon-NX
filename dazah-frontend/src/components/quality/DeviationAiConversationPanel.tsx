'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { App, Space, Spin, Typography } from 'antd'
import {
  applyDeviationAiSession as applyDeviationAiSessionAction,
  deleteDeviationAiSessionAttachment as deleteDeviationAiSessionAttachmentAction,
  regenerateDeviationAiSession as regenerateDeviationAiSessionAction,
  updateDeviationAiSession as updateDeviationAiSessionAction,
  uploadDeviationAiSessionAttachment as uploadDeviationAiSessionAttachmentAction,
} from '@/actions/quality'
import { fetchDeviationAiSession } from '@/lib/api/quality'
import type { DeviationAiSession, DeviationAiWorkbenchRecord } from '@/types/quality'
import { QualityAiAttachmentList } from './QualityAiAttachmentList'
import { QualityAiResultCard } from './QualityAiResultCard'
import { QualityAiSupplementForm } from './QualityAiSupplementForm'

interface DeviationAiConversationPanelProps {
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
  const [session, setSession] = useState<DeviationAiSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [applyingSection, setApplyingSection] = useState<string | null>(null)
  const [supplementText, setSupplementText] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadSession = useCallback(async () => {
    try {
      setLoading(true)
      setLoadError(null)
      const result = await fetchDeviationAiSession(deviation.id)
      setSession(result)
      setSupplementText(result.supplement_text)
    } catch (error) {
      const nextError = getErrorMessage(error, '加载 AI 会话失败')
      setLoadError(nextError)
      message.error(nextError)
    } finally {
      setLoading(false)
    }
  }, [deviation.id, message])

  useEffect(() => {
    void loadSession()
  }, [loadSession])

  const dirty = useMemo(
    () => supplementText.trim() !== (session?.supplement_text || '').trim(),
    [session?.supplement_text, supplementText]
  )

  const handleSubmit = useCallback(async () => {
    try {
      setSaving(true)
      if (dirty) {
        await updateDeviationAiSessionAction(deviation.id, supplementText)
      }
      const result = await regenerateDeviationAiSessionAction(deviation.id)
      if (result) {
        setSession(result)
        setSupplementText(result.supplement_text)
      }
      message.success('AI 已根据当前上下文重新完善分析')
      onApplied?.()
    } catch (error) {
      message.error(getErrorMessage(error, '重新完善分析失败'))
    } finally {
      setSaving(false)
    }
  }, [deviation.id, dirty, message, onApplied, supplementText])

  const handleUpload = useCallback(
    async (file: File) => {
      try {
        setUploading(true)
        const formData = new FormData()
        formData.append('file', file)
        await uploadDeviationAiSessionAttachmentAction(deviation.id, formData)
        message.success('附件已上传')
        await loadSession()
      } catch (error) {
        message.error(getErrorMessage(error, '附件上传失败'))
      } finally {
        setUploading(false)
      }
    },
    [deviation.id, loadSession, message]
  )

  const handleDeleteAttachment = useCallback(
    async (attachmentId: string) => {
      try {
        setDeletingId(attachmentId)
        const result = await deleteDeviationAiSessionAttachmentAction(deviation.id, attachmentId)
        if (result) {
          setSession(result)
        }
        message.success('附件已删除')
      } catch (error) {
        message.error(getErrorMessage(error, '删除附件失败'))
      } finally {
        setDeletingId(null)
      }
    },
    [deviation.id, message]
  )

  const handleApply = useCallback(
    async (section: 'deviation_analysis' | 'capa_suggestion', fieldKeys: string[]) => {
      try {
        setApplyingSection(section)
        const result = await applyDeviationAiSessionAction(deviation.id, {
          section,
          field_keys: fieldKeys,
        })
        if (result) {
          setSession(result)
        }
        message.success('AI 建议已应用到偏差字段')
        onApplied?.()
      } catch (error) {
        message.error(getErrorMessage(error, '应用 AI 建议失败'))
      } finally {
        setApplyingSection(null)
      }
    },
    [deviation.id, message, onApplied]
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
      {loadError ? (
        <Typography.Text type="danger" style={{ display: 'block' }}>
          {loadError}
        </Typography.Text>
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

      <Space direction="vertical" style={{ width: '100%' }} size={16}>
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
