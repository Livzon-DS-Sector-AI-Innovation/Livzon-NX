'use client'

import { useEffect, useMemo } from 'react'
import { DatePicker, Form, Input, Modal, Select, Switch, Typography } from 'antd'
import dayjs, { Dayjs } from 'dayjs'
import type {
  DepartmentContact,
  QcValidationFieldMeta,
  QcValidationRecord,
} from '@/types/quality'
import { fetchDepartmentContacts } from '@/lib/api/client/quality'
import { useQuery } from '@tanstack/react-query'

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

/** QC验证新增/编辑弹窗：按飞书字段元数据动态生成表单（人员走部门联系人解析）。 */
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

  const { data: contacts = [] } = useQuery<DepartmentContact[]>({
    queryKey: ['quality-department-contacts'],
    queryFn: fetchDepartmentContacts,
    enabled: open,
  })

  const personOptions = contacts
    .map((contact) => {
      const id = contact.bitable_user_id || contact.open_id || ''
      return { label: contact.name || id, value: id }
    })
    .filter((option) => option.value)

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
          fields[meta.field_name] = (value as string[]).map((id) => ({ id }))
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
