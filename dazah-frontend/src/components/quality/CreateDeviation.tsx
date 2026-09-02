'use client'

import type { Dayjs } from 'dayjs'
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { components } from '@/types/generated/schema'
import { fetchDeviationReporters } from '@/lib/api/client/deviation-reporters'
import { useRouter } from 'next/navigation'
import { Alert, App, Button, Card, DatePicker, Form, Input, Select, Space } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { createDeviation } from '@/actions/quality-deviation'
import type { DeviationLevel } from '@/types/quality'
import { useDeviationPermissions } from './useDeviationPermissions'

interface CreateDeviationFormValues {
  reporter_open_id: string
  department: string
  level?: DeviationLevel
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
  { label: '严重', value: 'major' },
  { label: '中等', value: 'moderate' },
  { label: '轻微', value: 'minor' },
] as Array<{ label: string; value: DeviationLevel }>

const booleanOptions = [
  { label: '是', value: true },
  { label: '否', value: false },
] as Array<{ label: string; value: boolean }>

export function CreateDeviation() {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm<CreateDeviationFormValues>()
  const isClosed = Form.useWatch('is_closed', form)
  const { canOperate, workflowFieldsReadOnly, authorizationKey } = useDeviationPermissions()
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<{ authorizationKey: string; reporter: components['schemas']['DeviationReporterOption'] } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const submitLock = useRef(false)
  const reporters = useQuery({
    queryKey: ['quality-deviation', 'reporter-options', authorizationKey, search],
    queryFn: ({ signal }) => fetchDeviationReporters(search, signal),
    enabled: canOperate,
    retry: false,
  })
  useEffect(() => {
    const timer = setTimeout(() => setSearch(keyword), 250)
    return () => clearTimeout(timer)
  }, [keyword])
  useEffect(() => { form.resetFields(['reporter_open_id', 'department']) }, [authorizationKey, form])
  const selectedReporter = selected?.authorizationKey === authorizationKey ? selected.reporter : undefined
  const candidates = reporters.data?.data ?? []
  const options = selectedReporter && !candidates.some((item) => item.open_id === selectedReporter.open_id)
    ? [selectedReporter, ...candidates] : candidates

  const handleSubmit = async (values: CreateDeviationFormValues) => {
    if (!canOperate || submitLock.current) return
    if (!selectedReporter || selectedReporter.open_id !== values.reporter_open_id) {
      message.error('请重新选择有效的报告人')
      return
    }
    submitLock.current = true
    setSubmitting(true)
    try {
      await createDeviation({
        title: values.description.trim(),
        reporter_open_id: selectedReporter.open_id,
        department: selectedReporter.department,
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
        is_closed: workflowFieldsReadOnly ? false : values.is_closed ?? false,
        close_time: !workflowFieldsReadOnly && values.is_closed && values.close_time
          ? values.close_time.toISOString()
          : null,
        needs_cross_dept_review: true,
      })
      message.success('台账已创建')
      router.push('/quality/deviations/ledger')
    } catch (error) {
      message.error((error instanceof Error ? error.message : '') || '创建失败')
    } finally {
      submitLock.current = false
      setSubmitting(false)
    }
  }

  if (!canOperate) {
    return <Alert type="info" showIcon title="尚未获得新增偏差记录的操作权限，请联系系统管理员。" />
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
        {reporters.isError && <Alert type="error" showIcon title={reporters.error.message} action={<Button onClick={() => reporters.refetch()}>重试</Button>} />}
        <Form
          form={form}
          layout="vertical"
          disabled={submitting}
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
            name="reporter_open_id"
            label="报告人"
            rules={[{ required: true, message: '请选择报告人' }]}
            extra="选择报告人后自动关联部门；最多显示50人，可输入姓名或部门缩小范围。"
          >
            <Select
              placeholder="输入姓名或部门搜索报告人"
              showSearch
              filterOption={false}
              onSearch={setKeyword}
              loading={reporters.isFetching}
              allowClear
              notFoundContent={reporters.isFetching ? '正在加载报告人' : reporters.isError ? '报告人加载失败，请重试' : '没有匹配的可选报告人'}
              options={options.map((item) => ({ value: item.open_id, label: `${item.name}（${item.department}）` }))}
              onChange={(value: string | undefined) => {
                const reporter = options.find((item) => item.open_id === value)
                setSelected(reporter ? { authorizationKey, reporter } : null)
                form.setFieldValue('department', reporter?.department)
              }}
            />
          </Form.Item>

          <Form.Item
            name="department"
            label="部门"
            rules={[{ required: true, message: '请输入部门' }]}
          >
            <Input
              placeholder="选择报告人后自动关联"
              readOnly
              maxLength={255}
            />
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

          <Form.Item name="is_closed" label="是否关闭" extra={workflowFieldsReadOnly ? '新记录默认为草稿，关闭状态由业务流程维护。' : undefined}>
            <Select placeholder="请选择" options={booleanOptions} disabled={workflowFieldsReadOnly} />
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
              disabled={workflowFieldsReadOnly || !isClosed}
            />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={submitting} disabled={reporters.isError || !selectedReporter}>
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
