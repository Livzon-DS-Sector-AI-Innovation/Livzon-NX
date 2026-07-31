'use client'

import { useEffect, useState } from 'react'
import { ApiOutlined, SafetyCertificateOutlined, SaveOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, List, Space, Switch, Tag, Typography } from 'antd'
import {
  createExternalIdentityBinding,
  disableExternalIdentityBinding,
  getAgentToolCatalog,
  getExternalIdentityBindings,
  getLivzonFeishuGatewayStatus,
  getLivzonFeishuConfig,
  setAgentToolEnabled,
} from '@/actions/settings'
import type {
  FeishuConfig,
  FeishuConfigUpsert,
  FeishuGatewayStatus,
  ExternalIdentityBinding,
  ExternalIdentityBindingCreate,
  AgentToolCatalogEntry,
} from '@/actions/settings'

const { Text, Title } = Typography

type CredentialsFormValues = Pick<
  FeishuConfigUpsert,
  'app_id' | 'app_secret' | 'tenant_id' | 'gateway_enabled'
>

const DEFAULT_VALUES: CredentialsFormValues = {
  app_id: '',
  app_secret: '',
  tenant_id: 'default',
  gateway_enabled: true,
}

export async function requestFeishuConfig<T>(
  path: string,
  payload: FeishuConfigUpsert,
  method: 'POST' | 'PUT',
): Promise<T> {
  const response = await fetch(`/api/v1/identity/feishu-config${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  })
  const body = (await response.json().catch(() => null)) as
    | { data?: T; detail?: string; message?: string }
    | null
  if (!response.ok) {
    throw new Error(
      body?.detail || body?.message || `API error: ${response.status}`,
    )
  }
  if (!body || body.data === undefined) {
    throw new Error('飞书配置接口返回格式无效')
  }
  return body.data
}

export function buildPayload(
  values: CredentialsFormValues,
  config: FeishuConfig | null,
): FeishuConfigUpsert {
  return {
    config_name: config?.config_name || 'Livzon 助手飞书设置',
    app_id: values.app_id.trim(),
    app_secret: values.app_secret?.trim() || undefined,
    tenant_id: values.tenant_id.trim(),
    gateway_enabled: values.gateway_enabled,
    sync_root_department_id: config?.sync_root_department_id,
    sync_member_department_id: config?.sync_member_department_id,
    is_active: config?.is_active ?? true,
  }
}

export default function FeishuSettingsClient() {
  const { message } = App.useApp()
  const [form] = Form.useForm<CredentialsFormValues>()
  const [bindingForm] = Form.useForm<ExternalIdentityBindingCreate>()
  const [config, setConfig] = useState<FeishuConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [gatewayStatus, setGatewayStatus] = useState<FeishuGatewayStatus | null>(null)
  const [bindings, setBindings] = useState<ExternalIdentityBinding[]>([])
  const [tools, setTools] = useState<AgentToolCatalogEntry[]>([])

  const configuredSecret = !!config?.app_secret_configured

  useEffect(() => {
    let cancelled = false

    Promise.all([
      getLivzonFeishuConfig(),
      getLivzonFeishuGatewayStatus().catch(() => null),
      getExternalIdentityBindings(),
      getAgentToolCatalog(),
    ])
      .then(([data, status, identityBindings, catalog]) => {
        if (cancelled) return
        setConfig(data)
        setGatewayStatus(status)
        setBindings(identityBindings)
        setTools(catalog)
        form.setFieldsValue({
          app_id: data.app_id || '',
          app_secret: '',
          tenant_id: data.tenant_id || 'default',
          gateway_enabled: data.gateway_enabled,
        })
        bindingForm.setFieldsValue({
          tenant_id: data.tenant_id || 'default',
          platform: 'feishu',
          app_fingerprint: data.app_id || '',
        })
      })
      .catch((error) => {
        if (cancelled) return
        console.error('Failed to load Livzon Feishu config:', error)
        message.error('加载 Livzon 助手设置失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [bindingForm, form, message])

  const handleSave = async () => {
    try {
      const payload = buildPayload(await form.validateFields(), config)
      setSaving(true)
      const data = await requestFeishuConfig<FeishuConfig>('', payload, 'PUT')
      setConfig(data)
      setGatewayStatus(await getLivzonFeishuGatewayStatus().catch(() => null))
      form.setFieldValue('app_secret', '')
      message.success('Livzon 助手凭证已保存')
    } catch (error) {
      console.error('Save Livzon Feishu credentials failed:', error)
      message.error(error instanceof Error ? error.message : '保存凭证失败')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    try {
      const payload = buildPayload(await form.validateFields(), config)
      setTesting(true)
      const result = await requestFeishuConfig<{
        message?: string
        steps?: Array<{ name: string; status: string; message?: string }>
      }>('/test', payload, 'POST')
      const credentialStep = result.steps?.find((step) => step.name === 'tenant_access_token')
      if (credentialStep?.status === 'ok') {
        message.success('Livzon 助手凭证连通性测试通过')
      } else {
        message.error(credentialStep?.message || result.message || '连通性测试失败')
      }
    } catch (error) {
      console.error('Test Livzon Feishu credentials failed:', error)
      message.error(error instanceof Error ? error.message : '连通性测试失败')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="max-w-[760px]">
      <div className="mb-5">
        <Title level={3} style={{ margin: 0 }}>
          <SafetyCertificateOutlined style={{ marginRight: 10 }} />
          Livzon 助手设置
        </Title>
        <Text className="mt-2 block text-[13px] text-[var(--color-steel)]">
          配置 Livzon 助手使用的飞书应用凭证。
        </Text>
      </div>

      <Card>
        <Space className="mb-4" wrap>
          <Text strong>Gateway</Text>
          <Tag color={gatewayStatus?.gateway === 'connected' ? 'green' : 'orange'}>
            {gatewayStatus?.gateway || 'unknown'}
          </Tag>
          <Text type="secondary">
            配置版本 {gatewayStatus?.config_version ?? config?.config_version ?? 0}
            {' · '}重连 {gatewayStatus?.gateway_reconnects ?? 0}
          </Text>
        </Space>
        <Form
          form={form}
          layout="vertical"
          initialValues={DEFAULT_VALUES}
          disabled={loading}
        >
          <Form.Item
            name="app_id"
            label="App ID"
            rules={[{ required: true, message: '请输入 App ID' }]}
          >
            <Input placeholder="cli_xxx" />
          </Form.Item>

          <Form.Item
            name="tenant_id"
            label="租户标识"
            rules={[{ required: true, message: '请输入租户标识' }]}
          >
            <Input placeholder="default" />
          </Form.Item>

          <Form.Item
            name="gateway_enabled"
            label="启用 Hermes Feishu Gateway"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="app_secret"
            label="App Secret"
            extra={configuredSecret ? '已保存凭证；留空则不修改。' : '首次保存必须填写。'}
            rules={[{ required: !configuredSecret, message: '请输入 App Secret' }]}
          >
            <Input.Password
              autoComplete="new-password"
              placeholder={configuredSecret ? '留空则不修改' : '请输入 App Secret'}
            />
          </Form.Item>

          <Space wrap>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
              保存凭证
            </Button>
            <Button icon={<ApiOutlined />} loading={testing} onClick={handleTest}>
              测试连通性
            </Button>
          </Space>
        </Form>
      </Card>

      <Card className="mt-4" title="可信飞书身份绑定">
        <Form
          form={bindingForm}
          layout="vertical"
          initialValues={{
            tenant_id: config?.tenant_id || 'default',
            platform: 'feishu',
            app_fingerprint: config?.app_id || '',
          }}
          onFinish={async (values) => {
            try {
              await createExternalIdentityBinding(values)
              setBindings(await getExternalIdentityBindings())
              bindingForm.resetFields([
                'external_user_id',
                'external_open_id',
                'external_union_id',
                'local_user_id',
              ])
              message.success('身份绑定已创建')
            } catch (error) {
              message.error(error instanceof Error ? error.message : '创建绑定失败')
            }
          }}
        >
          <Space wrap align="start">
            <Form.Item name="tenant_id" label="租户" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="app_fingerprint" label="App ID" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="external_open_id" label="飞书 Open ID">
              <Input placeholder="ou_xxx" />
            </Form.Item>
            <Form.Item name="external_union_id" label="飞书 Union ID">
              <Input placeholder="on_xxx" />
            </Form.Item>
            <Form.Item name="local_user_id" label="本地用户 UUID" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item label=" ">
              <Button htmlType="submit" type="primary">创建绑定</Button>
            </Form.Item>
          </Space>
        </Form>
        <List
          dataSource={bindings}
          locale={{ emptyText: '暂无身份绑定' }}
          renderItem={(item) => (
            <List.Item
              actions={item.status === 'active' ? [
                <Button
                  key="disable"
                  danger
                  type="link"
                  onClick={async () => {
                    await disableExternalIdentityBinding(item.id)
                    setBindings(await getExternalIdentityBindings())
                  }}
                >
                  停用
                </Button>,
              ] : undefined}
            >
              <List.Item.Meta
                title={`${item.external_open_id || item.external_union_id || item.external_user_id} → ${item.local_user_id}`}
                description={`${item.tenant_id} · ${item.app_fingerprint}`}
              />
              <Tag color={item.status === 'active' ? 'green' : 'default'}>{item.status}</Tag>
            </List.Item>
          )}
        />
      </Card>

      <Card className="mt-4" title="企业工具目录">
        <List
          dataSource={tools}
          locale={{ emptyText: '暂无已发现工具' }}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Switch
                  key="enabled"
                  checked={item.status === 'active'}
                  onChange={async (enabled) => {
                    await setAgentToolEnabled(item.operation, enabled)
                    setTools(await getAgentToolCatalog())
                  }}
                />,
              ]}
            >
              <List.Item.Meta
                title={item.operation}
                description={`${item.module || 'platform'} · ${item.summary}`}
              />
              <Tag color={item.risk_level === 'high' ? 'red' : item.risk_level === 'medium' ? 'orange' : 'blue'}>
                {item.risk_level}
              </Tag>
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
