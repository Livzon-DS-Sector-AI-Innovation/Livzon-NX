'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  App, Button, DatePicker, Descriptions, Form, Input, InputNumber, Modal,
  Select, Space, Switch,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

import { createInspectionFeishuRecord, updateInspectionFeishuRecord } from '@/actions/quality-inspection'
import { fetchInspectionFeishuFields } from '@/lib/api/client/quality'
import type { InspectionFeishuFieldMeta } from '@/types/quality'

interface InspectionFeishuRecordModalProps {
  open: boolean
  entityCode: string
  mode: 'create' | 'edit'
  initialValues?: Record<string, unknown>
  onClose: () => void
  onSuccess: () => void
}

function renderReadOnlyValue(
  value: unknown,
  onOpenAttachment: (att: { name?: string; url?: string; file_token?: string }) => void
): React.ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    if (value.some((v) => (v as { url?: string })?.url)) {
      return (
        <Space orientation="vertical" size={4}>
          {value.map((v, i) => {
            const att = v as { name?: string; url?: string; file_token?: string }
            return (
              <Button
                key={i}
                type="link"
                size="small"
                style={{
                  padding: 0,
                  height: 'auto',
                  textAlign: 'left',
                  whiteSpace: 'normal',
                  wordBreak: 'break-all',
                  lineHeight: 1.4,
                  maxWidth: 220,
                }}
                onClick={() => onOpenAttachment(att)}
              >
                {att.name || '附件'}
              </Button>
            )
          })}
        </Space>
      )
    }
    if (value.some((v) => (v as { name?: string })?.name)) {
      const names = (value as { name?: string }[])
        .map((v) => v.name)
        .filter((n): n is string => Boolean(n))
      return names.length ? names.join('、') : '-'
    }
    return (value as unknown[]).join('、')
  }
  if (typeof value === 'object' && value !== null) {
    const obj = value as { link?: string; text?: string }
    if (obj.link) {
      return (
        <a href={obj.link} target="_blank" rel="noopener noreferrer">
          {obj.text || obj.link}
        </a>
      )
    }
  }
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function toFormValue(field: InspectionFeishuFieldMeta, value: unknown): unknown {
  if (value === null || value === undefined || value === '') return undefined
  if (field.ui_type === 'DateTime') {
    const d = dayjs(String(value))
    return d.isValid() ? d : undefined
  }
  if (field.ui_type === 'Checkbox') {
    if (typeof value === 'boolean') return value
    const s = String(value).trim()
    return s === '是' || s === 'true' || s === '1'
  }
  if (field.ui_type === 'Number' || field.ui_type === 'Currency') {
    const n = Number(value)
    return Number.isNaN(n) ? undefined : n
  }
  if (field.ui_type === 'MultiSelect' && Array.isArray(value)) {
    return value.map((v) => String(v))
  }
  if (field.ui_type === 'Url') {
    const obj = value as { link?: string; text?: string }
    return obj?.link || String(value)
  }
  return String(value)
}

function toApiValue(field: InspectionFeishuFieldMeta, value: unknown): unknown {
  if (field.ui_type === 'DateTime' && value) {
    return (value as Dayjs).format('YYYY-MM-DD')
  }
  if (field.ui_type === 'Number' || field.ui_type === 'Currency') {
    return typeof value === 'number' ? value : Number(value)
  }
  return value
}

function FieldControl({
  field,
}: {
  field: InspectionFeishuFieldMeta
}) {
  const label = field.field_name
  if (field.ui_type === 'DateTime') {
    return (
      <Form.Item name={field.field_name} label={label}>
        <DatePicker style={{ width: '100%' }} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'Checkbox') {
    return (
      <Form.Item name={field.field_name} label={label} valuePropName="checked">
        <Switch checkedChildren="是" unCheckedChildren="否" />
      </Form.Item>
    )
  }
  if (field.ui_type === 'Number' || field.ui_type === 'Currency') {
    return (
      <Form.Item name={field.field_name} label={label}>
        <InputNumber style={{ width: '100%' }} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'MultiSelect') {
    return (
      <Form.Item name={field.field_name} label={label}>
        <Select mode="multiple" allowClear placeholder={`请选择${label}`} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'SingleSelect') {
    return (
      <Form.Item name={field.field_name} label={label}>
        <Select allowClear placeholder={`请选择${label}`} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'Text' || field.ui_type === 'LongText' || field.ui_type === 'Paragraph') {
    return (
      <Form.Item name={field.field_name} label={label}>
        <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} placeholder={`请输入${label}`} />
      </Form.Item>
    )
  }
  return (
    <Form.Item name={field.field_name} label={label}>
      <Input placeholder={`请输入${label}`} />
    </Form.Item>
  )
}

export function InspectionFeishuRecordModal({
  open,
  entityCode,
  mode,
  initialValues,
  onClose,
  onSuccess,
}: InspectionFeishuRecordModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [fieldsMeta, setFieldsMeta] = useState<InspectionFeishuFieldMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

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
        if (!f.editable) continue
        const v = toFormValue(f, initialValues?.[f.field_name])
        if (v !== undefined) values[f.field_name] = v
      }
      form.setFieldsValue(values)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [open, entityCode, initialValues, form])

  const editableFields = useMemo(() => fieldsMeta.filter((f) => f.editable), [fieldsMeta])
  const readOnlyFields = useMemo(() => fieldsMeta.filter((f) => !f.editable), [fieldsMeta])

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
          title="只读字段（附件/人员/关联等）"
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
          <FieldControl key={f.field_name} field={f} />
        ))}
      </Form>
    </Modal>
  )
}
