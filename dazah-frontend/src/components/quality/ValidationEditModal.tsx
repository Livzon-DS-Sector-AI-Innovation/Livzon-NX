'use client'

import { useEffect, useState } from 'react'
import { DatePicker, Form, Input, Modal, Select } from 'antd'
import dayjs from 'dayjs'
import type { FeishuValidationItem, DepartmentContact } from '@/types/quality'
import { fetchDepartmentContacts } from '@/lib/api/quality'

interface ValidationEditModalProps {
  open: boolean
  saving: boolean
  mode: 'master' | 'child'
  validationType?: string
  validationTypeLabel: string
  initialValue?: FeishuValidationItem | null
  onCancel: () => void
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void
}

const statusOptions = [
  { label: '完成', value: '完成' },
  { label: '未完成', value: '未完成' },
]

export function ValidationEditModal({
  open,
  saving,
  mode,
  validationType,
  validationTypeLabel,
  initialValue,
  onCancel,
  onSubmit,
}: ValidationEditModalProps) {
  const [form] = Form.useForm()
  const [contacts, setContacts] = useState<DepartmentContact[]>([])
  const [contactsLoading, setContactsLoading] = useState(false)
  const isMaster = mode === 'master'

  useEffect(() => {
    if (!open) return
    let cancelled = false
    async function load() {
      setContactsLoading(true)
      try {
        const items = await fetchDepartmentContacts()
        if (!cancelled) setContacts(items)
      } catch {
        // 静默失败
      } finally {
        if (!cancelled) setContactsLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [open])

  const contactOptions = contacts
    .map((c) => ({
      label: `${c.name || '未命名'} (${c.department || '未知部门'})`,
      value: c.name || '',
    }))
    .filter((c) => c.value)

  const departmentOptions = Array.from(
    new Set(contacts.map((c) => c.department).filter(Boolean) as string[])
  )
    .sort((a, b) => a.localeCompare(b, 'zh-CN'))
    .map((d) => ({ label: d, value: d }))

  useEffect(() => {
    if (!open) return
    const typed = initialValue as FeishuValidationItem | null
    form.setFieldsValue({
      validation_type_label: validationTypeLabel,
      validation_type: typed?.validation_type ?? validationType,
      title: typed?.title ?? '',
      status: typed?.status ?? undefined,
      department: typed?.department ?? '',
      equipment_code: typed?.equipment_code ?? '',
      product_codes: Array.isArray(typed?.product_codes)
        ? typed.product_codes
        : typed?.product_codes
          ? [typed.product_codes]
          : [],
      planned_end_date: typed?.planned_end_date ?? '',
      group_chat: typed?.group_chat ?? '',
      participants: typed?.participants
        ? typed.participants.split('、').filter(Boolean)
        : [],
      owner_name: typed?.owner_name ?? '',
      plan_name: typed?.plan_name ?? '',
      plan_code: typed?.plan_code ?? '',
      drafted_at: typed?.drafted_at ? dayjs(typed.drafted_at) : null,
      approved_at: typed?.approved_at ? dayjs(typed.approved_at) : null,
      report_no: typed?.report_no ?? '',
      drafted_at_1: typed?.drafted_at_1 ? dayjs(typed.drafted_at_1) : null,
      approved_at_1: typed?.approved_at_1 ? dayjs(typed.approved_at_1) : null,
      revalidation_cycle_years: typed?.revalidation_cycle_years ?? undefined,
    })
  }, [form, initialValue, open, validationType, validationTypeLabel])

  const buildSubmitPayload = (values: Record<string, unknown>): Record<string, unknown> => {
    const participantsRaw = values.participants
    const participantsStr =
      Array.isArray(participantsRaw)
        ? participantsRaw.filter(Boolean).join('、')
        : String(participantsRaw || '').trim() || null

    return {
      validation_type: values.validation_type || validationType,
      title: String(values.title || '').trim(),
      status: values.status ?? null,
      department: String(values.department || '').trim() || null,
      equipment_code: String(values.equipment_code || '').trim() || null,
      product_codes: Array.isArray(values.product_codes) && values.product_codes.length > 0
        ? values.product_codes
        : null,
      planned_end_date: String(values.planned_end_date || '').trim() || null,
      group_chat: String(values.group_chat || '').trim() || null,
      participants: participantsStr,
      owner_name: String(values.owner_name || '').trim() || null,
      plan_name: String(values.plan_name || '').trim() || null,
      plan_code: String(values.plan_code || '').trim() || null,
      drafted_at: values.drafted_at
        ? (values.drafted_at as dayjs.Dayjs).format('YYYY-MM-DD')
        : null,
      approved_at: values.approved_at
        ? (values.approved_at as dayjs.Dayjs).format('YYYY-MM-DD')
        : null,
      report_no: String(values.report_no || '').trim() || null,
      drafted_at_1: values.drafted_at_1
        ? (values.drafted_at_1 as dayjs.Dayjs).format('YYYY-MM-DD')
        : null,
      approved_at_1: values.approved_at_1
        ? (values.approved_at_1 as dayjs.Dayjs).format('YYYY-MM-DD')
        : null,
      revalidation_cycle_years: values.revalidation_cycle_years ?? null,
    }
  }

  return (
    <Modal
      title={initialValue ? `编辑${validationTypeLabel}` : `新增${validationTypeLabel}`}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={saving}
      destroyOnHidden
      width={isMaster ? 700 : 900}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) => onSubmit(buildSubmitPayload(values))}
      >
        {isMaster ? (
          <>
            <Form.Item label="确认名称" name="title" rules={[{ required: true, message: '请输入确认名称' }]}>
              <Input maxLength={255} />
            </Form.Item>
            <Form.Item label="验证类别" name="validation_type" rules={[{ required: true, message: '请选择验证类别' }]}>
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
                allowClear
                showSearch
                loading={contactsLoading}
                placeholder="选择部门（来源于部门联系人）"
                options={departmentOptions}
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
            <Form.Item label="验证到期时间" name="planned_end_date" help="格式如 2026.02">
              <Input maxLength={20} placeholder="2026.02" />
            </Form.Item>
            <Form.Item label="群组" name="group_chat">
              <Input maxLength={255} />
            </Form.Item>
            <Form.Item label="人员" name="participants">
              <Select
                getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
                mode="multiple"
                allowClear
                showSearch
                loading={contactsLoading}
                placeholder="选择人员（来源于部门联系人）"
                options={contactOptions}
              />
            </Form.Item>
            <Form.Item label="负责人" name="owner_name">
              <Select
                getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
                allowClear
                showSearch
                loading={contactsLoading}
                placeholder="选择负责人（来源于部门联系人）"
                options={contactOptions}
              />
            </Form.Item>
          </>
        ) : (
          <>
            <Form.Item label="台账类型" name="validation_type_label">
              <Input disabled />
            </Form.Item>
            <Form.Item label="确认名称" name="title">
              <Input maxLength={255} disabled />
            </Form.Item>
            <Form.Item label="验证类别" name="validation_type_label">
              <Input disabled />
            </Form.Item>
            <Form.Item label="任务状态" name="status">
              <Select
                getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
                allowClear
                options={statusOptions}
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
            <Form.Item label="验证到期时间" name="planned_end_date" help="格式如 2026.02">
              <Input maxLength={20} placeholder="2026.02" />
            </Form.Item>
            <Form.Item label="群组" name="group_chat">
              <Input maxLength={255} />
            </Form.Item>
            <Form.Item label="人员" name="participants">
              <Select
                getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
                mode="multiple"
                allowClear
                showSearch
                loading={contactsLoading}
                placeholder="选择人员（来源于部门联系人）"
                options={contactOptions}
              />
            </Form.Item>
            <Form.Item label="负责人" name="owner_name">
              <Select
                getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
                allowClear
                showSearch
                loading={contactsLoading}
                placeholder="选择负责人（来源于部门联系人）"
                options={contactOptions}
              />
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
          </>
        )}
      </Form>
    </Modal>
  )
}
