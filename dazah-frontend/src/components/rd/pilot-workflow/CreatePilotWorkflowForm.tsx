'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Form, Input, InputNumber, Select, Button, Card, Space, App } from 'antd'
import { createPilotWorkflow } from '@/actions/rd'

const EQUIPMENT_TYPES = [
  { value: '反应釜', label: '反应釜' },
  { value: '结晶釜', label: '结晶釜' },
  { value: '高压釜', label: '高压釜' },
]

export function CreatePilotWorkflowForm() {
  const router = useRouter()
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  const handleSubmit = async (values: {
    product_name: string
    scale_up_ratio: number
    equipment_type: string
    equipment_volume: number
  }) => {
    setLoading(true)
    try {
      const workflow = await createPilotWorkflow(values) as { id: string }
      message.success('工作流创建成功')
      router.push(`/rd/pilot-workflow/${workflow.id}`)
    } catch (err) {
      message.error('创建失败: ' + (err instanceof Error ? err.message : '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6">
      <h1 className="mb-6 text-xl font-semibold">新建中试研究</h1>

      <Card style={{ maxWidth: 600 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{ scale_up_ratio: 10, equipment_volume: 100 }}
        >
          <Form.Item
            name="product_name"
            label="产品名称"
            rules={[{ required: true, message: '请输入产品名称' }]}
          >
            <Input placeholder="如：阿莫西林" />
          </Form.Item>

          <Form.Item
            name="scale_up_ratio"
            label="放大倍数"
            rules={[{ required: true, message: '请输入放大倍数' }]}
          >
            <Space.Compact style={{ width: '100%' }}>
              <InputNumber min={1} max={10000} style={{ width: '100%' }} placeholder="输入放大倍数" />
              <Input style={{ width: 60, textAlign: 'center' }} placeholder="x" disabled />
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="equipment_type"
            label="设备类型"
            rules={[{ required: true, message: '请选择设备类型' }]}
          >
            <Select placeholder="选择设备类型" options={EQUIPMENT_TYPES} />
          </Form.Item>

          <Form.Item
            name="equipment_volume"
            label="设备容积 (L)"
            rules={[{ required: true, message: '请输入设备容积' }]}
          >
            <Space.Compact style={{ width: '100%' }}>
              <InputNumber min={1} max={100000} style={{ width: '100%' }} placeholder="输入设备容积" />
              <Input style={{ width: 60, textAlign: 'center' }} placeholder="L" disabled />
            </Space.Compact>
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              创建工作流
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
