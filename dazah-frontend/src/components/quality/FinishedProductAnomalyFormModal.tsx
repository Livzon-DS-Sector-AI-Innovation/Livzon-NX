'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Button, DatePicker, Form, Input, Modal, Select, Switch, Typography, Upload } from 'antd'
import { PaperClipOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import type {
  AnomalyReportFieldMeta,
  AnomalyReportRecord,
  QualityPersonOption,
} from '@/types/quality'
import type { AnomalyAttachmentRef } from '@/actions/finished-product-anomaly'
import { uploadAnomalyAttachment } from '@/actions/finished-product-anomaly'
import { fetchQualityPersonDirectory } from '@/lib/api/client/quality'
import { useQuery } from '@tanstack/react-query'

/** 通用表单不写入的系统/派生字段类型 */
const ANOMALY_READONLY_UI_TYPES = new Set([
  'AutoNumber',
  'Lookup',
  'DuplexLink',
  'Formula',
  'CreatedUser',
  'ModifiedUser',
  'CreatedTime',
  'ModifiedTime',
  'GroupChat',
  'Button',
  'Url',
])

/** bitable 单附件上限 20MB（与后端校验一致，先在前端拦截省一次请求） */
const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

interface FinishedProductAnomalyFormModalProps {
  open: boolean
  saving?: boolean
  year?: number
  fieldMetas?: AnomalyReportFieldMeta[]
  /** 编辑时传入记录；新增传 null */
  initialRecord: AnomalyReportRecord | null
  onCancel: () => void
  onSubmit: (fields: Record<string, unknown>) => Promise<void> | void
}

function toBool(value: unknown): boolean {
  return value === true || value === 'True' || value === 'true'
}

/** 飞书附件记录值（含 url/size 等回显字段）→ 表单值（保留 file_token/name/size） */
function extractAttachments(raw: unknown): AnomalyAttachmentRef[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === 'object' && Boolean((item as Record<string, unknown>).file_token),
    )
    .map((item) => ({
      file_token: String(item.file_token),
      name: String(item.name || item.file_token),
      size: typeof item.size === 'number' ? item.size : 0,
      type: item.type ? String(item.type) : '',
    }))
}

function attachmentKey(list: AnomalyAttachmentRef[]): string {
  return list.map((item) => item.file_token).join(',')
}

/** 成品异常报告新增/编辑弹窗：动态字段 + 附件直传多维表格（人员经后端换发 union_id）。 */
export function FinishedProductAnomalyFormModal({
  open,
  saving = false,
  year = 2025,
  fieldMetas = [],
  initialRecord,
  onCancel,
  onSubmit,
}: FinishedProductAnomalyFormModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()

  const editableFields = useMemo(
    () =>
      fieldMetas.filter(
        (meta) =>
          !ANOMALY_READONLY_UI_TYPES.has(meta.ui_type) &&
          meta.ui_type !== 'Attachment',
      ),
    [fieldMetas],
  )
  const attachmentFields = useMemo(
    () => fieldMetas.filter((meta) => meta.ui_type === 'Attachment'),
    [fieldMetas],
  )
  const otherReadonlyFields = useMemo(
    () =>
      fieldMetas.filter(
        (meta) =>
          ANOMALY_READONLY_UI_TYPES.has(meta.ui_type) &&
          meta.ui_type !== 'Attachment',
      ),
    [fieldMetas],
  )

  const { data: contacts = [] } = useQuery<QualityPersonOption[]>({
    queryKey: ['quality-person-directory'],
    queryFn: fetchQualityPersonDirectory,
    enabled: open,
  })

  const personOptions = contacts
    .map((contact) => {
      const id = contact.open_id || ''
      return { label: contact.name || id, value: id }
    })
    .filter((option) => option.value)

  /** 附件字段值：field_name → 已上传（或编辑保留）的附件列表 */
  const [attachmentValues, setAttachmentValues] = useState<
    Record<string, AnomalyAttachmentRef[]>
  >({})
  /** 打开时的附件基线，用于提交时判断"是否有变更"（避免误清空/重复写） */
  const [attachmentBaseline, setAttachmentBaseline] = useState<
    Record<string, string>
  >({})
  const [uploadingField, setUploadingField] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    const values: Record<string, unknown> = {}
    for (const meta of editableFields) {
      const raw = initialRecord?.[meta.field_name]
      if (meta.ui_type === 'DateTime') {
        // 飞书 DateTime 返回毫秒时间戳（可能为 number 或数字字符串）
        const rawMillis =
          typeof raw === 'string' && /^\d+$/.test(raw.trim())
            ? Number(raw.trim())
            : raw
        values[meta.field_name] =
          typeof rawMillis === 'number' ? dayjs(rawMillis) : null
      } else if (meta.ui_type === 'Checkbox') {
        values[meta.field_name] = toBool(raw)
      } else if (meta.ui_type === 'User') {
        values[meta.field_name] = Array.isArray(raw)
          ? (raw as Array<{ id?: string }>)
              .map((item) => item?.id || '')
              .filter(Boolean)
          : []
      } else {
        values[meta.field_name] = raw ?? undefined
      }
    }
    form.setFieldsValue(values)
    const attachments: Record<string, AnomalyAttachmentRef[]> = {}
    const baseline: Record<string, string> = {}
    for (const meta of attachmentFields) {
      const existing = extractAttachments(initialRecord?.[meta.field_name])
      attachments[meta.field_name] = existing
      baseline[meta.field_name] = attachmentKey(existing)
    }
    setAttachmentValues(attachments)
    setAttachmentBaseline(baseline)
  }, [form, initialRecord, open, editableFields, attachmentFields])

  const handleUpload = async (fieldName: string, file: File) => {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      message.error('附件超过 20MB，请压缩后再上传')
      return
    }
    setUploadingField(fieldName)
    try {
      const uploaded = await uploadAnomalyAttachment(year, file)
      setAttachmentValues((prev) => ({
        ...prev,
        [fieldName]: [...(prev[fieldName] || []), uploaded],
      }))
    } catch (error: unknown) {
      message.error(
        error instanceof Error && error.message
          ? error.message
          : '附件上传失败',
      )
    } finally {
      setUploadingField(null)
    }
  }

  const removeAttachment = (fieldName: string, fileToken: string) => {
    setAttachmentValues((prev) => ({
      ...prev,
      [fieldName]: (prev[fieldName] || []).filter(
        (item) => item.file_token !== fileToken,
      ),
    }))
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    const fields: Record<string, unknown> = {}
    for (const meta of editableFields) {
      const value = values[meta.field_name]
      if (meta.ui_type === 'DateTime') {
        if (dayjs.isDayjs(value)) {
          fields[meta.field_name] = (value as Dayjs).valueOf()
        }
      } else if (meta.ui_type === 'Checkbox') {
        fields[meta.field_name] = Boolean(value)
      } else if (meta.ui_type === 'User') {
        if (Array.isArray(value) && value.length > 0) {
          fields[meta.field_name] = (value as string[]).map((id) => ({ id }))
        }
      } else if (value !== undefined && value !== null && value !== '') {
        fields[meta.field_name] = value
      }
    }
    for (const meta of attachmentFields) {
      const current = attachmentValues[meta.field_name] || []
      const changed =
        attachmentKey(current) !== (attachmentBaseline[meta.field_name] ?? '')
      if (!changed) continue
      // 新增：仅上传了才写；编辑：有变更（含删光）才写
      if (current.length > 0 || initialRecord) {
        fields[meta.field_name] = current.map((item) => ({
          file_token: item.file_token,
        }))
      }
    }
    await onSubmit(fields)
  }

  return (
    <Modal
      title={
        initialRecord
          ? `编辑成品异常报告（${year}年）`
          : `新增成品异常报告（${year}年）`
      }
      open={open}
      onCancel={onCancel}
      onOk={() => void handleSubmit()}
      confirmLoading={saving}
      destroyOnHidden
      width={720}
    >
      <Form form={form} layout="vertical">
        {editableFields.map((meta) => {
          if (meta.ui_type === 'DateTime') {
            return (
              <Form.Item key={meta.field_name} label={meta.field_name} name={meta.field_name}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            )
          }
          if (meta.ui_type === 'Checkbox') {
            return (
              <Form.Item
                key={meta.field_name}
                label={meta.field_name}
                name={meta.field_name}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            )
          }
          if (meta.ui_type === 'User') {
            return (
              <Form.Item key={meta.field_name} label={meta.field_name} name={meta.field_name}>
                <Select
                  mode="multiple"
                  allowClear
                  showSearch
                  placeholder="请选择人员"
                  options={personOptions}
                  filterOption={(input, option) =>
                    (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            )
          }
          if (meta.ui_type === 'MultiSelect') {
            return (
              <Form.Item key={meta.field_name} label={meta.field_name} name={meta.field_name}>
                <Select
                  mode="multiple"
                  allowClear
                  options={(meta.options ?? []).map((option) => ({
                    label: option.name,
                    value: option.name,
                  }))}
                />
              </Form.Item>
            )
          }
          if (meta.ui_type === 'SingleSelect') {
            return (
              <Form.Item key={meta.field_name} label={meta.field_name} name={meta.field_name}>
                <Select
                  allowClear
                  showSearch
                  options={(meta.options ?? []).map((option) => ({
                    label: option.name,
                    value: option.name,
                  }))}
                  filterOption={(input, option) =>
                    (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            )
          }
          return (
            <Form.Item key={meta.field_name} label={meta.field_name} name={meta.field_name}>
              <Input maxLength={255} />
            </Form.Item>
          )
        })}
        {attachmentFields.map((meta) => {
          const list = attachmentValues[meta.field_name] || []
          return (
            <Form.Item key={meta.field_name} label={meta.field_name}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {list.map((item) => (
                  <div
                    key={`${item.file_token}`}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      fontSize: 13,
                    }}
                  >
                    <PaperClipOutlined />
                    <span style={{ flex: 1, wordBreak: 'break-all' }}>{item.name}</span>
                    <Button
                      size="small"
                      type="text"
                      danger
                      onClick={() => removeAttachment(meta.field_name, item.file_token)}
                    >
                      移除
                    </Button>
                  </div>
                ))}
                <Upload
                  multiple
                  showUploadList={false}
                  beforeUpload={(file) => {
                    void handleUpload(meta.field_name, file as unknown as File)
                    return false
                  }}
                >
                  <Button
                    size="small"
                    icon={<UploadOutlined />}
                    loading={uploadingField === meta.field_name}
                  >
                    上传文件
                  </Button>
                </Upload>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  上传后随本次保存写入多维表格附件字段；单个文件 ≤20MB。
                </Typography.Text>
              </div>
            </Form.Item>
          )
        })}
        {otherReadonlyFields.length > 0 && (
          <Typography.Text type="secondary">
            系统字段（{otherReadonlyFields.map((meta) => meta.field_name).join('、')}）由飞书自动维护，平台详情中可查看。
          </Typography.Text>
        )}
      </Form>
    </Modal>
  )
}
