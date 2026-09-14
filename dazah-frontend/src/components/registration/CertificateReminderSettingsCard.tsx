'use client'

import { useMemo, useState, useTransition } from 'react'
import { Alert, App, Button, Card, Col, Input, InputNumber, Row, Select, Space, Switch, Tag, Typography } from 'antd'
import { useRouter } from 'next/navigation'

import {
  testCertificateReminderSettings,
  updateCertificateReminderSettings,
} from '@/actions/registration'
import type {
  CertificateReminderRecipientOption,
  CertificateReminderSetting,
} from '@/types/registration'

const DEFAULT_HEADER_TEMPLATE = '以下证书已进入**到期前 {reminder_days} 天**提醒窗口，请及时处理：'

interface CertificateReminderSettingsCardProps {
  reminderSettings: CertificateReminderSetting
  reminderRecipients: CertificateReminderRecipientOption[]
}

export default function CertificateReminderSettingsCard({
  reminderSettings,
  reminderRecipients,
}: CertificateReminderSettingsCardProps) {
  const { message } = App.useApp()
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [testing, setTesting] = useState(false)
  const [reminderEnabled, setReminderEnabled] = useState(reminderSettings.is_enabled)
  const [reminderDays, setReminderDays] = useState(reminderSettings.reminder_days)
  const [recipientOpenId, setRecipientOpenId] = useState<string | undefined>(
    reminderSettings.recipient_open_id || undefined
  )
  const [headerTemplate, setHeaderTemplate] = useState(reminderSettings.header_template || '')
  const [footerTemplate, setFooterTemplate] = useState(reminderSettings.footer_template || '')

  const recipientOptions = useMemo(
    () =>
      reminderRecipients.map((item) => ({
        label: item.department ? `${item.name} / ${item.department}` : item.name,
        value: item.open_id,
      })),
    [reminderRecipients]
  )

  function buildPayload() {
    return {
      is_enabled: reminderEnabled,
      reminder_days: reminderDays,
      recipient_open_id: recipientOpenId || null,
      header_template: headerTemplate.trim() || null,
      footer_template: footerTemplate.trim() || null,
    }
  }

  function handleSaveReminderSettings() {
    startTransition(async () => {
      try {
        await updateCertificateReminderSettings(buildPayload())
        message.success('证书到期提醒配置已保存')
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '提醒配置保存失败')
      }
    })
  }

  async function handleTestSend() {
    if (!recipientOpenId) {
      message.warning('请先选择通知人，再发送测试消息')
      return
    }
    setTesting(true)
    try {
      const result = await testCertificateReminderSettings({
        recipient_open_id: recipientOpenId,
        header_template: headerTemplate.trim() || null,
        footer_template: footerTemplate.trim() || null,
      })
      if (result?.sent) {
        message.success(result.detail || '测试消息已发送，请在飞书查收')
      } else {
        message.warning(result?.detail || '测试消息发送失败')
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '测试消息发送失败')
    } finally {
      setTesting(false)
    }
  }

  function handleResetTemplates() {
    setHeaderTemplate('')
    setFooterTemplate('')
  }

  return (
    <Card
      size="small"
      title="证书到期提醒设置"
      extra={
        <Space>
          <Button onClick={handleTestSend} loading={testing}>
            测试发送
          </Button>
          <Button type="primary" onClick={handleSaveReminderSettings} loading={pending}>
            保存设置
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={6}>
            <Space>
              <Typography.Text strong>启用自动提醒</Typography.Text>
              <Switch checked={reminderEnabled} onChange={setReminderEnabled} />
            </Space>
          </Col>
          <Col xs={24} md={6}>
            <Space>
              <Typography.Text strong>到期前</Typography.Text>
              <InputNumber
                min={1}
                max={365}
                value={reminderDays}
                onChange={(value) => setReminderDays(value || 90)}
                style={{ width: 110 }}
              />
              <Typography.Text>天通知</Typography.Text>
            </Space>
          </Col>
          <Col xs={24} md={12}>
            <Select
              showSearch
              allowClear
              style={{ width: '100%' }}
              placeholder="选择通知人（仅显示 QA 人员）"
              value={recipientOpenId}
              onChange={(value) => setRecipientOpenId(value)}
              optionFilterProp="label"
              options={recipientOptions}
            />
          </Col>
        </Row>

        <Space wrap size={[8, 8]}>
          <Tag color={reminderSettings.is_enabled ? 'processing' : 'default'}>
            {reminderSettings.is_enabled ? '已启用' : '未启用'}
          </Tag>
          <Tag color="purple">当前规则命中 {reminderSettings.pending_count} 份待提醒证书</Tag>
          {reminderSettings.recipient_name ? (
            <Tag color="blue">
              当前通知人：{reminderSettings.recipient_name}
              {reminderSettings.recipient_department
                ? ` / ${reminderSettings.recipient_department}`
                : ''}
            </Tag>
          ) : null}
        </Space>

        <Card type="inner" size="small" title="消息模板（开头语 / 结尾语）">
          <Space orientation="vertical" size={12} style={{ width: '100%' }}>
            <div>
              <Typography.Text strong>开头语</Typography.Text>
              <Input.TextArea
                rows={2}
                maxLength={500}
                showCount
                value={headerTemplate}
                onChange={(event) => setHeaderTemplate(event.target.value)}
                placeholder={DEFAULT_HEADER_TEMPLATE}
              />
            </div>
            <div>
              <Typography.Text strong>结尾语</Typography.Text>
              <Input.TextArea
                rows={2}
                maxLength={500}
                showCount
                value={footerTemplate}
                onChange={(event) => setFooterTemplate(event.target.value)}
                placeholder="默认空；证书超过 10 条时自动追加：其余还有 N 份，请到系统「注册管理 - 证书管理」查看。"
              />
            </div>
            <Space wrap align="center">
              <Typography.Text type="secondary">
                可用变量：{'{date}'} 发送日期、{'{count}'} 命中证书数、{'{reminder_days}'} 提前天数、
                {'{overflow_count}'} 未展示条数（仅结尾语）。明细行格式固定，不可修改。
              </Typography.Text>
              <Button size="small" onClick={handleResetTemplates}>
                恢复默认文案
              </Button>
            </Space>
          </Space>
        </Card>

        <Typography.Text type="secondary">
          通知人直接取自质量管理中的 QA 飞书联系人。人员变动后，直接在这里重新选择即可；保存前可先「测试发送」验证模板效果。
        </Typography.Text>

        {!recipientOptions.length ? (
          <Alert
            type="warning"
            showIcon
            title="当前没有可用的 QA 飞书联系人，暂时无法启用自动提醒。"
          />
        ) : null}
      </Space>
    </Card>
  )
}
