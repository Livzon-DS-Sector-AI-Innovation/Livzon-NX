'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Descriptions, Form, Modal } from 'antd'

import { createInspectionFeishuRecord, updateInspectionFeishuRecord } from '@/actions/quality-inspection'
import { fetchInspectionFeishuFields } from '@/lib/api/client/quality'
import type { InspectionFeishuFieldMeta } from '@/types/quality'
import {
  FieldControl,
  renderReadOnlyValue,
  toApiValue,
  toFormValue,
} from './inspectionFeishuFormFields'

interface InspectionFeishuRecordModalProps {
  open: boolean
  entityCode: string
  mode: 'create' | 'edit'
  initialValues?: Record<string, unknown>
  /** 开启后人员字段（User）可搜索选人；关闭时与旧版一致只读展示 */
  editablePersonFields?: boolean
  onClose: () => void
  onSuccess: () => void
}

export function InspectionFeishuRecordModal({
  open,
  entityCode,
  mode,
  initialValues,
  editablePersonFields = false,
  onClose,
  onSuccess,
}: InspectionFeishuRecordModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [fieldsMeta, setFieldsMeta] = useState<InspectionFeishuFieldMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  // 人员字段（User）元数据标为只读（附件上传等才是真只读），但通用写接口支持
  // 按 [{id}] 提交并换发 union_id，因此页面开启 editablePersonFields 时放开为可选人
  const isFieldEditable = (f: InspectionFeishuFieldMeta) =>
    f.editable || (editablePersonFields && f.ui_type === 'User')

  useEffect(() => {
    if (!open || !entityCode) return
    let cancelled = false
    setLoading(true)
    setFieldsMeta([])
    form.resetFields()
    fetchInspectionFeishuFields(entityCode).then((res) => {
      if (cancelled) return
      const meta = res?.fields ?? []
      setFieldsMeta(meta)
      const values: Record<string, unknown> = {}
      for (const f of meta) {
        if (!isFieldEditable(f)) continue
        const v = toFormValue(f, initialValues?.[f.field_name])
        if (v !== undefined) values[f.field_name] = v
      }
      form.setFieldsValue(values)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, entityCode, initialValues, form, editablePersonFields])

  const editableFields = useMemo(
    () => fieldsMeta.filter((f) => isFieldEditable(f)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fieldsMeta, editablePersonFields],
  )
  const readOnlyFields = useMemo(
    () => fieldsMeta.filter((f) => !isFieldEditable(f)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fieldsMeta, editablePersonFields],
  )

  const handleOk = async () => {
    try {
      const raw = await form.validateFields()
      const fields: Record<string, unknown> = {}
      for (const f of editableFields) {
        const v = raw[f.field_name]
        if (v === undefined || v === null || v === '') continue
        fields[f.field_name] = toApiValue(f, v)
      }
      setSubmitting(true)
      if (mode === 'create') {
        await createInspectionFeishuRecord(entityCode, fields)
      } else {
        await updateInspectionFeishuRecord(
          entityCode,
          String(initialValues?.record_id ?? ''),
          fields
        )
      }
      message.success(mode === 'create' ? '创建成功，已同步飞书' : '更新成功，已同步飞书')
      onSuccess()
      onClose()
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const openAttachment = async (att: { name?: string; url?: string; file_token?: string }) => {
    const recordId = initialValues?.record_id
    if (!entityCode || !recordId || !att.file_token) {
      if (att.url) window.open(att.url, '_blank', 'noopener,noreferrer')
      return
    }
    try {
      const res = await fetch(
        `/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/records/${encodeURIComponent(String(recordId))}/attachments/${encodeURIComponent(att.file_token)}/content`
      )
      if (!res.ok) {
        let msg = `下载失败(${res.status})`
        try {
          const errJson = await res.json()
          if (errJson?.message) msg = errJson.message
        } catch { /* 非 JSON 错误体则用默认文案 */ }
        throw new Error(msg)
      }
      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      window.open(blobUrl, '_blank')
    } catch (err) {
      message.error(err instanceof Error ? err.message : '附件下载失败')
    }
  }

  return (
    <Modal
      open={open}
      title={mode === 'create' ? '新增记录' : '编辑记录'}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={submitting}
      width={640}
      destroyOnHidden
    >
      {readOnlyFields.length > 0 && (
        <Descriptions
          size="small"
          column={1}
          style={{ marginBottom: 16 }}
          title="只读字段（附件/公式/关联等）"
        >
          {readOnlyFields.map((f) => (
            <Descriptions.Item key={f.field_name} label={f.field_name}>
              {renderReadOnlyValue(initialValues?.[f.field_name], openAttachment)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}
      <Form form={form} layout="vertical" disabled={loading}>
        {editableFields.map((f) => (
          <FieldControl
            key={f.field_name}
            field={f}
            initialValue={initialValues?.[f.field_name]}
            required={Boolean(f.is_primary)}
          />
        ))}
      </Form>
    </Modal>
  )
}