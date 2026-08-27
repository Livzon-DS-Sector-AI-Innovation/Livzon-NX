'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Switch,
  InputNumber,
  Typography,
  Space,
  Tag,
  Popconfirm,
  Tooltip,
  App,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ArrowLeftOutlined,
  ApiOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import {
  getLLMConfigs,
  createLLMConfig,
  updateLLMConfig,
  deleteLLMConfig,
  testLLMConnection,
  testLLMConfig,
  probeLLMConfig,
} from '@/actions/settings'
import type {
  LLMConfig,
  LLMConfigProbeRequest,
  LLMConfigUpdate,
} from '@/actions/settings'
import {
  buildLLMConfigPayload,
  getNewLLMConfigFormValues,
  type LLMConfigFormValues,
} from './llmConfigForm'

const { Title, Text } = Typography
const { TextArea } = Input

interface LLMConfigClientProps {
  embedded?: boolean
}

export default function LLMConfigClient({ embedded = false }: LLMConfigClientProps) {
  const { message } = App.useApp()
  const router = useRouter()
  const [configs, setConfigs] = useState<LLMConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<LLMConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [probing, setProbing] = useState<LLMConfigProbeRequest['probe_type'] | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [activatingId, setActivatingId] = useState<string | null>(null)
  const [form] = Form.useForm<LLMConfigFormValues>()
  const useTemperature = Form.useWatch('use_temperature', form) ?? false

  const loadConfigs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getLLMConfigs()
      setConfigs(res.data || [])
    } catch (error) {
      console.error('Failed to load configs:', error)
      message.error('加载配置失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadConfigs)
  }, [loadConfigs])

  const handleCreate = () => {
    setEditingConfig(null)
    form.resetFields()
    form.setFieldsValue(getNewLLMConfigFormValues())
    setModalOpen(true)
  }

  const handleEdit = (record: LLMConfig) => {
    setEditingConfig(record)
    form.setFieldsValue({
      config_name: record.config_name,
      api_base_url: record.api_base_url,
      api_key: '',
      model_name: record.model_name,
      temperature: record.temperature > 0 ? record.temperature : 0.1,
      use_temperature: record.temperature > 0,
      timeout_seconds: record.timeout_seconds,
      is_active: record.is_active,
      notes: record.notes,
    })
    setModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteLLMConfig(id)
      message.success('删除成功')
      loadConfigs()
    } catch {
      message.error('删除失败')
    }
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const payload = buildLLMConfigPayload(values)
      setSaving(true)
      if (editingConfig) {
        const updatePayload: LLMConfigUpdate = { ...payload }
        if (!updatePayload.api_key) delete updatePayload.api_key
        await updateLLMConfig(editingConfig.id, updatePayload)
        message.success('更新成功')
      } else {
        await createLLMConfig(payload)
        message.success('创建成功')
      }
      setModalOpen(false)
      loadConfigs()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(error instanceof Error ? error.message : '保存配置失败')
    } finally {
      setSaving(false)
    }
  }

  const handleActivate = async (id: string) => {
    setActivatingId(id)
    try {
      await updateLLMConfig(id, { is_active: true })
      message.success('能力检测通过并已激活，所有 AI 调用将使用此配置')
      loadConfigs()
    } catch {
      message.error('激活失败')
    } finally {
      setActivatingId(null)
    }
  }

  const handleProbe = async (probeType: LLMConfigProbeRequest['probe_type']) => {
    try {
      const fields: Array<keyof LLMConfigFormValues> = [
        'api_base_url',
        'api_key',
        'timeout_seconds',
      ]
      if (probeType === 'model') fields.push('model_name')
      const values = await form.validateFields(fields)
      if (!values.api_key) {
        message.warning('请先输入 API 密钥后再测试连通性')
        return
      }

      setProbing(probeType)
      const res = await probeLLMConfig({
        probe_type: probeType,
        api_base_url: values.api_base_url,
        api_key: values.api_key,
        model_name: probeType === 'model' ? values.model_name : null,
        timeout_seconds: values.timeout_seconds,
      })
      if (!res.ok) {
        message.error(res.error)
        return
      }
      message.success(res.data.detail)
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(error instanceof Error ? error.message : '连通性测试失败')
    } finally {
      setProbing(null)
    }
  }

  const handleTestConfig = async (id: string) => {
    setTestingId(id)
    try {
      const res = await testLLMConfig(id)
      message.success(res.data.detail)
      loadConfigs()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '模型能力检测失败')
    } finally {
      setTestingId(null)
    }
  }

  const handleTestConnection = async () => {
    try {
      const res = await testLLMConnection()
      message.success(res.data.detail)
      loadConfigs()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '当前模型能力检测失败')
    }
  }

  const columns = [
    {
      title: '配置名称',
      dataIndex: 'config_name',
      key: 'config_name',
      width: 180,
      render: (name: string, record: LLMConfig) => (
        <Space>
          {name}
          {record.is_active && <Tag color="success">当前使用</Tag>}
        </Space>
      ),
    },
    {
      title: '自动检测能力',
      dataIndex: 'capabilities',
      key: 'capabilities',
      width: 210,
      render: (capabilities: string[]) => (
        <Space size={4} wrap>
          <Tag color="blue">文本</Tag>
          <Tag color="cyan">文档</Tag>
          {capabilities.includes('image') && <Tag color="purple">图片 / 视觉</Tag>}
        </Space>
      ),
    },
    {
      title: 'API 地址',
      dataIndex: 'api_base_url',
      key: 'api_base_url',
      ellipsis: true,
      width: 260,
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
      width: 200, fixed: "right" as const,
      render: (model: string) => <Tag color="geekblue">{model}</Tag>,
    },
    {
      title: 'Temperature',
      dataIndex: 'temperature',
      key: 'temperature',
      width: 110,
      render: (temperature: number) =>
        temperature > 0 ? temperature : <Text type="secondary">模型默认</Text>,
    },
    {
      title: '超时(秒)',
      dataIndex: 'timeout_seconds',
      key: 'timeout_seconds',
      width: 100,
    },
    {
      title: '操作',
      key: 'actions',
      width: 200, fixed: "right" as const,
      render: (_: unknown, record: LLMConfig) => (
        <Space>
          {!record.is_active && (
            <Tooltip title="激活此配置">
              <Button
                type="link"
                size="small"
                icon={<CheckCircleOutlined />}
                loading={activatingId === record.id}
                onClick={() => handleActivate(record.id)}
              />
            </Tooltip>
          )}
          <Tooltip title="重新检测模型能力">
            <Button
              type="link"
              size="small"
              icon={<ApiOutlined />}
              loading={testingId === record.id}
              onClick={() => handleTestConfig(record.id)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此配置？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ maxWidth: 1300, margin: '0 auto', padding: embedded ? 0 : '24px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 24,
        }}
      >
        <div>
        {!embedded && (
          <Button icon={<ArrowLeftOutlined />} onClick={() => router.back()} style={{ marginRight: 16 }}>
            返回
          </Button>
        )}
          <Title level={3} style={{ margin: 0 }}>
            <SettingOutlined style={{ marginRight: 12 }} />
            LLM 模型配置
          </Title>
          <Text style={{ fontSize: 14, color: '#666', marginTop: 8, display: 'block' }}>
            配置 AI 大模型 API 连接参数。系统会发送真实探测请求，自动识别文本、文档和图片能力；同一时间仅一个配置生效。
          </Text>
        </div>
        <Space>
          <Button icon={<ApiOutlined />} onClick={handleTestConnection}>
            测试连接
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreate}
          >
            新建配置
          </Button>
        </Space>
      </div>

      <Card>
        <Table scroll={{ x: 1000 }}
          columns={columns}
          dataSource={configs}
          rowKey="id"
          loading={loading}
          size="middle"
          pagination={false}
        />
      </Card>

      <Modal
        title={editingConfig ? '编辑 LLM 配置' : '新建 LLM 配置'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        width={640}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="config_name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="例如：生产环境 GPT-4o" />
          </Form.Item>

          <Form.Item
            label="API 基础 URL"
            htmlFor="api_base_url"
            required
          >
            <Space.Compact block>
              <Form.Item
                name="api_base_url"
                noStyle
                rules={[
                  { required: true, message: '请输入 API 地址' },
                  { type: 'url', message: '请输入有效的 API URL' },
                ]}
              >
                <Input id="api_base_url" placeholder="https://api.openai.com/v1" />
              </Form.Item>
              <Button
                icon={<ApiOutlined />}
                loading={probing === 'url'}
                disabled={probing !== null && probing !== 'url'}
                onClick={() => handleProbe('url')}
              >
                测试 URL
              </Button>
            </Space.Compact>
          </Form.Item>

          <Form.Item
            name="api_key"
            label="API 密钥"
            rules={[{ required: !editingConfig, message: '请输入 API 密钥' }]}
            extra={editingConfig ? '留空则不修改' : undefined}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>

          <Form.Item
            label="模型名称"
            htmlFor="model_name"
            required
          >
            <Space.Compact block>
              <Form.Item
                name="model_name"
                noStyle
                rules={[{ required: true, message: '请输入模型名称' }]}
              >
                <Input id="model_name" placeholder="gpt-4o" />
              </Form.Item>
              <Button
                icon={<ApiOutlined />}
                loading={probing === 'model'}
                disabled={probing !== null && probing !== 'model'}
                onClick={() => handleProbe('model')}
              >
                测试模型
              </Button>
            </Space.Compact>
          </Form.Item>

          <Space size="large">
            <Form.Item
              label="温度设置"
              extra={useTemperature
                ? '向模型请求传递自定义 temperature'
                : '不传递 temperature，使用模型默认值'}
            >
              <Space>
                <Form.Item name="use_temperature" valuePropName="checked" noStyle>
                  <Switch checkedChildren="自定义" unCheckedChildren="模型默认" />
                </Form.Item>
                {useTemperature && (
                  <Form.Item
                    name="temperature"
                    noStyle
                    rules={[{ required: true, message: '请输入温度' }]}
                  >
                    <InputNumber
                      min={0.1}
                      max={2}
                      step={0.1}
                      style={{ width: 120 }}
                      aria-label="Temperature"
                    />
                  </Form.Item>
                )}
              </Space>
            </Form.Item>
            <Form.Item name="timeout_seconds" label="超时(秒)">
              <InputNumber min={10} max={600} style={{ width: 120 }} />
            </Form.Item>
          </Space>

          <Form.Item name="is_active" label="激活状态" valuePropName="checked">
            <Switch checkedChildren="激活" unCheckedChildren="未激活" />
          </Form.Item>

          <Form.Item name="notes" label="备注">
            <TextArea rows={2} placeholder="配置说明" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
