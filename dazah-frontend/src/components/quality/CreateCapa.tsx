'use client'

import { useRouter } from 'next/navigation'
import { App, Card, Form, Input, Select, Button, DatePicker, Space } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { createCapa } from '@/actions/quality'

export function CreateCapa() {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm()

  const handleSubmit = async (values: any) => {
    try {
      const result = await createCapa({
        ...values,
        expected_completion_date: values.expected_completion_date?.toISOString(),
      })
      message.success('创建成功')
      router.push('/quality/capas')
    } catch (error: any) {
      message.error(error?.message || '创建失败')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/quality/capas')}>
          返回
        </Button>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>新建CAPA</h1>
      </div>

      <Card>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          style={{ maxWidth: 800 }}
        >
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="请输入CAPA标题" />
          </Form.Item>

          <Form.Item name="source" label="来源">
            <Select
              placeholder="选择来源"
              allowClear
              options={[
                { label: '偏差', value: 'deviation' },
                { label: '审计', value: 'audit' },
                { label: '客户投诉', value: 'customer_complaint' },
                { label: '内部检查', value: 'internal_inspection' },
              ]}
            />
          </Form.Item>

          <Form.Item name="category" label="类别">
            <Select
              placeholder="选择类别"
              allowClear
              options={[
                { label: 'A类', value: 'A' },
                { label: 'B类', value: 'B' },
                { label: 'C类', value: 'C' },
              ]}
            />
          </Form.Item>

          <Form.Item name="root_cause_category" label="根本原因类别">
            <Select
              placeholder="选择原因类别"
              allowClear
              options={[
                { label: '人员', value: '人员' },
                { label: '设施/设备', value: '设施/设备' },
                { label: '产品/物料', value: '产品/物料' },
                { label: '文件', value: '文件' },
                { label: '环境', value: '环境' },
                { label: '其它', value: '其它' },
              ]}
            />
          </Form.Item>

          <Form.Item name="non_conformity_description" label="不符合事项描述">
            <Input.TextArea rows={3} placeholder="描述不符合事项" />
          </Form.Item>

          <Form.Item name="root_cause_analysis" label="根本原因分析">
            <Input.TextArea rows={4} placeholder="分析根本原因" />
          </Form.Item>

          <Form.Item name="capa_content" label="CAPA内容">
            <Input.TextArea rows={4} placeholder="描述CAPA措施内容" />
          </Form.Item>

          <Form.Item name="expected_completion_date" label="预期完成日期">
            <DatePicker showTime style={{ width: '100%' }} placeholder="选择预期完成日期" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                创建CAPA
              </Button>
              <Button onClick={() => router.push('/quality/capas')}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
