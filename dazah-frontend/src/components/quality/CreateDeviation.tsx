'use client'

import type { Dayjs } from 'dayjs'
import { useRouter } from 'next/navigation'
import { App, Button, Card, DatePicker, Form, Input, Select, Space } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { createFeishuDeviationLedgerRecord } from '@/actions/quality'

interface CreateDeviationFormValues {
  level?: string
  description: string
  affected_items: string
  has_occurred_before?: boolean
  root_cause_analysis?: string
  investigation_completed_at?: Dayjs
  corrective_actions?: string
  material_disposition?: string
  is_closed?: boolean
  close_time?: Dayjs
}

const levelOptions = [
  { label: '重大', value: '重大' },
  { label: '次要', value: '次要' },
  { label: '微小', value: '微小' },
] as Array<{ label: string; value: string }>

const booleanOptions = [
  { label: '是', value: true },
  { label: '否', value: false },
] as Array<{ label: string; value: boolean }>

export function CreateDeviation() {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm<CreateDeviationFormValues>()
  const isClosed = Form.useWatch('is_closed', form)

  const handleSubmit = async (values: CreateDeviationFormValues) => {
    try {
      await createFeishuDeviationLedgerRecord({
        title: values.description.trim(),
        description: values.description.trim(),
        affected_items: values.affected_items.trim(),
        level: values.level ?? null,
        has_occurred_before: values.has_occurred_before ?? null,
        root_cause_analysis: values.root_cause_analysis?.trim() || null,
        investigation_completed_at: values.investigation_completed_at
          ? values.investigation_completed_at.toISOString()
          : null,
        corrective_actions: values.corrective_actions?.trim() || null,
        material_disposition: values.material_disposition?.trim() || null,
        is_closed: values.is_closed ?? false,
        close_time: values.is_closed && values.close_time
          ? values.close_time.toISOString()
          : null,
      })
      message.success('飞书台账已创建')
      router.push('/quality/deviations/ledger')
    } catch (error) {
      message.error(error?.message || '创建失败')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/quality/deviations/ledger')}>
          返回
        </Button>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>新增台账</h1>
      </div>

      <Card>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          onValuesChange={(changedValues, allValues) => {
            if ('is_closed' in changedValues && allValues.is_closed !== true) {
              form.setFieldValue('close_time', undefined)
            }
          }}
          style={{ maxWidth: 800 }}
        >
          <Form.Item
            label="偏差编号"
          >
            <Input value="保存后自动生成" disabled />
          </Form.Item>

          <Form.Item
            name="affected_items"
            label="产品名称/批号"
            rules={[{ required: true, message: '请输入产品名称/批号' }]}
          >
            <Input
              placeholder="请输入产品名称/批号"
              maxLength={255}
            />
          </Form.Item>

          <Form.Item
            name="description"
            label="偏差简要描述"
            rules={[{ required: true, message: '请输入偏差简要描述' }]}
          >
            <Input.TextArea
              rows={5}
              placeholder="请输入偏差简要描述"
              maxLength={2000}
              showCount
            />
          </Form.Item>

          <Form.Item
            name="has_occurred_before"
            label="偏差是否曾发生"
          >
            <Select
              placeholder="请选择"
              options={booleanOptions}
            />
          </Form.Item>

          <Form.Item name="root_cause_analysis" label="根本原因">
            <Input.TextArea rows={4} placeholder="请输入根本原因" />
          </Form.Item>

          <Form.Item name="level" label="偏差等级">
            <Select placeholder="请选择偏差等级" options={levelOptions} />
          </Form.Item>

          <Form.Item name="investigation_completed_at" label="调查完成时间">
            <DatePicker
              showTime
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
            />
          </Form.Item>

          <Form.Item name="corrective_actions" label="纠正预防措施">
            <Input.TextArea rows={4} placeholder="请输入纠正预防措施" />
          </Form.Item>

          <Form.Item name="material_disposition" label="产品/物料处理结果">
            <Input.TextArea rows={4} placeholder="请输入产品/物料处理结果" />
          </Form.Item>

          <Form.Item name="is_closed" label="是否关闭">
            <Select placeholder="请选择" options={booleanOptions} />
          </Form.Item>

          <Form.Item
            name="close_time"
            label="关闭时间"
            rules={[
              {
                validator: async (_rule, value) => {
                  if (isClosed && !value) {
                    throw new Error('请选择关闭时间')
                  }
                },
              },
            ]}
          >
            <DatePicker
              showTime
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
              disabled={!isClosed}
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                保存台账
              </Button>
              <Button onClick={() => router.push('/quality/deviations/ledger')}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
