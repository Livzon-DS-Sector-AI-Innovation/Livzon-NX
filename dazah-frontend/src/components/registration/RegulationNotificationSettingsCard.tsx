'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Input, InputNumber, Row, Select, Space, Switch, Tag, Typography } from 'antd'

import { testRegulatoryTrackerNotificationSettings } from '@/actions/regulatory-tracker'
import {
  fetchRegulatoryTrackerNotificationRecipientsClient,
  updateRegulatoryTrackerNotificationSettingsClient,
  type RegulatoryTrackerNotificationRecipientOption,
  type RegulatoryTrackerNotificationSetting,
} from '@/lib/api/client/regulatoryTracker'

const DEFAULT_HEADER_TEMPLATE = '以下为今日法规跟踪自动抓取到的更新内容，请及时查看：'

interface RegulationNotificationSettingsCardProps {
  initialNotificationSettings: RegulatoryTrackerNotificationSetting
  notificationRecipients: RegulatoryTrackerNotificationRecipientOption[]
}

export default function RegulationNotificationSettingsCard({
  initialNotificationSettings,
  notificationRecipients,
}: RegulationNotificationSettingsCardProps) {
  const { message } = App.useApp()

  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [notificationEnabled, setNotificationEnabled] = useState(
    initialNotificationSettings.is_enabled
  )
  const [notificationRecentDays, setNotificationRecentDays] = useState(
    initialNotificationSettings.recent_days
  )
  const [notificationRecipientOpenId, setNotificationRecipientOpenId] = useState<
    string | undefined
  >(initialNotificationSettings.recipient_open_id || undefined)
  const [headerTemplate, setHeaderTemplate] = useState(
    initialNotificationSettings.header_template || ''
  )
  const [footerTemplate, setFooterTemplate] = useState(
    initialNotificationSettings.footer_template || ''
  )
  const [settingSnapshot, setSettingSnapshot] = useState<RegulatoryTrackerNotificationSetting>(
    initialNotificationSettings
  )

  const recipientsQuery = useQuery({
    queryKey: ['registration-settings', 'regulation-recipients'],
    queryFn: () => fetchRegulatoryTrackerNotificationRecipientsClient(),
    initialData: notificationRecipients,
  })
  const recipientOptions = useMemo(
    () =>
      (recipientsQuery.data ?? []).map((item) => ({
        label: item.department ? `${item.name} / ${item.department}` : item.name,
        value: item.open_id,
      })),
    [recipientsQuery.data]
  )

  function buildPayload() {
    return {
      is_enabled: notificationEnabled,
      recent_days: notificationRecentDays,
      recipient_open_id: notificationRecipientOpenId || null,
      header_template: headerTemplate.trim() || null,
      footer_template: footerTemplate.trim() || null,
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      const result = await updateRegulatoryTrackerNotificationSettingsClient(buildPayload())
      if (!result) {
        message.warning('推送配置未返回结果，请稍后刷新确认')
        return
      }
      setSettingSnapshot(result)
      message.success('法规更新推送配置已保存')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存推送配置失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleTestSend() {
    if (!notificationRecipientOpenId) {
      message.warning('请先选择接收人，再发送测试消息')
      return
    }
    setTesting(true)
    try {
      const result = await testRegulatoryTrackerNotificationSettings({
        recipient_open_id: notificationRecipientOpenId,
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
      title="法规更新推送设置"
      extra={
        <Space>
          <Button onClick={handleTestSend} loading={testing}>
            测试发送
          </Button>
          <Button type="primary" onClick={() => void handleSave()} loading={saving}>
            保存设置
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          title="系统会在每天 00:10 自动抓取法规网站更新内容，02:00 自动 AI 分析；若存在新增或更新法规，将在每天 10:00 推送到指定 QA 接收人。"
        />
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={6}>
            <Space>
              <Typography.Text strong>启用自动推送</Typography.Text>
              <Switch checked={notificationEnabled} onChange={setNotificationEnabled} />
            </Space>
          </Col>
          <Col xs={24} md={6}>
            <Space>
              <Typography.Text strong>抓取最近</Typography.Text>
              <InputNumber
                min={1}
                max={30}
                value={notificationRecentDays}
                onChange={(value) => setNotificationRecentDays(value || 7)}
                style={{ width: 110 }}
              />
              <Typography.Text>天</Typography.Text>
            </Space>
          </Col>
          <Col xs={24} md={12}>
            <Select
              showSearch
              allowClear
              style={{ width: '100%' }}
              placeholder="选择通知人（仅显示 QA 人员）"
              loading={recipientsQuery.isFetching}
              value={notificationRecipientOpenId}
              onChange={(value) => setNotificationRecipientOpenId(value)}
              optionFilterProp="label"
              options={recipientOptions}
            />
          </Col>
        </Row>

        <Space wrap size={[8, 8]}>
          <Tag color={settingSnapshot.is_enabled ? 'processing' : 'default'}>
            {settingSnapshot.is_enabled ? '已启用' : '未启用'}
          </Tag>
          <Tag color="purple">执行时间：每日 {settingSnapshot.schedule_time}</Tag>
          <Tag color="blue">当前规则命中 {settingSnapshot.pending_count} 条待推送更新</Tag>
          {settingSnapshot.recipient_name ? (
            <Tag color="gold">
              当前接收人：{settingSnapshot.recipient_name}
              {settingSnapshot.recipient_department
                ? ` / ${settingSnapshot.recipient_department}`
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
                placeholder="默认空；法规超过 10 条时自动追加：其余还有 N 条，请到系统「注册管理 - 法规跟踪」查看。"
              />
            </div>
            <Space wrap align="center">
              <Typography.Text type="secondary">
                可用变量：{'{date}'} 发送日期、{'{count}'} 待推送条数、{'{overflow_count}'}{' '}
                未展示条数（仅结尾语）。明细行格式固定，不可修改。
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
            title="当前没有可用的 QA 飞书联系人，暂时无法启用法规更新自动推送。"
          />
        ) : null}
      </Space>
    </Card>
  )
}
