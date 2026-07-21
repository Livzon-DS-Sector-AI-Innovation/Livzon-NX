'use client'

"use client"

'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Card,
  Form,
  Input,
  Button,
  Typography,
  Row,
  Col,
  Space,
  Upload,
  Steps,
} from 'antd'
import { ArrowLeftOutlined, UploadOutlined, FileTextOutlined, ThunderboltOutlined } from '@ant-design/icons'
import {
  createHazardIdentification,
  submitHazardIdentification,
  uploadHazardAttachment,
} from '@/actions/safety'
import { App } from 'antd'

const { Title, Text } = Typography

export default function NewHazardIdentificationPage() {
  const router = useRouter()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [submitType, setSubmitType] = useState<'save' | 'submit'>('save')
  const { message } = App.useApp()

  const handleSubmit = async (saveOnly: boolean) => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      setSubmitType(saveOnly ? 'save' : 'submit')

      const createRes = await createHazardIdentification({
        hazard_id_no: values.hazard_id_no,
        department: values.department,
        position: values.position,
        production_step: values.production_step,
        notes: values.notes,
      })

      if (createRes.code !== 200) {
        message.error(createRes.message || '创建失败')
        setLoading(false)
        return
      }

      const recordId = createRes.data.id

      if (values.attachment?.length > 0) {
        const file = values.attachment[0].originFileObj
        if (file) {
          await uploadHazardAttachment(recordId, file)
        }
      }

      if (!saveOnly) {
        const submitRes = await submitHazardIdentification(recordId)
        if (submitRes.code !== 200) {
          message.error(submitRes.message || '提交失败')
          setLoading(false)
          return
        }
      }

      message.success(saveOnly ? '保存成功' : '提交成功，进入AI辨识流程')
      router.push(`/safety/hazard-identification/${recordId}`)
    } catch {
      if (!loading) {
        message.error('请完善表单信息')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 800, margin: '0 auto' }}>
      {/* 返回 */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => router.push('/safety/hazard-identification')}
        style={{ marginBottom: 24 }}
      >
        返回列表
      </Button>

      {/* 步骤引导 */}
      <Card
        style={{ marginBottom: 24, borderRadius: 12, border: '1px solid #e5e3df', background: '#fafaf9' }}
        styles={{ body: { padding: '16px 24px' } }}
      >
        <Steps
          current={0}
          size="small"
          items={[
            { title: '填写基础信息', icon: <FileTextOutlined /> },
            { title: '上传岗位资料', icon: <UploadOutlined /> },
            { title: '提交进入AI流程', icon: <ThunderboltOutlined /> },
          ]}
        />
      </Card>

      {/* 表单 */}
      <Card style={{ borderRadius: 12, border: '1px solid #e5e3df' }}>
        <Title level={5} style={{ marginBottom: 20, color: '#1a1a1a' }}>
          ① 基础信息
        </Title>

        <Form
          form={form}
          layout="vertical"
          initialValues={{
            hazard_id_no: `HI-${Date.now().toString(36).toUpperCase()}`,
          }}
        >
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="hazard_id_no"
                label="危险源编号"
                rules={[{ required: true, message: '请输入编号' }]}
              >
                <Input placeholder="自动生成或手动输入" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="department"
                label="部门"
                rules={[{ required: true, message: '请输入部门' }]}
              >
                <Input placeholder="如：提取一车间" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="position"
                label="岗位"
                rules={[{ required: true, message: '请输入岗位' }]}
              >
                <Input placeholder="如：离心操作岗" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="production_step"
            label="生产步骤"
            rules={[{ required: true, message: '请输入生产步骤' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="详细描述生产步骤，包括操作名称、操作过程、涉及的设备设施和原辅料等"
            />
          </Form.Item>

          {/* 附件上传区 */}
          <div style={{ marginBottom: 24 }}>
            <Title level={5} style={{ marginBottom: 4, color: '#1a1a1a' }}>
              ② 岗位资料附件
            </Title>
            <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
              AI 将据此解析识别危险源（可选）
            </Text>

            <Form.Item
              name="attachment"
              valuePropName="fileList"
              getValueFromEvent={(e: unknown) =>
                Array.isArray(e) ? e : (e as { fileList?: unknown[] })?.fileList ?? []
              }
              noStyle
            >
              <Upload.Dragger
                maxCount={1}
                beforeUpload={() => false}
                accept=".pdf,.docx,.xlsx,.xls,.txt,.md"
                style={{ borderRadius: 12 }}
              >
                <div style={{ padding: '20px 0' }}>
                  <UploadOutlined style={{ fontSize: 32, color: '#5645d4' }} />
                  <p style={{ marginTop: 8, color: '#37352f' }}>拖拽或点击上传 SOP/操作规程</p>
                  <p style={{ color: '#787671', fontSize: 12 }}>
                    支持 PDF、Word、Excel、文本文件
                  </p>
                </div>
              </Upload.Dragger>
            </Form.Item>
          </div>

          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="可选备注信息" />
          </Form.Item>

          <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', paddingTop: 16, borderTop: '1px solid #e5e3df' }}>
            <Button onClick={() => router.push('/safety/hazard-identification')}>
              取消
            </Button>
            <Button
              loading={loading && submitType === 'save'}
              onClick={() => handleSubmit(true)}
            >
              仅保存草稿
            </Button>
            <Button
              type="primary"
              loading={loading && submitType === 'submit'}
              onClick={() => handleSubmit(false)}
            >
              提交并进入AI流程
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  )
}
