'use client'

import { useMemo, useState } from 'react'
import { Alert, App, Button, Card, Descriptions, Input, Space, Tag, Typography } from 'antd'
import { CheckCircleOutlined, LinkOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import {
  saveProcurementMaterialSource,
  testProcurementMaterialSource,
} from '@/actions/purchasing'
import type {
  MaterialSourceConfigResponse,
  MaterialSourceProbeResponse,
} from '@/types/purchasing'

type ProcurementMaterialSourceSettingsClientProps = {
  initialConfig: MaterialSourceConfigResponse | null
  initialLoadFailed?: boolean
}

function statusTag(status: string | undefined) {
  if (status === 'success') return <Tag color="success">连接正常</Tag>
  if (status === 'error') return <Tag color="error">测试失败</Tag>
  return <Tag>未测试</Tag>
}

export function ProcurementMaterialSourceSettingsClient({
  initialConfig,
  initialLoadFailed = false,
}: ProcurementMaterialSourceSettingsClientProps) {
  const { message } = App.useApp()
  const [sourceUrl, setSourceUrl] = useState(initialConfig?.source_url ?? '')
  const [config, setConfig] = useState(initialConfig)
  const [probe, setProbe] = useState<MaterialSourceProbeResponse | null>(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)

  const displaySource = probe ?? config
  const latestStatus = probe?.status ?? config?.last_test_status
  const latestError = probe?.error_message ?? config?.last_test_error
  const availableFields = useMemo(() => {
    if (probe?.available_fields?.length) return probe.available_fields
    return config
      ? [
          config.material_code_field,
          config.material_description_field,
          config.rule_model_field,
        ]
      : []
  }, [config, probe])

  async function handleTest() {
    const nextUrl = sourceUrl.trim()
    if (!nextUrl) {
      message.warning('请输入飞书多维表格链接')
      return
    }
    setTesting(true)
    try {
      const response = await testProcurementMaterialSource({ source_url: nextUrl })
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '物料数据源测试失败')
        return
      }
      setProbe(response.data)
      message.success('飞书多维表格连接测试通过')
    } catch {
      message.error('物料数据源测试失败，请稍后重试')
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    const nextUrl = sourceUrl.trim()
    if (!nextUrl) {
      message.warning('请输入飞书多维表格链接')
      return
    }
    setSaving(true)
    try {
      const response = await saveProcurementMaterialSource({ source_url: nextUrl })
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '物料数据源保存失败')
        return
      }
      setConfig(response.data)
      setProbe(null)
      message.success('采购物料数据源配置已保存')
    } catch {
      message.error('物料数据源保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 系统设置</p>
        <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">采购设置</h1>
        <p className="text-[13px] text-[var(--color-steel)]">
          八类物料明细共用同一张飞书多维表格。平台使用已绑定的企业自建应用访问，采购模块不保存 App Secret。
        </p>
      </div>

      {initialLoadFailed && (
        <Alert
          type="warning"
          showIcon
          message="当前配置读取失败"
          description="可以继续输入链接并测试；保存前会再次校验飞书访问权限和字段。"
        />
      )}

      <Card title="物料数据源" bordered={false}>
        <Space direction="vertical" size="large" className="w-full">
          <div>
            <Typography.Text strong>飞书多维表格链接</Typography.Text>
            <Input
              className="mt-2"
              prefix={<LinkOutlined />}
              value={sourceUrl}
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder="粘贴包含 /base/{app_token} 和 table 参数的链接"
              maxLength={1024}
              allowClear
            />
            <Typography.Text type="secondary" className="mt-1 block text-[12px]">
              保存时自动识别物料编码、物料说明和规格型号字段；旧表中的“规则型号”也可兼容。
            </Typography.Text>
          </div>

          <Space>
            <Button icon={<ReloadOutlined />} loading={testing} onClick={handleTest}>
              测试连接
            </Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
              保存配置
            </Button>
          </Space>

          <Descriptions bordered size="small" column={2} title="解析结果">
            <Descriptions.Item label="App Token">
              {displaySource?.app_token || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="数据表">
              {displaySource?.table_id || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="视图">
              {displaySource?.view_id || '未指定，使用默认视图'}
            </Descriptions.Item>
            <Descriptions.Item label="最近测试">
              {statusTag(latestStatus)}
              {latestError && <span className="ml-2 text-[12px] text-[var(--color-danger)]">{latestError}</span>}
            </Descriptions.Item>
            <Descriptions.Item label="物料编码字段">
              {displaySource?.material_code_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="物料说明字段">
              {displaySource?.material_description_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="规格型号字段">
              {displaySource?.rule_model_field || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="测试时间">
              {probe?.tested_at || config?.last_tested_at || '—'}
            </Descriptions.Item>
          </Descriptions>

          {availableFields.length > 0 && (
            <div>
              <Typography.Text type="secondary">已识别字段</Typography.Text>
              <div className="mt-2 flex flex-wrap gap-2">
                {availableFields.map((field) => (
                  <Tag key={field} icon={<CheckCircleOutlined />}>
                    {field}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Space>
      </Card>
    </div>
  )
}
