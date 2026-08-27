'use client'

import { useState, useEffect } from 'react'
import { App, AutoComplete, Button, Card, Form, InputNumber, Select, Spin, Input } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import { createAnnualTrainingPlan } from '@/actions/hr'
import { fetchTrainingDepartments } from '@/lib/api/client/hr'
import { with201SubDepts } from './trainingDept'

export default function AnnualPlanForm() {
  const { message } = App.useApp()

  const router = useRouter()
  const [form] = Form.useForm()
  const [departments, setDepartments] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    queueMicrotask(() => setLoading(true))
    fetchTrainingDepartments()
      .then((names) => {
        setDepartments(with201SubDepts(names))
      })
      .catch(() => {
        message.error('加载部门列表失败')
      })
      .finally(() => setLoading(false))
  }, [message])

  const handleSubmit = async (values: { year: number; department: string; plan_level: string }) => {
    setSubmitting(true)
    try {
      const res = await createAnnualTrainingPlan({
        year: values.year,
        department: values.department,
        plan_level: values.plan_level,
      })
      message.success('年度培训计划创建成功')
      const planId = res.data?.id
      if (planId) {
        router.push(`/hr/training/annual-plan?id=${planId}`)
      } else {
        router.push('/hr/training/annual-plan')
      }
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spin size="large" description="加载中..." />
      </div>
    )
  }

  return (
    <Card className="max-w-xl">
      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{ year: new Date().getFullYear(), plan_level: '公司级' }}
      >
        <Form.Item
          label="年度"
          name="year"
          rules={[{ required: true, message: '请输入年度' }]}
        >
          <InputNumber style={{ width: '100%' }} min={2000} max={2100} />
        </Form.Item>

        <Form.Item
          label="计划级别"
          name="plan_level"
          rules={[{ required: true, message: '请选择计划级别' }]}
        >
          <Select
            options={[
              { label: '公司级', value: '公司级' },
              { label: '部门级', value: '部门级' },
            ]}
            placeholder="选择计划级别"
            onChange={(value: string) => {
              if (value === '公司级') {
                form.setFieldValue('department', '公司')
              } else {
                form.setFieldValue('department', undefined)
              }
            }}
          />
        </Form.Item>

        <Form.Item noStyle shouldUpdate={(prev, cur) => prev.plan_level !== cur.plan_level}>
          {({ getFieldValue }) =>
            getFieldValue('plan_level') === '部门级' ? (
              <Form.Item
                label="部门"
                name="department"
                rules={[{ required: true, message: '请选择部门' }]}
              >
                <AutoComplete
                  placeholder="选择或输入部门"
                  options={departments.map((d) => ({ value: d }))}
                  filterOption={(input, option) =>
                    (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
            ) : (
              <Form.Item label="部门">
                <Input disabled value="公司" />
                <Form.Item name="department" hidden initialValue="公司">
                  <Input />
                </Form.Item>
              </Form.Item>
            )
          }
        </Form.Item>

        <Form.Item className="mb-0">
          <Button
            type="primary"
            htmlType="submit"
            icon={<SaveOutlined />}
            loading={submitting}
          >
            创建计划
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}
