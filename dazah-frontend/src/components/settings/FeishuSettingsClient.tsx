'use client'

import { useEffect, useState } from 'react'
import { ApiOutlined, SafetyCertificateOutlined, SaveOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Space, Typography } from 'antd'
import {
  getLivzonFeishuConfig,
  saveLivzonFeishuConfig,
  testLivzonFeishuConfig,
} from '@/actions/settings'
import type {
  FeishuConfig,
  FeishuConfigUpsert,
} from '@/actions/settings'

const { Text, Title } = Typography

type CredentialsFormValues = Pick<FeishuConfigUpsert, 'app_id' | 'app_secret'>

const DEFAULT_VALUES: CredentialsFormValues = {
  app_id: '',
  app_secret: '',
}

function buildPayload(
  values: CredentialsFormValues,
  config: FeishuConfig | null,
): FeishuConfigUpsert {
  return {
    config_name: config?.config_name || 'Livzon 助手飞书设置',
    app_id: values.app_id.trim(),
    app_secret: values.app_secret?.trim() || undefined,
    sync_root_department_id: config?.sync_root_department_id,
    sync_member_department_id: config?.sync_member_department_id,
    is_active: config?.is_active ?? true,
  }
}

export default function FeishuSettingsClient() {
  const { message } = App.useApp()
  const [form] = Form.useForm<CredentialsFormValues>()
  const [config, setConfig] = useState<FeishuConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const configuredSecret = !!config?.app_secret_configured

  useEffect(() => {
    let cancelled = false

    getLivzonFeishuConfig()
      .then((data) => {
        if (cancelled) return
        setConfig(data)
        form.setFieldsValue({
          app_id: data.app_id || '',
          app_secret: '',
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
  }, [form, message])

  const handleSave = async () => {
    try {
      const payload = buildPayload(await form.validateFields(), config)
      setSaving(true)
      const data = await saveLivzonFeishuConfig(payload)
      setConfig(data)
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
      const result = await testLivzonFeishuConfig(payload)
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
    </div>
  )
}
