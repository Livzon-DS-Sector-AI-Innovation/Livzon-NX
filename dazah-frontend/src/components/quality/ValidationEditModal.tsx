'use client'

import { useEffect, useMemo, useState } from 'react'
import { DatePicker, Form, Input, Modal, Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import type { ValidationListItem } from '@/types/quality'
import { fetchValidationPersonOptions } from '@/lib/api/client/quality'
import {
  FeishuPersonSelect,
  type FeishuPersonValue,
} from '@/components/shared/FeishuPersonSelect'

interface ValidationEditModalProps {
  open: boolean
  saving: boolean
  validationType?: string
  validationTypeLabel: string
  initialValue?: ValidationListItem | null
  /** 年度台账模式：真实年度表没有"验证类别"列，隐藏该字段 */
  hideCategory?: boolean
  /** 当前选择的年度表；空 = 验证总表 */
  year?: number
  onCancel: () => void
  onSubmit: (
    values: Record<string, unknown>,
    targetYear: number,
  ) => Promise<void> | void
}

const statusOptions = [
  { label: '完成', value: '完成' },
  { label: '未完成', value: '未完成' },
  { label: '待完成', value: '待完成' },
]

/** 可写入的验证年度台账（对应验证主计划 Base 的三张年度表） */
const TARGET_YEAR_OPTIONS = [2024, 2025, 2026].map((y) => ({
  label: `${y}年验证台账`,
  value: y,
}))

/** 记录里的人员字段 → 选择器回显值（id 可能是飞书成员字段 id 或 open_id，也可能是纯姓名） */
function toPersonValue(raw: unknown): FeishuPersonValue[] {
  if (!raw) return []
  if (typeof raw === 'string') {
    return raw.trim() ? [{ id: '', name: raw.trim() }] : []
  }
  if (Array.isArray(raw)) {
    return raw
      .map((item) => {
        if (typeof item === 'string') return { id: '', name: item.trim() }
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
  return []
}

export function ValidationEditModal({
  open,
  saving,
  validationType,
  validationTypeLabel,
  initialValue,
  hideCategory,
  year,
  onCancel,
  onSubmit,
}: ValidationEditModalProps) {
  const [form] = Form.useForm()
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null)

  // 部门与人员候选统一来自人事管理-飞书联系人目录（中文/拼音搜索）
  const { data: directory = [], isLoading: directoryLoading } = useQuery({
    queryKey: ['quality-person-directory'],
    queryFn: () => fetchValidationPersonOptions(undefined, 500),
    // 不做前端缓存：每次打开都重查，保证人事-飞书联系人同步后立刻生效
    staleTime: 0,
    enabled: open,
  })

  // 提取去重部门列表
  const departmentOptions = useMemo(
    () =>
      [...new Set(directory.map(p => p.department).filter(Boolean))].map(d => ({
        label: d as string,
        value: d as string,
      })),
    [directory],
  )

  // 编辑回显：已有人员/负责人作为候选项并入（候选中没有的 id 也能正常显示）
  const participantExtras = useMemo(
    () => toPersonValue(initialValue?.participants),
    [initialValue],
  )
  const ownerExtras = useMemo(
    () => toPersonValue(initialValue?.owner_name),
    [initialValue],
  )

  const handleDepartmentChange = (dept: string | undefined) => {
    setSelectedDepartment(dept || null)
  }

  useEffect(() => {
    if (!open) return
    const dept = initialValue?.department || null
    setSelectedDepartment(dept)
    form.setFieldsValue({
      target_year: year ?? new Date().getFullYear(),
      validation_type_label: validationTypeLabel,
      validation_type: initialValue?.validation_type ?? validationType,
      record_code: initialValue?.record_code ?? '',
      title: initialValue?.title ?? '',
      status: initialValue?.status ?? undefined,
      department: initialValue?.department ?? '',
      equipment_code: initialValue?.equipment_code ?? '',
      product_codes: initialValue?.product_codes ?? [],
      planned_end_date:
        initialValue?.planned_end_date
          ? dayjs(initialValue.planned_end_date)
          : null,
      group_chat: initialValue?.group_chat ?? '验证群',
      participants: participantExtras,
      owner_name: ownerExtras[0] ?? undefined,
      plan_name: initialValue?.plan_name ?? '',
      plan_code: initialValue?.plan_code ?? '',
      drafted_at: initialValue?.drafted_at ? dayjs(initialValue.drafted_at) : null,
      approved_at: initialValue?.approved_at ? dayjs(initialValue.approved_at) : null,
      report_no: initialValue?.report_no ?? '',
      drafted_at_1: initialValue?.drafted_at_1 ? dayjs(initialValue.drafted_at_1) : null,
      approved_at_1: initialValue?.approved_at_1 ? dayjs(initialValue.approved_at_1) : null,
      revalidation_cycle_years: initialValue?.revalidation_cycle_years ?? undefined,
    })
  }, [form, initialValue, open, validationType, validationTypeLabel, participantExtras, ownerExtras])

  return (
    <Modal
      title={initialValue ? `编辑${validationTypeLabel}` : `新增${validationTypeLabel}`}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={saving}
      destroyOnHidden
      width={900}
    >
      <div
        style={{
          marginBottom: 16,
          padding: '8px 12px',
          background: 'var(--color-bg-soft, #f5f7fa)',
          borderRadius: 6,
          fontSize: 13,
          color: 'var(--color-steel, #555)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span style={{ whiteSpace: 'nowrap' }}>将写入：</span>
        <Form.Item name="target_year" noStyle>
          <Select
            style={{ width: 200 }}
            disabled={Boolean(initialValue)}
            options={TARGET_YEAR_OPTIONS}
          />
        </Form.Item>
        {Boolean(initialValue) && (
          <span>（编辑时不可更换年度表）</span>
        )}
      </div>
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) => {
          const { target_year, ...rest } = values as Record<string, unknown> & {
            target_year?: number
          }
          const targetYear = Number(target_year) || new Date().getFullYear()
          return onSubmit({
            validation_type: values.validation_type,
            record_code: values.record_code?.trim() || null,
            title: values.title?.trim() || null,
            status: values.status ?? null,
            department: values.department || null,
            equipment_code: values.equipment_code?.trim() || null,
            product_codes: values.product_codes?.length ? values.product_codes : null,
            planned_end_date: values.planned_end_date ? values.planned_end_date.format('YYYY-MM-DD') : null,
            group_chat: values.group_chat?.trim() || null,
            // 人员：[{id, name}]（空数组=清空）；负责人：单条或空数组
            participants: (values.participants ?? []) as FeishuPersonValue[],
            owner_name: values.owner_name ? [values.owner_name as FeishuPersonValue] : [],
            plan_name: values.plan_name?.trim() || null,
            plan_code: values.plan_code?.trim() || null,
            drafted_at: values.drafted_at ? values.drafted_at.format('YYYY-MM-DD') : null,
            approved_at: values.approved_at ? values.approved_at.format('YYYY-MM-DD') : null,
            report_no: values.report_no?.trim() || null,
            drafted_at_1: values.drafted_at_1 ? values.drafted_at_1.format('YYYY-MM-DD') : null,
            approved_at_1: values.approved_at_1 ? values.approved_at_1.format('YYYY-MM-DD') : null,
            revalidation_cycle_years: values.revalidation_cycle_years ?? null,
          }, targetYear)
        }}
      >
        <Form.Item label="台账类型" name="validation_type_label">
          <Input disabled />
        </Form.Item>
        <Form.Item label="记录编号" name="record_code" rules={[{ required: true, message: '请输入记录编号' }]}>
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item label="确认名称" name="title" rules={[{ required: true, message: '请输入确认名称' }]}>
          <Input maxLength={255} />
        </Form.Item>
        <Form.Item
          label="验证类别"
          name="validation_type"
          hidden={hideCategory}
          rules={hideCategory ? [] : [{ required: true, message: '请选择验证类别' }]}
        >
          <Select
            getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
            options={[
              { label: '设备确认', value: 'equipment_qualification' },
              { label: '工艺验证', value: 'process_validation' },
              { label: '清洁验证', value: 'cleaning_validation' },
              { label: '其他验证', value: 'other_validation' },
            ]}
          />
        </Form.Item>
        <Form.Item label="任务状态" name="status">
          <Select
            getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
            allowClear
            options={statusOptions}
          />
        </Form.Item>
        <Form.Item label="部门名称" name="department">
          <Select
            getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
            showSearch
            allowClear
            placeholder="请选择部门"
            loading={directoryLoading}
            options={departmentOptions}
            onChange={handleDepartmentChange}
            filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
          />
        </Form.Item>
        <Form.Item label="设备编码" name="equipment_code">
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item label="产品代码" name="product_codes">
          <Select
            getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
            mode="tags"
            allowClear
            placeholder="请输入或选择产品代码"
          />
        </Form.Item>
        <Form.Item label="验证到期时间" name="planned_end_date">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          label="群组"
          name="group_chat"
          extra="飞书开放接口不支持写入群组字段，新增记录的群组请在多维表格中维护（表内默认群：验证群）"
        >
          <Input maxLength={255} disabled />
        </Form.Item>
        <Form.Item
          label="人员"
          name="participants"
          extra="来自人事管理-飞书联系人，支持中文/全拼/首字母搜索"
        >
          <FeishuPersonSelect multiple extraOptions={participantExtras} />
        </Form.Item>
        <Form.Item
          label="负责人"
          name="owner_name"
          extra="来自人事管理-飞书联系人，支持中文/全拼/首字母搜索"
        >
          <FeishuPersonSelect extraOptions={ownerExtras} placeholder="输入姓名或拼音搜索负责人" />
        </Form.Item>
        <Form.Item label="方案名称" name="plan_name">
          <Input maxLength={255} />
        </Form.Item>
        <Form.Item label="方案编码" name="plan_code">
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item label="起草时间" name="drafted_at">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="批准时间" name="approved_at">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="报告编号" name="report_no">
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item label="报告起草时间" name="drafted_at_1">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="报告批准时间" name="approved_at_1">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="再验证周期（几年）" name="revalidation_cycle_years">
          <Input type="number" min={1} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
