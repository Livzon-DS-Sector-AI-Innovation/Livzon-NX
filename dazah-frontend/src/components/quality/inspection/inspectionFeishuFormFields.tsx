'use client'

import { Button, DatePicker, Form, Input, InputNumber, Select, Space, Switch } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

import { FeishuPersonSelect, type FeishuPersonValue } from '@/components/shared/FeishuPersonSelect'
import type { InspectionFeishuFieldMeta } from '@/types/quality'

/** 只读字段值渲染（附件/人员/链接等），供新增/编辑弹窗与详情共用。 */
export function renderReadOnlyValue(
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

/** 记录里的人员字段值 → 选择器回显候选（id 可能不在人事目录里）。 */
export function toPersonExtraOptions(value: unknown): FeishuPersonValue[] {
  const list = Array.isArray(value) ? value : [value]
  const result: FeishuPersonValue[] = []
  for (const item of list) {
    const person = item as
      | { id?: string; open_id?: string; name?: string; email?: string; mobile?: string }
      | null
    if (!person || typeof person !== 'object') continue
    const id = String(person.id ?? person.open_id ?? '')
    if (!id) continue
    result.push({
      id,
      name: String(person.name ?? ''),
      email: person.email || undefined,
      mobile: person.mobile || undefined,
      // 记录回读的 id 对目标 Base 有效，提交时无需再次换发
      resolved: true,
    })
  }
  return result
}

/** 记录值 → 表单控件值（编辑回显）。 */
export function toFormValue(field: InspectionFeishuFieldMeta, value: unknown): unknown {
  if (value === null || value === undefined || value === '') return undefined
  if (field.ui_type === 'DateTime') {
    // 飞书 DateTime 回读为毫秒时间戳（number 或数字字符串，镜像归一化后是数字
    // 字符串）。直接 dayjs(字符串) 会被日历正则误解析成错误年份（如 1771-10-14），
    // 纯数字必须先转数字再解析
    if (typeof value === 'number') return dayjs(value)
    const text = String(value).trim()
    if (/^\d+$/.test(text)) return dayjs(Number(text))
    const d = dayjs(text)
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
  if (field.ui_type === 'User') {
    return toPersonExtraOptions(value)
  }
  if (field.ui_type === 'Url') {
    const obj = value as { link?: string; text?: string }
    return obj?.link || String(value)
  }
  return String(value)
}

/** 表单控件值 → 提交值（写飞书）。 */
export function toApiValue(field: InspectionFeishuFieldMeta, value: unknown): unknown {
  if (field.ui_type === 'DateTime' && value) {
    return (value as Dayjs).format('YYYY-MM-DD')
  }
  if (field.ui_type === 'Number' || field.ui_type === 'Currency') {
    return typeof value === 'number' ? value : Number(value)
  }
  if (field.ui_type === 'User') {
    // 人员按 [{id,...}] 提交，后端统一换发 union_id 后写飞书
    const list = Array.isArray(value) ? value : [value]
    return list.filter(
      (p): p is FeishuPersonValue => Boolean(p && typeof p === 'object' && p.id),
    )
  }
  return value
}

/** 按字段元数据渲染动态表单控件（校验错误靠近字段展示）。 */
export function FieldControl({
  field,
  initialValue,
  required,
}: {
  field: InspectionFeishuFieldMeta
  /** 编辑回显用原始值（人员字段并入候选列表） */
  initialValue?: unknown
  /** 主字段必填：飞书拒绝主字段为空的新记录 */
  required?: boolean
}) {
  const label = field.field_name
  // 飞书 SingleSelect/MultiSelect 的可选项来自字段元数据（如「结果判断」= 合格/不合格）
  const selectOptions = (field.options ?? []).map((opt) => ({
    label: opt.name,
    value: opt.name,
  }))
  const rules = required ? [{ required: true, message: `请填写${label}` }] : undefined
  if (field.ui_type === 'DateTime') {
    return (
      <Form.Item name={field.field_name} label={label} rules={rules}>
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
      <Form.Item name={field.field_name} label={label} rules={rules}>
        <InputNumber style={{ width: '100%' }} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'User') {
    return (
      <Form.Item
        name={field.field_name}
        label={label}
        rules={rules}
        extra="来自人事管理-飞书联系人，支持中文/全拼/首字母搜索"
      >
        <FeishuPersonSelect
          multiple
          extraOptions={toPersonExtraOptions(initialValue)}
        />
      </Form.Item>
    )
  }
  if (field.ui_type === 'MultiSelect') {
    return (
      <Form.Item name={field.field_name} label={label} rules={rules}>
        <Select mode="multiple" allowClear placeholder={`请选择${label}`} options={selectOptions} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'SingleSelect') {
    return (
      <Form.Item name={field.field_name} label={label} rules={rules}>
        <Select allowClear placeholder={`请选择${label}`} options={selectOptions} />
      </Form.Item>
    )
  }
  if (field.ui_type === 'Text' || field.ui_type === 'LongText' || field.ui_type === 'Paragraph') {
    return (
      <Form.Item name={field.field_name} label={label} rules={rules}>
        <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} placeholder={`请输入${label}`} />
      </Form.Item>
    )
  }
  return (
    <Form.Item name={field.field_name} label={label} rules={rules}>
      <Input placeholder={`请输入${label}`} />
    </Form.Item>
  )
}