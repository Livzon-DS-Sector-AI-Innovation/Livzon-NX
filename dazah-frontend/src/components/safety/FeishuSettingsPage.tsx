'use client'

import { useCallback, useState } from 'react'

import {
  ApiOutlined,
  SaveOutlined,
  SecurityScanOutlined,
  SendOutlined,
} from '@ant-design/icons'
import { App, Button, Card, Input, Space, Switch, Tabs, Tag, Typography } from 'antd'

import {
  getSafetyFeishuSettings,
  testRadarNotify,
  getSafetyFeishuWsStatus,
  restartSafetyFeishuWs,
  saveSafetyFeishuSettings,
  testSafetyFeishuSettings,
} from '@/actions/safety'
import PlatformNotice from '@/components/shared/PlatformNotice'
import type { components } from '@/types/generated/schema'

type SafetyFeishuAppSettingsDetail = components['schemas']['SafetyFeishuAppSettingsDetail']
type UpdateSafetyFeishuAppSettingsRequest = components['schemas']['UpdateSafetyFeishuAppSettingsRequest']

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '未测试'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '未测试'
  return parsed.toLocaleString('zh-CN', { hour12: false })
}

function renderSyncTag(status: string | null | undefined) {
  if (status === 'success') return <Tag color="success">同步成功</Tag>
  if (status === 'partial') return <Tag color="warning">部分失败</Tag>
  if (status === 'failed') return <Tag color="error">同步失败</Tag>
  return <Tag>未同步</Tag>
}

function renderStatusTag(status: string | null | undefined) {
  if (status === 'success') return <Tag color="success">连接正常</Tag>
  if (status === 'failed') return <Tag color="error">连接失败</Tag>
  return <Tag>未测试</Tag>
}

type WsStatus = {
  connected?: boolean
  is_connected?: boolean
  running?: boolean
  registered_events?: string[]
  event_types?: string[]
}

export default function FeishuSettingsPage({
  initialSettings,
  initialWsStatus,
}: {
  initialSettings: SafetyFeishuAppSettingsDetail | null
  initialWsStatus: Record<string, unknown> | null
}) {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [restartingWs, setRestartingWs] = useState(false)
  const [settings, setSettings] = useState<SafetyFeishuAppSettingsDetail | null>(initialSettings)
  const [form, setForm] = useState<UpdateSafetyFeishuAppSettingsRequest>({
    app_id: initialSettings?.app_id || '',
    app_secret: '',
    bitable_app_token: initialSettings?.bitable_app_token || null,
    bitable_hazard_table_id: initialSettings?.bitable_hazard_table_id || null,
    knowledge_app_token: initialSettings?.knowledge_app_token || null,
    knowledge_table_id: initialSettings?.knowledge_table_id || null,
    radar_notify_enabled: initialSettings?.radar_notify_enabled ?? false,
    radar_notify_chat_ids: initialSettings?.radar_notify_chat_ids ?? [],
    radar_notify_user_ids: initialSettings?.radar_notify_user_ids ?? [],
    is_enabled: initialSettings?.is_enabled ?? true,
  })
  const [notifyChatIdsText, setNotifyChatIdsText] = useState(
    (initialSettings?.radar_notify_chat_ids ?? []).join('\n')
  )
  const [notifyUserIdsText, setNotifyUserIdsText] = useState(
    (initialSettings?.radar_notify_user_ids ?? []).join('\n')
  )
  const [notifyTesting, setNotifyTesting] = useState(false)
  const [wsStatus, setWsStatus] = useState<WsStatus | null>(
    (initialWsStatus as WsStatus | null) ?? null
  )

  const handleSave = useCallback(async () => {
    if (!form.app_id.trim()) {
      message.warning('请填写飞书应用 App ID')
      return
    }
    if (!settings && !form.app_secret.trim()) {
      message.warning('首次保存需要填写 App Secret')
      return
    }
    setSaving(true)
    const payload: UpdateSafetyFeishuAppSettingsRequest = {
      ...form,
      radar_notify_chat_ids: notifyChatIdsText
        .split(/[,，\n]/)
        .map((s) => s.trim())
        .filter(Boolean),
      radar_notify_user_ids: notifyUserIdsText
        .split(/[,，\n]/)
        .map((s) => s.trim())
        .filter(Boolean),
    }
    const res = await saveSafetyFeishuSettings(payload)
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('飞书配置已保存')
      setSettings(res.data)
      setForm((current) => ({ ...current, app_secret: '' }))
    } else {
      message.error(res.message || '保存失败')
    }
  }, [form, message, settings, notifyChatIdsText, notifyUserIdsText])

  const handleTestNotify = useCallback(async () => {
    // 先保存当前通知配置，再发测试卡片
    if (!form.app_id.trim()) {
      message.warning('请先填写飞书应用 App ID')
      return
    }
    setNotifyTesting(true)
    try {
      const saveRes = await saveSafetyFeishuSettings({
        ...form,
        radar_notify_chat_ids: notifyChatIdsText
          .split(/[,，\n]/)
          .map((s) => s.trim())
          .filter(Boolean),
        radar_notify_user_ids: notifyUserIdsText
          .split(/[,，\n]/)
          .map((s) => s.trim())
          .filter(Boolean),
      })
      if (saveRes.code !== 200) {
        message.error(saveRes.message || '保存配置失败')
        return
      }
      setSettings(saveRes.data ?? null)
      const res = await testRadarNotify()
      if (res.code === 200 && res.data) {
        const d = res.data as { sent?: number; errors?: string[] }
        if ((d.sent ?? 0) > 0) {
          message.success(`测试通知已发送（${d.sent} 个目标）`)
        } else {
          message.error((d.errors ?? []).join('；') || '发送失败')
        }
      } else {
        message.error(res.message || '测试发送失败')
      }
    } finally {
      setNotifyTesting(false)
    }
  }, [form, message, notifyChatIdsText, notifyUserIdsText])

  const handleTest = useCallback(async () => {
    setTesting(true)
    const res = await testSafetyFeishuSettings()
    setTesting(false)
    if (res.code === 200 && res.data) {
      if (res.data.success) {
        message.success(res.data.message || '连接成功')
      } else {
        message.error(res.data.message || '连接失败')
      }
      const refreshed = await getSafetyFeishuSettings()
      if (refreshed.code === 200 && refreshed.data) {
        setSettings(refreshed.data)
      }
    } else {
      message.error(res.message || '测试失败')
    }
  }, [message])

  const handleRestartWs = useCallback(async () => {
    setRestartingWs(true)
    const res = await restartSafetyFeishuWs()
    setRestartingWs(false)
    if (res.code === 200) {
      message.success('已重新发起飞书事件订阅连接')
      const status = await getSafetyFeishuWsStatus()
      if (status.code === 200 && status.data) {
        setWsStatus(status.data as WsStatus)
      }
    } else {
      message.error(res.message || '重连失败')
    }
  }, [message])

  const wsConnected = Boolean(wsStatus?.connected ?? wsStatus?.is_connected ?? wsStatus?.running)

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <PlatformNotice
        type="info"
        title="安全模块使用独立飞书应用凭证，在此页面统一维护"
        description={
          'App Secret 加密存储，仅在保存时写入，页面只回显掩码；隐患多维表格绑定用于台账双向同步与卡片链接。'
        }
      />
      <Tabs
        defaultActiveKey="bitable"
        items={[
          {
            key: 'bitable',
            label: '应用与多维表格',
            children: (
              <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <Card
        title="飞书应用信息"
        extra={
          <Space>
            <Button
              icon={<SecurityScanOutlined />}
              onClick={() => void handleTest()}
              loading={testing}
            >
              测试连接
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={() => void handleSave()} loading={saving}>
              保存配置
            </Button>
          </Space>
        }
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              App ID
            </Button>
            <Input
              value={form.app_id}
              placeholder="请输入安全模块飞书应用 App ID"
              onChange={(event) =>
                setForm((current) => ({ ...current, app_id: event.target.value }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              App Secret
            </Button>
            <Input.Password
              value={form.app_secret}
              placeholder={settings?.app_secret_masked || '留空则保持当前 Secret 不变'}
              onChange={(event) =>
                setForm((current) => ({ ...current, app_secret: event.target.value }))
              }
            />
          </Space.Compact>
          <Space size={12} wrap>
            <Typography.Text>启用飞书集成</Typography.Text>
            <Switch
              checked={form.is_enabled}
              onChange={(checked) =>
                setForm((current) => ({ ...current, is_enabled: checked }))
              }
            />
            {renderStatusTag(settings?.last_test_status)}
            <Typography.Text type="secondary">
              最近测试：{formatDateTime(settings?.last_tested_at)}
            </Typography.Text>
          </Space>
          {settings?.last_test_error ? (
            <PlatformNotice type="warning" title={settings.last_test_error} />
          ) : null}
        </Space>
      </Card>

      <Card title="隐患多维表格绑定">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              App Token
            </Button>
            <Input
              value={form.bitable_app_token ?? ''}
              placeholder="隐患多维表格 app_token（bascn 开头）"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  bitable_app_token: event.target.value || null,
                }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              Table ID
            </Button>
            <Input
              value={form.bitable_hazard_table_id ?? ''}
              placeholder="隐患登记表 table_id（tbl 开头）"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  bitable_hazard_table_id: event.target.value || null,
                }))
              }
            />
          </Space.Compact>
          <Typography.Text type="secondary">
            Bitable 事件订阅（隐患登记双向同步）依赖该绑定；修改后请保存并通过右侧按钮重连事件订阅。
          </Typography.Text>
        </Space>
      </Card>
      </Space>
            ),
          },
          {
            key: 'notify',
            label: '通知设置',
            children: (
      <Card title="法规雷达通知（扫描结果推送到飞书）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space size={12} wrap>
            <Typography.Text>启用扫描结果通知</Typography.Text>
            <Switch
              checked={form.radar_notify_enabled}
              onChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  radar_notify_enabled: checked,
                }))
              }
            />
            <Typography.Text type="secondary">
              开启后，每次扫描发现新法规/修订时，自动推送卡片到下方群和个人
            </Typography.Text>
          </Space>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              群 chat_id
            </Button>
            <Input
              value={notifyChatIdsText}
              placeholder="飞书群 chat_id，多个用英文逗号分隔（oc_ 开头）"
              onChange={(event) => setNotifyChatIdsText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              个人 open_id
            </Button>
            <Input
              value={notifyUserIdsText}
              placeholder="个人 open_id，多个用英文逗号分隔（ou_ 开头）"
              onChange={(event) => setNotifyUserIdsText(event.target.value)}
            />
          </Space.Compact>
          <Typography.Text type="secondary">
            需先把本应用的机器人拉进目标群；个人通知发给 open_id 对应的用户。
            修改后请先「保存配置」，再点「发送测试通知」验证。
          </Typography.Text>
          <div>
            <Button
              icon={<SendOutlined />}
              onClick={() => void handleTestNotify()}
              loading={notifyTesting}
            >
              发送测试通知
            </Button>
          </div>
        </Space>
      </Card>
            ),
          },
          {
            key: 'radar',
            label: '法规雷达',
            children: (
              <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <Card title="EHS 法规库绑定（安全知识库）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              App Token
            </Button>
            <Input
              value={form.knowledge_app_token ?? ''}
              placeholder="EHS 法规库多维表格 app_token（链接中 /base/ 后一段）"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  knowledge_app_token: event.target.value || null,
                }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              Table ID
            </Button>
            <Input
              value={form.knowledge_table_id ?? ''}
              placeholder="法规数据表 table_id（链接中 table= 参数，tbl 开头）"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  knowledge_table_id: event.target.value || null,
                }))
              }
            />
          </Space.Compact>
          <Space size={12} wrap>
            <Typography.Text>最近同步：</Typography.Text>
            {renderSyncTag(settings?.knowledge_last_sync_status)}
            <Typography.Text type="secondary">
              {formatDateTime(settings?.knowledge_last_synced_at)}
            </Typography.Text>
          </Space>
          {settings?.knowledge_last_sync_error ? (
            <PlatformNotice type="warning" title={settings.knowledge_last_sync_error} />
          ) : null}
          <Typography.Text type="secondary">
            保存后到 安全管理 → 安全知识库 点击「同步飞书法规库」拉取法规台账；附件预览走安全应用凭证代理下载。
          </Typography.Text>
        </Space>
      </Card>

      <Card
        title="飞书事件订阅（WebSocket）"
        extra={
          <Button
            icon={<ApiOutlined />}
            onClick={() => void handleRestartWs()}
            loading={restartingWs}
          >
            重连事件订阅
          </Button>
        }
      >
        <Space size={12} wrap>
          {wsConnected ? <Tag color="success">已连接</Tag> : <Tag color="warning">未连接</Tag>}
          <Typography.Text type="secondary">
            {wsConnected
              ? `已注册事件：${(wsStatus?.registered_events ?? wsStatus?.event_types ?? []).join('、') || '无'}`
              : '未连接时隐患表格变更不会同步；配置保存后可点击「重连事件订阅」恢复。'}
          </Typography.Text>
        </Space>
      </Card>
      </Space>
            ),
          },
        ]}
      />
    </Space>
  )
}
