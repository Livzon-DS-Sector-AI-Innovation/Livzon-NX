'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Form, Input, Modal, Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { fetchDepartmentContacts } from '@/lib/api/client/quality'
import { createDeviationReportRecord } from '@/actions/quality-deviation'
import type { DepartmentContact } from '@/types/quality'

interface CreateDeviationReportRecordModalProps {
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

interface FormValues {
  description: string
  product_batch: string
  reporter_open_id: string
}

export function CreateDeviationReportRecordModal({
  open,
  onClose,
  onSuccess,
}: CreateDeviationReportRecordModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const reporterOpenId = Form.useWatch('reporter_open_id', form)

  const { data: contacts = [], isLoading: contactsLoading } = useQuery({
    queryKey: ['quality-department-contacts', 'for-deviation-report'],
    queryFn: () => fetchDepartmentContacts(),
    enabled: open,
  })

  const contactOptions = useMemo(
    () =>
      contacts
        .filter((c) => c.name && c.open_id)
        .map((c: DepartmentContact) => ({
          label: c.name,
          value: c.open_id!,
        })),
    [contacts],
  )

  const selectedDepartment = useMemo(() => {
    if (!reporterOpenId) return null
    const contact = contacts.find((c) => c.open_id === reporterOpenId)
    return contact?.department || null
  }, [reporterOpenId, contacts])

  useEffect(() => {
    if (!open) {
      form.resetFields()
    }
  }, [open, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await createDeviationReportRecord({
        description: values.description.trim(),
        product_batch: values.product_batch.trim(),
        reporter_open_id: values.reporter_open_id,
      })
      message.success('偏差报告记录已创建')
      form.resetFields()
      onClose()
      onSuccess?.()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      const msg = error instanceof Error ? error.message : '创建失败'
      message.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="新建偏差"
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={submitting}
      okText="提交"
      cancelText="取消"
      width={560}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="description"
          label="偏差内容"
          rules={[{ required: true, message: '请输入偏差内容' }]}
        >
          <Input.TextArea
            rows={4}
            placeholder="请输入偏差内容"
            maxLength={2000}
            showCount
          />
        </Form.Item>

        <Form.Item
          name="product_batch"
          label="涉及产品名称/批号"
          rules={[{ required: true, message: '请输入涉及产品名称/批号' }]}
        >
          <Input placeholder="请输入涉及产品名称/批号" maxLength={255} />
        </Form.Item>

        <Form.Item
          name="reporter_open_id"
          label="报告人"
          rules={[{ required: true, message: '请选择报告人' }]}
        >
          <Select
            placeholder="请选择报告人"
            loading={contactsLoading}
            options={contactOptions}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>

        <Form.Item label="部门">
          <Input value={selectedDepartment || ''} disabled placeholder="选择报告人后自动填充" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
