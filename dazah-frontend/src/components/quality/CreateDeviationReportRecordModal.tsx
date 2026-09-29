'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Avatar, Form, Input, Modal, Select } from 'antd'
import { UserOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { fetchQualityPersonDirectory } from '@/lib/api/client/quality'
import { createDeviationReportRecord } from '@/actions/quality-deviation'
import type { QualityPersonOption } from '@/types/quality'

// 与偏差报告记录飞书表“涉及产品”（多选）和“事件类型”（单选）的选项保持一致；
// 多选写入飞书不存在的选项时会自动追加，选项以飞书表为准。
export const DEVIATION_PRODUCT_OPTIONS = [
  '霉酚酸',
  '盐酸林可霉素',
  '2%氟苯尼考预混剂',
  '5%芬苯达唑',
  '美伐他汀',
  '洛伐他汀',
  '多拉菌素',
  '其它',
]

export const DEVIATION_EVENT_TYPE_OPTIONS = ['偏差', '异常', 'OOS/OOT', '其他']

interface CreateDeviationReportRecordModalProps {
  open: boolean
  onClose: () => void
  onSuccess?: () => void
}

interface FormValues {
  description: string
  event_type: string
  products: string[]
  batch_numbers: string
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
    queryKey: ['quality-person-directory', 'for-deviation-report'],
    queryFn: () => fetchQualityPersonDirectory(),
    enabled: open,
  })

  const contactOptions = useMemo(
    () =>
      contacts
        .filter((c) => c.name && c.open_id)
        .map((c: QualityPersonOption) => ({
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
        event_type: values.event_type || '偏差',
        products: values.products,
        batch_numbers: values.batch_numbers.trim(),
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
      <Form form={form} layout="vertical" initialValues={{ event_type: '偏差' }}>
        <Form.Item
          name="event_type"
          label="事件类型"
          rules={[{ required: true, message: '请选择事件类型' }]}
        >
          <Select
            placeholder="请选择事件类型"
            options={DEVIATION_EVENT_TYPE_OPTIONS.map((v) => ({ label: v, value: v }))}
          />
        </Form.Item>

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
          name="products"
          label="涉及产品"
          rules={[{ required: true, message: '请选择涉及产品' }]}
        >
          <Select
            mode="multiple"
            placeholder="请选择涉及产品（可多选）"
            options={DEVIATION_PRODUCT_OPTIONS.map((v) => ({ label: v, value: v }))}
            maxTagCount="responsive"
          />
        </Form.Item>

        <Form.Item name="batch_numbers" label="涉及批次">
          <Input placeholder="请输入涉及批次" maxLength={255} />
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
            optionRender={(option) => {
              const contact = contacts.find((c) => c.open_id === option.value)
              if (!contact) return <span>{option.label}</span>
              return (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Avatar
                    size={24}
                    src={contact.avatar_url || undefined}
                    style={{ backgroundColor: contact.avatar_url ? 'transparent' : undefined, flexShrink: 0, fontSize: 12, fontWeight: 700 }}
                    icon={!contact.avatar_url ? <UserOutlined /> : undefined}
                  >
                    {!contact.avatar_url ? (contact.name || '').charAt(0) : undefined}
                  </Avatar>
                  <span>{option.label}</span>
                </div>
              )
            }}
          />
        </Form.Item>

        <Form.Item label="部门">
          <Input value={selectedDepartment || ''} disabled placeholder="选择报告人后自动填充" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
