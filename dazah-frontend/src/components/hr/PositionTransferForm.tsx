'use client'

import { useEffect, useState, useCallback } from 'react'
import { App, Modal, Form, Input, DatePicker, Card, Select } from 'antd'
import dayjs from 'dayjs'
import {
  PositionTransferRecord,
  PositionTransferRecordCreateInput,
  PositionTransferRecordUpdateInput,
} from '@/types/hr'
import { createPositionTransfer, updatePositionTransfer } from '@/actions/hr'
import { searchFeishuMembers, type FeishuContactVM } from '@/lib/api/client/hr'

const APPLICANT_CONFIRMATION_DEFAULT = '此申请经审批通过后，本人到原部门办理交接手续，即时与原部门的工作交接清楚。'

interface PositionTransferFormProps {
  open: boolean
  record: PositionTransferRecord | null
  onClose: () => void
  onSuccess: () => void
}

export default function PositionTransferForm({
  open,
  record,
  onClose,
  onSuccess,
}: PositionTransferFormProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [contactOptions, setContactOptions] = useState<{ label: string; value: string; contact?: FeishuContactVM }[]>([])
  const [contactLoading, setContactLoading] = useState(false)
  const isEdit = !!record

  // 飞书联系人搜索
  const handleContactSearch = useCallback(async (keyword: string) => {
    if (!keyword || keyword.length < 1) {
      setContactOptions([])
      return
    }
    setContactLoading(true)
    try {
      const members = await searchFeishuMembers(keyword)
      setContactOptions(
        members.map((m) => ({
          label: `${m.name} - ${m.department || ''}${m.job_title ? ` - ${m.job_title}` : ''}`,
          value: m.name,
          contact: m,
        }))
      )
    } catch {
      setContactOptions([])
    } finally {
      setContactLoading(false)
    }
  }, [])

  // 选择联系人后自动填充签名
  const handleContactSelect = useCallback((value: string, option: any) => {
    const contact = option?.contact as FeishuContactVM | undefined
    if (contact) {
      form.setFieldsValue({ applicant_signature: contact.name })
    }
  }, [form])

  // 生效日期变化 → 自动填充申请人确认日期
  const handleEffectiveDateChange = useCallback((date: dayjs.Dayjs | null) => {
    if (date) {
      form.setFieldsValue({ applicant_confirmation_date: date })
    }
  }, [form])

  useEffect(() => {
    if (open) {
      if (record) {
        const values: any = { ...record }
        if (record.effective_date) {
          values.effective_date = dayjs(record.effective_date)
        }
        if (record.applicant_confirmation_date) {
          values.applicant_confirmation_date = dayjs(record.applicant_confirmation_date)
        }
        form.setFieldsValue(values)
      } else {
        form.resetFields()
        form.setFieldsValue({
          applicant_confirmation_text: APPLICANT_CONFIRMATION_DEFAULT,
        })
      }
    }
  }, [open, record, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      const data: any = { ...values }
      if (data.effective_date) {
        data.effective_date = data.effective_date.format('YYYY-MM-DD')
      }
      if (data.applicant_confirmation_date) {
        data.applicant_confirmation_date = data.applicant_confirmation_date.format('YYYY-MM-DD')
      }

      if (isEdit && record) {
        await updatePositionTransfer(record.id, data as PositionTransferRecordUpdateInput)
        message.success('更新成功')
      } else {
        await createPositionTransfer(data as PositionTransferRecordCreateInput)
        message.success('创建成功')
      }
      onSuccess()
      onClose()
    } catch (err) {
      if ((typeof err === 'object' && err !== null && 'errorFields' in err)) return
      message.error((err instanceof Error ? err.message : '') || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={isEdit ? '编辑岗位调动记录' : '新增岗位调动记录'}
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      width={680}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        {/* ── 申请人 ── */}
        <Form.Item
          name="employee_name"
          label="申请人"
          rules={[{ required: true, message: '请选择申请人' }]}
        >
          <Select
            showSearch
            placeholder="请输入姓名搜索飞书联系人"
            filterOption={false}
            onSearch={handleContactSearch}
            onSelect={handleContactSelect}
            loading={contactLoading}
            options={contactOptions}
            notFoundContent={contactLoading ? '搜索中...' : '请输入姓名搜索'}
            allowClear
          />
        </Form.Item>

        {/* ── 原信息（加框） ── */}
        <Card size="small" title="原信息" className="mb-4">
          <Form.Item name="department_before" label="原部门">
            <Input placeholder="请输入原部门" />
          </Form.Item>
          <Form.Item name="sub_department_before" label="二级部门">
            <Input placeholder="请输入二级部门" />
          </Form.Item>
          <Form.Item name="original_position" label="原职位">
            <Input placeholder="请输入原职位" />
          </Form.Item>
        </Card>

        {/* ── 申请信息（加框） ── */}
        <Card size="small" title="申请信息" className="mb-4">
          <Form.Item
            name="apply_department"
            label="申请部门"
            rules={[{ required: true, message: '请输入申请部门' }]}
          >
            <Input placeholder="请输入申请部门" />
          </Form.Item>
          <Form.Item name="sub_department_after" label="二级部门（变动后）">
            <Input placeholder="请输入二级部门（变动后）" />
          </Form.Item>
          <Form.Item name="apply_position" label="申请职位">
            <Input placeholder="请输入申请职位" />
          </Form.Item>
        </Card>

        {/* ── 生效日期+联系电话（加框） ── */}
        <Card size="small" className="mb-4">
          <Form.Item
            name="effective_date"
            label="生效日期"
            rules={[{ required: true, message: '请选择生效日期' }]}
          >
            <DatePicker className="w-full" onChange={handleEffectiveDateChange} />
          </Form.Item>
          <Form.Item name="contact_phone" label="联系电话">
            <Input placeholder="请输入联系电话" />
          </Form.Item>
        </Card>

        {/* ── 申请人确认 ── */}
        <Form.Item name="applicant_confirmation_text" label="申请人确认说明">
          <Input.TextArea rows={3} placeholder="申请人确认说明" />
        </Form.Item>

        <div className="grid grid-cols-2 gap-4">
          <Form.Item name="applicant_signature" label="申请人签名">
            <Input placeholder="默认=申请人姓名" />
          </Form.Item>
          <Form.Item name="applicant_confirmation_date" label="申请人确认日期">
            <DatePicker className="w-full" placeholder="默认=生效日期" />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  )
}
