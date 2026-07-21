'use client'

import { useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons'

import {
  createProductionFeishuSyncBinding,
  deleteProductionFeishuSyncBinding,
  executeProductionFeishuSyncBinding,
  previewProductionFeishuSyncBinding,
  updateProductionFeishuSyncBinding,
} from '@/actions/production'
import type { components } from '@/types/generated/schema'
import type { ProductionFeishuConfig } from '@/types/production'

type SyncBinding = components['schemas']['ProductionFeishuSyncBindingResponse']
type SyncBindingCreate = components['schemas']['ProductionFeishuSyncBindingCreate']
type SyncBindingUpdate = components['schemas']['ProductionFeishuSyncBindingUpdate']

type BindingFormValues = Omit<SyncBindingCreate, 'field_mapping'> & {
  field_mapping_text?: string
}

interface ProductionFeishuSyncBindingPanelProps {
  initialBindings: SyncBinding[]
  configs: ProductionFeishuConfig[]
}

function cleanOptionalText(value?: string | null) {
  const cleaned = value?.trim()
  return cleaned || undefined
}

function parseFieldMapping(value?: string) {
  if (!value?.trim()) return {}
  const parsed: unknown = JSON.parse(value)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('字段映射必须是 JSON 对象，例如 {"product_name":"产品名称"}')
  }
  return Object.fromEntries(
    Object.entries(parsed).map(([key, field]) => {
      if (typeof field !== 'string' || !field.trim()) {
        throw new Error('字段映射的值必须是非空字符串')
      }
      return [key.trim(), field.trim()]
    }),
  )
}

export function ProductionFeishuSyncBindingPanel({
  initialBindings,
  configs,
}: ProductionFeishuSyncBindingPanelProps) {
  const { message } = App.useApp()
  const [bindings, setBindings] = useState(initialBindings)
  const [editing, setEditing] = useState<SyncBinding | null>(null)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [runningBindingId, setRunningBindingId] = useState<string | null>(null)
  const [form] = Form.useForm<BindingFormValues>()

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      config_id: configs.find((config) => config.id)?.id || '',
      binding_name: '',
      sync_target: '',
      table_id: '',
      field_mapping_text: '{}',
      is_active: false,
    })
    setOpen(true)
  }

  const openEdit = (binding: SyncBinding) => {
    setEditing(binding)
    form.setFieldsValue({
      config_id: binding.config_id,
      binding_name: binding.binding_name,
      sync_target: binding.sync_target,
      product_name: binding.product_name || undefined,
      workshop_code: binding.workshop_code || undefined,
      table_id: binding.table_id,
      field_mapping_text: JSON.stringify(binding.field_mapping || {}, null, 2),
      is_active: binding.is_active,
      remark: binding.remark || undefined,
    })
    setOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const fieldMapping = parseFieldMapping(values.field_mapping_text)
      const payload = {
        config_id: values.config_id,
        binding_name: values.binding_name.trim(),
        sync_target: values.sync_target.trim(),
        product_name: cleanOptionalText(values.product_name),
        workshop_code: cleanOptionalText(values.workshop_code),
        table_id: values.table_id.trim(),
        field_mapping: fieldMapping,
        is_active: values.is_active,
        remark: cleanOptionalText(values.remark),
      }
      setSubmitting(true)
      const response = editing
        ? await updateProductionFeishuSyncBinding(editing.id, payload satisfies SyncBindingUpdate)
        : await createProductionFeishuSyncBinding(payload satisfies SyncBindingCreate)
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '保存同步绑定失败')
        return
      }
      setBindings((current) =>
        editing
          ? current.map((item) => (item.id === editing.id ? response.data : item))
          : [response.data, ...current],
      )
      message.success('同步绑定已保存；尚不会自动执行同步')
      setOpen(false)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '字段映射格式不正确')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (binding: SyncBinding) => {
    const response = await deleteProductionFeishuSyncBinding(binding.id)
    if (response.code !== 200) {
      message.error(response.message || '删除同步绑定失败')
      return
    }
    setBindings((current) => current.filter((item) => item.id !== binding.id))
    message.success('同步绑定已删除')
  }

  const handlePreview = async (binding: SyncBinding) => {
    try {
      setRunningBindingId(binding.id)
      const response = await previewProductionFeishuSyncBinding(binding.id)
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '读取飞书预览失败')
        return
      }
      message.success(
        `已读取 ${response.data.records.length} 条样本记录、${response.data.fields.length} 个字段`,
      )
    } catch (error) {
      message.error(error instanceof Error ? error.message : '读取飞书预览失败')
    } finally {
      setRunningBindingId(null)
    }
  }

  const handleRun = async (binding: SyncBinding, dryRun: boolean) => {
    try {
      setRunningBindingId(binding.id)
      const response = await executeProductionFeishuSyncBinding(binding.id, {
        dry_run: dryRun,
      })
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '同步运行失败')
        return
      }
      const run = response.data
      setBindings((current) =>
        current.map((item) =>
          item.id === binding.id
            ? {
                ...item,
                last_status: run.status,
                last_run_at: run.finished_at || run.started_at,
                last_error: run.error_summary,
              }
            : item,
        ),
      )
      const summary = `新增 ${run.created_count}，更新 ${run.updated_count}，跳过 ${run.skipped_count}`
      if (run.status === 'success') {
        message.success(`${dryRun ? '试运行' : '同步'}完成：${summary}`)
      } else {
        message.error(run.error_summary || `同步失败：${summary}`)
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步运行失败')
    } finally {
      setRunningBindingId(null)
    }
  }

  const columns: ColumnsType<SyncBinding> = [
    {
      title: '绑定 / 目标',
      key: 'name',
      render: (_, record) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>{record.binding_name}</Typography.Text>
          <Typography.Text type="secondary">{record.sync_target}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '飞书表',
      dataIndex: 'table_id',
      ellipsis: true,
    },
    {
      title: '范围',
      key: 'scope',
      render: (_, record) =>
        [record.product_name, record.workshop_code].filter(Boolean).join(' / ') || '全部',
    },
    {
      title: '状态',
      key: 'status',
      render: (_, record) => (
        <Space orientation="vertical" size={2}>
          <Tag color={record.is_active ? 'green' : 'default'}>
            {record.is_active ? '已启用' : '未启用'}
          </Tag>
          <Typography.Text type="secondary">{record.last_status}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 300,
      render: (_, record) => (
        <Space>
          <Button
            icon={<EyeOutlined />}
            loading={runningBindingId === record.id}
            size="small"
            onClick={() => handlePreview(record)}
          >
            预览
          </Button>
          <Button
            loading={runningBindingId === record.id}
            size="small"
            onClick={() => handleRun(record, true)}
          >
            试运行
          </Button>
          <Popconfirm
            disabled={!record.is_active}
            title="执行销售执行同步？"
            description="将按飞书 record_id 幂等写入销售执行明细；手工记录不会被覆盖。"
            okText="执行"
            cancelText="取消"
            onConfirm={() => handleRun(record, false)}
          >
            <Button
              disabled={!record.is_active}
              icon={<PlayCircleOutlined />}
              loading={runningBindingId === record.id}
              size="small"
              type="primary"
            >
              执行
            </Button>
          </Popconfirm>
          <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除该同步绑定？"
            description="不会删除飞书表中的任何数据。"
            okText="删除"
            cancelText="取消"
            onConfirm={() => handleDelete(record)}
          >
            <Button danger icon={<DeleteOutlined />} size="small" />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card
      className="mt-6"
      title="同步绑定"
      extra={
        <Button
          icon={<PlusOutlined />}
          type="primary"
          disabled={configs.length === 0}
          onClick={openCreate}
        >
          新增绑定
        </Button>
      }
    >
      <Alert
        showIcon
        type="info"
        message="绑定仅定义目标表和字段映射"
        description="先使用“预览”和“试运行”核对字段；已启用的计划、批次、发酵、种子及工序绑定均可执行同步。执行按飞书 record_id 幂等写入，不会覆盖手工记录或已完工工序。"
        className="mb-4"
      />
      {configs.length === 0 && (
        <Alert
          showIcon
          type="warning"
          message="请先保存至少一个生产飞书配置，再建立同步绑定。"
          className="mb-4"
        />
      )}
      <Table rowKey="id" columns={columns} dataSource={bindings} pagination={false} />
      <Modal
        destroyOnHidden
        open={open}
        title={editing ? '编辑同步绑定' : '新增同步绑定'}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="config_id" label="飞书配置" rules={[{ required: true, message: '请选择飞书配置' }]}>
            <Select
              options={configs
                .filter((config): config is ProductionFeishuConfig & { id: string } => Boolean(config.id))
                .map((config) => ({ value: config.id, label: config.config_name }))}
            />
          </Form.Item>
          <Form.Item name="binding_name" label="绑定名称" rules={[{ required: true, message: '请输入绑定名称' }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="sync_target" label="同步业务目标" rules={[{ required: true, message: '请输入业务目标' }]}>
            <Select
              options={[
                { value: 'sales_plan_detail', label: '销售执行明细' },
                { value: 'production_plan', label: '生产执行计划' },
                { value: 'batch', label: '生产批次' },
                { value: 'fermentation_record', label: '发酵记录' },
                { value: 'seed_culture', label: '种子培养' },
                { value: 'broth_receive', label: '203 · 发酵液接收' },
                { value: 'broth_pretreat', label: '203 · 预处理' },
                { value: 'ceramic_feed', label: '203 · 陶瓷膜进料' },
                { value: 'ceramic_ops', label: '203 · 陶瓷膜运行' },
                { value: 'ceramic_clean', label: '203 · 陶瓷膜清洗' },
                { value: 'ceramic_sep', label: '203 · 陶瓷膜分离' },
                { value: 'ceramic_equip', label: '203 · 陶瓷膜设备' },
                { value: 'decolor1', label: '203 · 一次脱色' },
                { value: 'filter1', label: '203 · 一次板框过滤' },
                { value: 'conc1', label: '203 · 一次浓缩' },
                { value: 'centrifuge1', label: '203 · 一次离心' },
                { value: 'recrystallize', label: '203 · 二次重结晶脱色' },
                { value: 'filter2', label: '203 · 二次板框过滤' },
                { value: 'conc2', label: '203 · 二次浓缩' },
                { value: 'centrifuge2', label: '203 · 二次离心' },
                { value: 'dry', label: '203 · 烘干' },
                { value: 'pack', label: '203 · 包装' },
              ]}
            />
          </Form.Item>
          <Form.Item name="table_id" label="飞书 Table ID" rules={[{ required: true, message: '请输入飞书 Table ID' }]}>
            <Input placeholder="tblxxxx" />
          </Form.Item>
          <Form.Item name="product_name" label="适用产品">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="workshop_code" label="适用车间 / 生产线">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="field_mapping_text" label="字段映射（JSON）">
            <Input.TextArea
              autoSize={{ minRows: 4, maxRows: 10 }}
              placeholder={'{"product_name":"产品名称"}'}
            />
          </Form.Item>
          <Form.Item name="is_active" label="允许后续同步任务使用" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
