'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  Table,
  Card,
  Select,
  Tag,
  Typography,
  App,
  Button,
  Modal,
  Form,
  Input,
  InputNumber,
  Space,
  Popconfirm,
  Empty,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { SettingOutlined, PlusOutlined } from '@ant-design/icons'
import {
  getProcessSpecs,
  getProcessSteps,
  getProcessParameters,
  createProcessParameter,
  updateProcessParameter,
  deleteProcessParameter,
} from '@/actions/production'
import type { ProcessSpec, ProcessStep, ProcessParameter, ProcessParameterFormData } from '@/types/production'

const { Title, Text } = Typography

// ═══════════════════════════════════════════
// 参数表单弹窗
// ═══════════════════════════════════════════
function ParamFormModal({
  open,
  editing,
  stepId,
  onCancel,
  onSuccess,
}: {
  open: boolean
  editing: ProcessParameter | null
  stepId: string
  onCancel: () => void
  onSuccess: () => void
}) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const isEdit = !!editing

  useEffect(() => {
    if (open) {
      if (editing) {
        form.setFieldsValue(editing)
      } else {
        form.resetFields()
      }
    }
  }, [open, editing, form])

  const handleOk = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      const data: ProcessParameterFormData = {
        param_name: values.param_name,
        param_code: values.param_code || undefined,
        unit: values.unit || undefined,
        min_value: values.min_value ?? undefined,
        max_value: values.max_value ?? undefined,
        target_value: values.target_value ?? undefined,
        is_critical: values.is_critical ?? false,
        data_type: values.data_type || undefined,
        notes: values.notes || undefined,
      }
      let res
      if (isEdit && editing) {
        res = await updateProcessParameter(editing.id, data)
      } else {
        res = await createProcessParameter({ ...data, step_id: stepId })
      }
      if (res.code === 200) {
        message.success(isEdit ? '更新成功' : '创建成功')
        onSuccess()
      } else {
        message.error(res.message || '操作失败')
      }
    } catch {
      // 表单验证失败
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={isEdit ? '编辑工艺参数' : '新建工艺参数'}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={loading}
      destroyOnHidden
      width={520}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item name="param_name" label="参数名称" rules={[{ required: true, message: '请输入参数名称' }]}>
          <Input placeholder="如: 进料温度" />
        </Form.Item>
        <Space size="middle" wrap>
          <Form.Item name="param_code" label="编码">
            <Input placeholder="如: FEED_TEMP" style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="unit" label="单位">
            <Input placeholder="如: ℃" style={{ width: 80 }} />
          </Form.Item>
          <Form.Item name="data_type" label="数据类型">
            <Select allowClear placeholder="类型" style={{ width: 100 }}
              options={['number', 'text', 'boolean'].map(t => ({ value: t, label: t }))} />
          </Form.Item>
        </Space>
        <Space size="middle" wrap>
          <Form.Item name="min_value" label="最小值">
            <InputNumber placeholder="最小值" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name="max_value" label="最大值">
            <InputNumber placeholder="最大值" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name="target_value" label="目标值">
            <InputNumber placeholder="目标值" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name="is_critical" label="关键参数" valuePropName="checked">
            <Select style={{ width: 90 }} options={[
              { value: true, label: '是' },
              { value: false, label: '否' },
            ]} />
          </Form.Item>
        </Space>
        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={2} placeholder="备注信息" />
        </Form.Item>
      </Form>
    </Modal>
  )
}

// ═══════════════════════════════════════════
// 主页面
// ═══════════════════════════════════════════
export default function ProcessParametersPage() {
  const { message } = App.useApp()

  // 规格
  const [specs, setSpecs] = useState<ProcessSpec[]>([])
  const [selectedSpecId, setSelectedSpecId] = useState<string | undefined>()

  // 步骤
  const [steps, setSteps] = useState<ProcessStep[]>([])
  const [selectedStepId, setSelectedStepId] = useState<string | undefined>()

  // 参数
  const [params, setParams] = useState<ProcessParameter[]>([])
  const [loading, setLoading] = useState(false)

  // 弹窗
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<ProcessParameter | null>(null)

  // 加载规格
  const loadSpecs = useCallback(async () => {
    try {
      const res = await getProcessSpecs({ page: 1, page_size: 200 })
      if (res.code === 200) setSpecs(res.data || [])
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadSpecs() }, [loadSpecs])

  // 加载步骤
  const loadSteps = useCallback(async (specId: string) => {
    try {
      const res = await getProcessSteps(specId)
      if (res.code === 200) setSteps(res.data || [])
    } catch { message.error('加载步骤失败') }
  }, [message])

  useEffect(() => {
    if (selectedSpecId) loadSteps(selectedSpecId)
    else setSteps([])
  }, [selectedSpecId, loadSteps])

  // 加载参数
  const loadParams = useCallback(async (stepId: string) => {
    setLoading(true)
    try {
      const res = await getProcessParameters(stepId)
      if (res.code === 200) setParams(res.data || [])
    } catch { message.error('加载参数失败') }
    finally { setLoading(false) }
  }, [message])

  useEffect(() => {
    if (selectedStepId) loadParams(selectedStepId)
    else setParams([])
  }, [selectedStepId, loadParams])

  const handleDelete = async (id: string) => {
    const res = await deleteProcessParameter(id)
    if (res.code === 200) {
      message.success('删除成功')
      if (selectedStepId) loadParams(selectedStepId)
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const columns: ColumnsType<ProcessParameter> = [
    { title: '参数名称', dataIndex: 'param_name', width: 120, render: (v: string) => <strong>{v}</strong> },
    { title: '编码', dataIndex: 'param_code', width: 100, render: (v: string | null) => v ? <Tag>{v}</Tag> : '-' },
    { title: '单位', dataIndex: 'unit', width: 60, render: (v: string | null) => v || '-' },
    { title: '最小值', dataIndex: 'min_value', width: 80, render: (v: number | null) => v != null ? v : '-' },
    { title: '最大值', dataIndex: 'max_value', width: 80, render: (v: number | null) => v != null ? v : '-' },
    { title: '目标值', dataIndex: 'target_value', width: 80, render: (v: number | null) => v != null ? v : '-' },
    {
      title: '关键参数', dataIndex: 'is_critical', width: 80,
      render: (v: boolean) => v ? <Tag color="red">关键</Tag> : <Tag>普通</Tag>,
    },
    { title: '备注', dataIndex: 'notes', width: 120, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '操作', key: 'actions', width: 120,
      render: (_: any, record: ProcessParameter) => (
        <Space size="small">
          <Button size="small" onClick={() => { setEditing(record); setModalOpen(true) }}>编辑</Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="p-6">
      <div className="mb-4">
        <Title level={4} style={{ margin: 0 }}>
          <SettingOutlined className="mr-2" />
          工艺参数管理
        </Title>
        <Text type="secondary">为工艺步骤配置参数定义（名称、范围、目标值）</Text>
      </div>

      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            placeholder="选择工艺规程"
            allowClear
            value={selectedSpecId}
            onChange={v => { setSelectedSpecId(v); setSelectedStepId(undefined) }}
            style={{ width: 200 }}
            options={specs.map(s => ({ value: s.id, label: `${s.spec_code} - ${s.spec_name || s.product_name || ''}` }))}
          />
          <Select
            placeholder="选择工艺步骤"
            allowClear
            value={selectedStepId}
            onChange={v => setSelectedStepId(v)}
            disabled={!selectedSpecId}
            style={{ width: 200 }}
            options={steps.map(s => ({ value: s.id, label: `步骤${s.step_no}: ${s.step_name}` }))}
          />
          {selectedStepId && (
            <Button type="primary" icon={<PlusOutlined />}
              onClick={() => { setEditing(null); setModalOpen(true) }}>
              新建参数
            </Button>
          )}
        </Space>

        {!selectedStepId ? (
          <Empty description="请先选择工艺规程和步骤" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table
            columns={columns}
            dataSource={params}
            rowKey="id"
            loading={loading}
            size="small"
            scroll={{ x: 900 }}
            pagination={false}
          />
        )}
      </Card>

      {selectedStepId && (
        <ParamFormModal
          open={modalOpen}
          editing={editing}
          stepId={selectedStepId}
          onCancel={() => { setModalOpen(false); setEditing(null) }}
          onSuccess={() => { setModalOpen(false); setEditing(null); loadParams(selectedStepId) }}
        />
      )}
    </div>
  )
}
