'use client'

import { useEffect, useState } from 'react'
import { DatePicker, Form, Input, Modal, Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import dayjs from 'dayjs'
import type { ValidationListItem, DepartmentContact } from '@/types/quality'
import { fetchDepartmentContacts } from '@/lib/api/client/quality'

interface ValidationEditModalProps {
  open: boolean
  saving: boolean
  validationType?: string
  validationTypeLabel: string
  initialValue?: ValidationListItem | null
  onCancel: () => void
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void
}

const statusOptions = [
  { label: '完成', value: '完成' },
  { label: '未完成', value: '未完成' },
  { label: '待完成', value: '待完成' },
]

export function ValidationEditModal({
  open,
  saving,
  validationType,
  validationTypeLabel,
  initialValue,
  onCancel,
  onSubmit,
}: ValidationEditModalProps) {
  const [form] = Form.useForm()
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null)

  // 加载部门联系人数据（共享缓存，仅当弹窗打开时启用）
  const { data: contacts = [], isLoading: contactsLoading } = useQuery<DepartmentContact[]>({
    queryKey: ['quality-department-contacts'],
    queryFn: fetchDepartmentContacts,
    enabled: open,
  })

  // 提取去重部门列表
  const departmentOptions = [...new Set(contacts.map(c => c.department).filter(Boolean))].map(d => ({
    label: d,
    value: d,
  }))

  // 当前部门下的人员
  const departmentPeople = selectedDepartment
    ? contacts.filter(c => c.department === selectedDepartment)
    : contacts

  const peopleOptions = departmentPeople.map(c => ({
    label: c.name || c.open_id || '',
    value: c.name || c.open_id || '',
  }))

  // 选部门时：更新人员选项，自动填负责人
  const handleDepartmentChange = (dept: string | undefined) => {
    setSelectedDepartment(dept || null)
    form.setFieldsValue({ participants: undefined, owner_name: undefined })
    if (dept) {
      const head = contacts.find(c => c.department === dept && c.department_head_name)
      if (head?.department_head_name) {
        form.setFieldsValue({ owner_name: head.department_head_name })
      }
    }
  }

  useEffect(() => {
    if (!open) return
    const dept = initialValue?.department || null
    setSelectedDepartment(dept)
    form.setFieldsValue({
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
      participants: initialValue?.participants
        ? (Array.isArray(initialValue.participants)
            ? initialValue.participants
            : String(initialValue.participants).split(',').map(s => s.trim()).filter(Boolean))
        : [],
      owner_name: initialValue?.owner_name ?? '',
      plan_name: initialValue?.plan_name ?? '',
      plan_code: initialValue?.plan_code ?? '',
      drafted_at: initialValue?.drafted_at ? dayjs(initialValue.drafted_at) : null,
      approved_at: initialValue?.approved_at ? dayjs(initialValue.approved_at) : null,
      report_no: initialValue?.report_no ?? '',
      drafted_at_1: initialValue?.drafted_at_1 ? dayjs(initialValue.drafted_at_1) : null,
      approved_at_1: initialValue?.approved_at_1 ? dayjs(initialValue.approved_at_1) : null,
      revalidation_cycle_years: initialValue?.revalidation_cycle_years ?? undefined,
    })
  }, [form, initialValue, open, validationType, validationTypeLabel])

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
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onSubmit({
            validation_type: values.validation_type,
            record_code: values.record_code?.trim() || null,
            title: values.title?.trim() || null,
            status: values.status ?? null,
            department: values.department || null,
            equipment_code: values.equipment_code?.trim() || null,
            product_codes: values.product_codes?.length ? values.product_codes : null,
            planned_end_date: values.planned_end_date ? values.planned_end_date.format('YYYY-MM-DD') : null,
            group_chat: values.group_chat?.trim() || null,
            participants: values.participants || null,
            owner_name: values.owner_name || null,
            plan_name: values.plan_name?.trim() || null,
            plan_code: values.plan_code?.trim() || null,
            drafted_at: values.drafted_at ? values.drafted_at.format('YYYY-MM-DD') : null,
            approved_at: values.approved_at ? values.approved_at.format('YYYY-MM-DD') : null,
            report_no: values.report_no?.trim() || null,
            drafted_at_1: values.drafted_at_1 ? values.drafted_at_1.format('YYYY-MM-DD') : null,
            approved_at_1: values.approved_at_1 ? values.approved_at_1.format('YYYY-MM-DD') : null,
            revalidation_cycle_years: values.revalidation_cycle_years ?? null,
          })
        }
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
            showSearch
            allowClear
            placeholder="请选择部门"
            loading={contactsLoading}
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
        <Form.Item label="群组" name="group_chat">
          <Input maxLength={255} />
        </Form.Item>
        <Form.Item label="人员" name="participants">
          <Select
            getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
            mode="multiple"
            allowClear
            placeholder={selectedDepartment ? '请选择人员' : '请先选择部门'}
            options={peopleOptions}
            filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
          />
        </Form.Item>
        <Form.Item label="负责人" name="owner_name">
          <Select
            getPopupContainer={(triggerNode) => triggerNode.parentElement || triggerNode.parentNode as HTMLElement}
            allowClear
            placeholder="选择部门后自动填入"
            options={peopleOptions}
            filterOption={(input, option) => (option?.label as string)?.toLowerCase().includes(input.toLowerCase())}
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
      </Form>
    </Modal>
  )
}
