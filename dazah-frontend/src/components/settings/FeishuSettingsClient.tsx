'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import {
  ApiOutlined,
  CloudSyncOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  getLivzonFeishuEventWsStatus,
  getLivzonFeishuConfig,
  restartLivzonFeishuEventWs,
  saveLivzonFeishuConfig,
  syncLivzonFeishuContacts,
  testLivzonFeishuConfig,
} from '@/actions/settings'
import type {
  FeishuConfig,
  FeishuConfigUpsert,
  FeishuDiagnosticResult,
  LivzonFeishuEventWsStatus,
} from '@/actions/settings'

const { Text, Title } = Typography
type DiagnosticStep = NonNullable<FeishuDiagnosticResult['steps']>[number]

const STATUS_COLOR: Record<string, string> = {
  ok: 'success',
  warning: 'warning',
  error: 'error',
}

const DEFAULT_VALUES: FeishuConfigUpsert = {
  config_name: 'Livzon 助手飞书设置',
  app_id: '',
  app_secret: '',
  card_callback_verification_token: '',
  card_callback_encrypt_key: '',
  sync_root_department_id: '0',
  sync_member_department_id: '0',
  is_active: true,
}

function normalizePayload(values: FeishuConfigUpsert): FeishuConfigUpsert {
  return {
    config_name: values.config_name?.trim() || 'Livzon 助手飞书设置',
    app_id: values.app_id?.trim() || '',
    app_secret: values.app_secret?.trim() || undefined,
    card_callback_verification_token: values.card_callback_verification_token?.trim() || undefined,
    card_callback_encrypt_key: values.card_callback_encrypt_key?.trim() || undefined,
    sync_root_department_id: values.sync_root_department_id?.trim() || '0',
    sync_member_department_id: values.sync_member_department_id?.trim() || '0',
    is_active: values.is_active ?? true,
  }
}

export default function FeishuSettingsClient() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FeishuConfigUpsert>()
  const [config, setConfig] = useState<FeishuConfig | null>(null)
  const [diagnostic, setDiagnostic] = useState<FeishuDiagnosticResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [eventWsStatus, setEventWsStatus] = useState<LivzonFeishuEventWsStatus | null>(null)
  const [eventWsLoading, setEventWsLoading] = useState(true)
  const [eventWsRestarting, setEventWsRestarting] = useState(false)

  const configuredSecret = !!config?.app_secret_configured

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getLivzonFeishuConfig()
      setConfig(data)
      form.setFieldsValue({
        config_name: data.config_name || DEFAULT_VALUES.config_name,
        app_id: data.app_id || '',
        app_secret: '',
        card_callback_verification_token: '',
        card_callback_encrypt_key: '',
        sync_root_department_id: data.sync_root_department_id || '0',
        sync_member_department_id: data.sync_member_department_id || '0',
        is_active: data.is_active ?? true,
      })
      if (data.last_diagnostic_result) {
        try {
          setDiagnostic(JSON.parse(data.last_diagnostic_result) as FeishuDiagnosticResult)
        } catch {
          setDiagnostic(null)
        }
      }
    } catch (error) {
      console.error('Failed to load Livzon Feishu config:', error)
      message.error('加载 Livzon 助手飞书设置失败')
    } finally {
      setLoading(false)
    }
  }, [form, message])

  const loadEventWsStatus = useCallback(async (notifyOnError = false) => {
    setEventWsLoading(true)
    try {
      setEventWsStatus(await getLivzonFeishuEventWsStatus())
    } catch (error) {
      console.error('Failed to load Livzon Feishu event WS status:', error)
      if (notifyOnError) {
        message.error('加载飞书双向对话连接状态失败')
      }
    } finally {
      setEventWsLoading(false)
    }
  }, [message])

  useEffect(() => {
    loadConfig()
    loadEventWsStatus()
  }, [loadConfig, loadEventWsStatus])

  const lastSyncText = useMemo(() => {
    if (!config?.last_synced_at) return '尚未同步'
    return `${config.last_synced_at}${config.last_sync_message ? ` · ${config.last_sync_message}` : ''}`
  }, [config])

  const handleSave = async () => {
    try {
      const values = normalizePayload(await form.validateFields())
      setSaving(true)
      const data = await saveLivzonFeishuConfig(values)
      setConfig(data)
      form.setFieldValue('app_secret', '')
      form.setFieldValue('card_callback_verification_token', '')
      form.setFieldValue('card_callback_encrypt_key', '')
      message.success('Livzon 助手飞书设置已保存')
    } catch (error) {
      console.error('Save Livzon Feishu config failed:', error)
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    try {
      const values = normalizePayload(await form.validateFields())
      setTesting(true)
      const result = await testLivzonFeishuConfig(values)
      setDiagnostic(result)
      if (result.status === 'ok') {
        message.success('Livzon 助手飞书权限诊断通过')
      } else if (result.status === 'warning') {
        message.warning('诊断完成，部分通讯录字段不可见')
      } else {
        message.error('诊断失败，请检查应用凭证和权限')
      }
      loadConfig()
    } catch (error) {
      console.error('Test Livzon Feishu config failed:', error)
      message.error(error instanceof Error ? error.message : '诊断失败')
    } finally {
      setTesting(false)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await syncLivzonFeishuContacts()
      const syncMessage = result.message || 'Livzon 助手通讯录同步完成'
      if (result.status === 'warning') {
        message.warning(syncMessage)
      } else {
        message.success(syncMessage)
      }
      loadConfig()
    } catch (error) {
      console.error('Sync Livzon Feishu contacts failed:', error)
      message.error(error instanceof Error ? error.message : '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  const handleRestartEventWs = async () => {
    setEventWsRestarting(true)
    try {
      const data = await restartLivzonFeishuEventWs()
      setEventWsStatus(data)
      message.success('飞书双向对话连接已请求重启')
    } catch (error) {
      console.error('Restart Livzon Feishu event WS failed:', error)
      message.error(error instanceof Error ? error.message : '重启飞书双向对话连接失败')
    } finally {
      setEventWsRestarting(false)
    }
  }

  const formatEventWsTime = (timestamp?: number | null) => {
    if (!timestamp) return '尚未连接'
    return new Date(timestamp * 1000).toLocaleString('zh-CN', { hour12: false })
  }

  return (
    <div className="max-w-[1120px]">
      <div className="mb-5">
        <Title level={3} style={{ margin: 0 }}>
          <SafetyCertificateOutlined style={{ marginRight: 10 }} />
          Livzon 助手飞书设置
        </Title>
        <Text className="mt-2 block text-[13px] text-[var(--color-steel)]">
          此配置仅用于 Livzon 助手通讯录同步和权限诊断，不影响仓储、安全、设备等模块的飞书应用配置。
        </Text>
      </div>

      <Alert
        className="mb-4"
        type="info"
        showIcon
        title="仅针对 Livzon 助手"
        description="这里保存的 App ID、App Secret 和卡片回调配置只会用于 Livzon 助手通讯录、消息发送和权限诊断，不影响其他模块。"
      />

      <Card title="Livzon 助手专用飞书应用">
        <Form
          form={form}
          layout="vertical"
          initialValues={DEFAULT_VALUES}
          disabled={loading}
        >
          <Form.Item
            name="config_name"
            label="配置名称"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="Livzon 助手飞书设置" />
          </Form.Item>

          <Form.Item
            name="app_id"
            label="App ID"
            rules={[{ required: true, message: '请输入飞书自建应用 App ID' }]}
          >
            <Input placeholder="cli_xxx" />
          </Form.Item>

          <Form.Item
            name="app_secret"
            label="App Secret"
            extra={
              configuredSecret
                ? `已配置：${config?.app_secret_masked || '******'}；留空则不修改。`
                : '首次保存必须填写。'
            }
            rules={[{ required: !configuredSecret, message: '请输入 App Secret' }]}
          >
            <Input.Password placeholder={configuredSecret ? '留空则不修改' : '请输入 App Secret'} />
          </Form.Item>

          <Space size="large" wrap align="start">
            <Form.Item
              name="card_callback_verification_token"
              label="卡片回调 Verification Token"
              extra={
                config?.card_callback_verification_token_configured
                  ? `已配置：${config.card_callback_verification_token_masked || '******'}；留空则不修改。`
                  : 'HTTP 回调模式用于校验请求；长连接模式可留空。'
              }
            >
              <Input.Password style={{ width: 360 }} placeholder="留空则不修改" />
            </Form.Item>

            <Form.Item
              name="card_callback_encrypt_key"
              label="卡片回调 Encrypt Key"
              extra={
                config?.card_callback_encrypt_key_configured
                  ? `已配置：${config.card_callback_encrypt_key_masked || '******'}；留空则不修改。`
                  : '可选。配置后后端会进行回调签名校验，密钥加密入库。'
              }
            >
              <Input.Password style={{ width: 360 }} placeholder="留空则不修改" />
            </Form.Item>
          </Space>

          <Alert
            className="mb-4"
            type="warning"
            showIcon
            title="交互卡片回调方式"
            description={`生产环境可配置 HTTP 回调地址：${config?.card_callback_url || '/api/v1/identity/feishu/card-callback'}；双向私聊与卡片长连接可在后端开启 LIVZON_FEISHU_EVENT_WS_ENABLED=true。旧的 LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=true 仍兼容。`}
          />

          <Space size="large" wrap>
            <Form.Item
              name="sync_root_department_id"
              label="组织架构同步根部门 ID"
              tooltip="默认为 0，表示从飞书根部门开始读取子部门。"
            >
              <Input style={{ width: 260 }} placeholder="0 或 open_department_id" />
            </Form.Item>

            <Form.Item
              name="sync_member_department_id"
              label="成员同步部门 ID"
              tooltip="默认为 0，建议填写 Livzon 助手可访问的成员根部门。"
            >
              <Input style={{ width: 260 }} placeholder="0 或 open_department_id" />
            </Form.Item>

            <Form.Item name="is_active" label="启用状态" valuePropName="checked">
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
          </Space>

          <Space wrap>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
              保存设置
            </Button>
            <Button icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
              诊断权限
            </Button>
            <Button icon={<CloudSyncOutlined />} loading={syncing} onClick={handleSync}>
              同步通讯录
            </Button>
          </Space>
        </Form>
      </Card>

      <Card
        className="mt-4"
        title="飞书双向对话事件连接"
        extra={
          <Space>
            <Button loading={eventWsLoading} onClick={() => loadEventWsStatus(true)}>
              刷新状态
            </Button>
            <Button
              icon={<ReloadOutlined />}
              loading={eventWsRestarting}
              onClick={handleRestartEventWs}
            >
              重启连接
            </Button>
          </Space>
        }
      >
        <Alert
          className="mb-4"
          type="info"
          showIcon
          title="启用 Livzon 飞书私聊"
          description="请在同一飞书自建应用中开启机器人能力；在“事件配置”订阅 im.message.receive_v1 并使用长连接，在“回调配置”订阅 card.action.trigger 并使用长连接；授予 im:message.p2p_msg（或只读版本）和发送消息权限，完成后发布应用。更换 App ID 后请重新同步通讯录。"
        />
        <Descriptions size="small" column={2}>
          <Descriptions.Item label="事件连接开关">
            {eventWsStatus?.event_ws_enabled ? <Tag color="success">已启用</Tag> : <Tag>未启用</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="兼容卡片开关">
            {eventWsStatus?.legacy_card_callback_ws_enabled ? <Tag color="processing">已启用</Tag> : <Tag>未启用</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="运行状态">
            {eventWsStatus?.running ? <Tag color="success">已连接</Tag> : <Tag color="warning">未运行</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="最近连接">
            {formatEventWsTime(eventWsStatus?.last_connected_at)}
          </Descriptions.Item>
          <Descriptions.Item label="事件类型" span={2}>
            {(eventWsStatus?.event_types || []).join('、') || '尚未读取'}
          </Descriptions.Item>
          <Descriptions.Item label="最近错误" span={2}>
            {eventWsStatus?.last_error || '无'}
          </Descriptions.Item>
          <Descriptions.Item label="事件计数" span={2}>
            {eventWsStatus
              ? Object.entries(eventWsStatus.frames || {})
                  .map(([name, count]) => `${name}: ${count}`)
                  .join(' · ')
              : '尚未读取'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="mt-4" title="同步与权限状态">
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="配置范围">仅用于 Livzon 助手</Descriptions.Item>
          <Descriptions.Item label="最近同步">{lastSyncText}</Descriptions.Item>
          <Descriptions.Item label="最近诊断">
            {config?.last_diagnostic_status ? (
              <Space>
                <Tag color={STATUS_COLOR[config.last_diagnostic_status] || 'default'}>
                  {config.last_diagnostic_status}
                </Tag>
                <span>{config.last_diagnostic_message}</span>
              </Space>
            ) : (
              '尚未诊断'
            )}
          </Descriptions.Item>
        </Descriptions>

        {diagnostic && (
          <div className="mt-4">
            <Alert
              className="mb-3"
              type={diagnostic.status === 'ok' ? 'success' : diagnostic.status}
              showIcon
              title={diagnostic.message}
              description={`部门 ${diagnostic.department_count || 0} 个，抽样用户 ${diagnostic.sample_user_count || 0} 名。`}
            />
            <ul className="divide-y divide-[var(--color-border)]">
              {((diagnostic.steps || []) as DiagnosticStep[]).map((item) => (
                <li key={`${item.status}-${item.name}`} className="py-3 first:pt-0 last:pb-0">
                  <Space>
                    <Tag color={STATUS_COLOR[item.status] || 'default'}>{item.status}</Tag>
                    <span>{item.name}</span>
                  </Space>
                  <div className="mt-1">
                    <div>{item.message}</div>
                    {item.suggestion && (
                      <Text type="secondary">{item.suggestion}</Text>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  )
}
