'use client'

import { useEffect, useMemo } from 'react'
import { DatePicker, Form, Input, Modal, Select, Switch, Typography } from 'antd'
import dayjs, { Dayjs } from 'dayjs'
import type {
  QcValidationFieldMeta,
  QcValidationRecord,
} from '@/types/quality'
import {
  FeishuPersonSelect,
  type FeishuPersonValue,
} from '@/components/shared/FeishuPersonSelect'

/** 通用表单不写入的只读字段类型（附件请在飞书中维护） */
const QC_READONLY_UI_TYPES = new Set([
  'Attachment',
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

interface QcValidationFormModalProps {
  open: boolean
  saving?: boolean
  year?: number
  fieldMetas?: QcValidationFieldMeta[]
  /** 编辑时传入记录；新增传 null */
  initialRecord: QcValidationRecord | null
  onCancel: () => void
  onSubmit: (fields: Record<string, unknown>) => Promise<void> | void
}

function toBool(value: unknown): boolean {
  return value === true || value === 'True' || value === 'true'
}

/** 记录里的 User 字段 → 选择器回显值（id 为飞书成员字段 id） */
function toPersonValues(raw: unknown): FeishuPersonValue[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      if (item && typeof item === 'object') {
        const record = item as Record<string, unknown>
        const id = String(record.id ?? record.open_id ?? '').trim()
        return {
          id,
          name: String(record.name ?? record.text ?? '').trim(),
          // 记录回读的 id 对当前飞书表有效，写回时无需反查
          resolved: Boolean(id),
        }
      }
      return { id: '', name: '' }
    })
    .filter((person) => person.id || person.name)
}

/** QC验证新增/编辑弹窗：按飞书字段元数据动态生成表单（人员来自 HR 飞书联系人，中文/拼音搜索）。 */
export function QcValidationFormModal({
  open,
  saving = false,
  year = 2026,
  fieldMetas = [],
  initialRecord,
  onCancel,
  onSubmit,
}: QcValidationFormModalProps) {
  const [form] = Form.useForm()

  const editableFields = useMemo(
    () => fieldMetas.filter((meta) => !QC_READONLY_UI_TYPES.has(meta.ui_type)),
    [fieldMetas],
  )
  const attachmentFields = useMemo(
    () => fieldMetas.filter((meta) => meta.ui_type === 'Attachment'),
    [fieldMetas],
  )

  // 编辑回显：每个 User 字段已有人员并入候选（候选中没有的成员 id 也能正常显示）
  const userExtrasByField = useMemo(() => {
    const extras: Record<string, FeishuPersonValue[]> = {}
    for (const meta of fieldMetas) {
      if (meta.ui_type === 'User') {
        extras[meta.field_name] = toPersonValues(initialRecord?.[meta.field_name])
      }
    }
    return extras
  }, [fieldMetas, initialRecord])

  useEffect(() => {
    if (!open) return
    const values: Record<string, unknown> = {}
    for (const meta of editableFields) {
      const raw = initialRecord?.[meta.field_name]
      if (meta.ui_type === 'DateTime') {
        values[meta.field_name] =
          typeof raw === 'number' || typeof raw === 'string'
            ? dayjs(raw as number)
            : null
      } else if (meta.ui_type === 'Checkbox') {
        values[meta.field_name] = toBool(raw)
      } else if (meta.ui_type === 'User') {
        values[meta.field_name] = toPersonValues(raw)
      } else {
        values[meta.field_name] = raw ?? undefined
      }
    }
    form.setFieldsValue(values)
  }, [form, initialRecord, open, editableFields])

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
          fields[meta.field_name] = (value as FeishuPersonValue[]).map((person) => ({
            id: person.id,
            name: person.name,
            resolved: person.resolved,
          }))
        }
      } else if (value !== undefined && value !== null && value !== '') {
        fields[meta.field_name] = value
      }
    }
    await onSubmit(fields)
  }

  return (
    <Modal
      title={initialRecord ? `编辑QC验证记录（${year}年）` : `新增QC验证记录（${year}年）`}
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
                <FeishuPersonSelect
                  multiple
                  placeholder="输入姓名或拼音搜索人员"
                  extraOptions={userExtrasByField[meta.field_name]}
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
            <Form.Item
              key={meta.field_name}
              label={meta.field_name}
              name={meta.field_name}
              rules={
                meta.field_name === '方案名称'
                  ? [{ required: true, message: '请输入方案名称' }]
                  : undefined
              }
            >
              <Input maxLength={255} />
            </Form.Item>
          )
        })}
        {attachmentFields.length > 0 && (
          <Typography.Text type="secondary">
            附件字段（{attachmentFields.map((meta) => meta.field_name).join('、')}）请在飞书多维表格中维护，平台详情中可查看下载。
          </Typography.Text>
        )}
      </Form>
    </Modal>
  )
}
