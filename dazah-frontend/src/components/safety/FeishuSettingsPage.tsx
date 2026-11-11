'use client'

import { useCallback, useState } from 'react'

import {
  ApiOutlined,
  SaveOutlined,
  SecurityScanOutlined,
  SendOutlined,
} from '@ant-design/icons'
import { App, Button, Card, Input, Select, Space, Switch, Tabs, Tag, Typography } from 'antd'

import {
  getSafetyFeishuSettings,
  testCommitmentNotify,
  testFireExpiryNotify,
  testHazardDueNotify,
  testRadarNotify,
  getSafetyFeishuWsStatus,
  restartSafetyFeishuWs,
  saveSafetyFeishuSettings,
  testSafetyFeishuSettings,
} from '@/actions/safety'
import PlatformNotice from '@/components/shared/PlatformNotice'
import PageFeishuTableConfigCard from '@/components/safety/PageFeishuTableConfigCard'
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
    radar_scan_enabled: initialSettings?.radar_scan_enabled ?? true,
    radar_notify_enabled: initialSettings?.radar_notify_enabled ?? false,
    radar_notify_chat_ids: initialSettings?.radar_notify_chat_ids ?? [],
    radar_notify_user_ids: initialSettings?.radar_notify_user_ids ?? [],
    hazard_due_notify_enabled:
      initialSettings?.hazard_due_notify_enabled ?? false,
    hazard_due_notify_milestones:
      initialSettings?.hazard_due_notify_milestones ?? [30, 15, 7],
    hazard_due_notify_chat_ids:
      initialSettings?.hazard_due_notify_chat_ids ?? [],
    hazard_due_notify_user_ids:
      initialSettings?.hazard_due_notify_user_ids ?? [],
    fire_expiry_notify_enabled:
      initialSettings?.fire_expiry_notify_enabled ?? false,
    fire_expiry_notify_milestones:
      initialSettings?.fire_expiry_notify_milestones ?? [30, 15, 7],
    fire_expiry_notify_chat_ids:
      initialSettings?.fire_expiry_notify_chat_ids ?? [],
    fire_expiry_notify_user_ids:
      initialSettings?.fire_expiry_notify_user_ids ?? [],
    permit_notify_enabled: initialSettings?.permit_notify_enabled ?? false,
    permit_notify_chat_ids: initialSettings?.permit_notify_chat_ids ?? [],
    permit_notify_user_ids: initialSettings?.permit_notify_user_ids ?? [],
    cert_expiry_notify_enabled:
      initialSettings?.cert_expiry_notify_enabled ?? false,
    cert_expiry_notify_milestones:
      initialSettings?.cert_expiry_notify_milestones ?? [30, 15, 7],
    cert_expiry_notify_chat_ids:
      initialSettings?.cert_expiry_notify_chat_ids ?? [],
    cert_expiry_notify_user_ids:
      initialSettings?.cert_expiry_notify_user_ids ?? [],
    commitment_notify_enabled:
      initialSettings?.commitment_notify_enabled ?? false,
    commitment_push_time: initialSettings?.commitment_push_time || '08:30',
    commitment_user_ids: initialSettings?.commitment_user_ids ?? [],
    is_enabled: initialSettings?.is_enabled ?? true,
  })
  const [notifyChatIdsText, setNotifyChatIdsText] = useState(
    (initialSettings?.radar_notify_chat_ids ?? []).join('\n')
  )
  const [notifyUserIdsText, setNotifyUserIdsText] = useState(
    (initialSettings?.radar_notify_user_ids ?? []).join('\n')
  )
  const [notifyTesting, setNotifyTesting] = useState(false)
  // 隐患到期提醒推送的目标输入（保存时解析成数组）
  const [dueChatIdsText, setDueChatIdsText] = useState(
    (initialSettings?.hazard_due_notify_chat_ids ?? []).join('\n')
  )
  const [dueUserIdsText, setDueUserIdsText] = useState(
    (initialSettings?.hazard_due_notify_user_ids ?? []).join('\n')
  )
  // 提醒节点输入（如 30,15,7 = 到期前一个月/半个月/一周各提醒一次）
  const [milestonesText, setMilestonesText] = useState(
    (initialSettings?.hazard_due_notify_milestones ?? [30, 15, 7]).join(',')
  )
  const [dueTesting, setDueTesting] = useState(false)
  // 消防器材有效期提醒推送的目标/节点输入
  const [fireChatIdsText, setFireChatIdsText] = useState(
    (initialSettings?.fire_expiry_notify_chat_ids ?? []).join('\n')
  )
  const [fireUserIdsText, setFireUserIdsText] = useState(
    (initialSettings?.fire_expiry_notify_user_ids ?? []).join('\n')
  )
  const [fireMilestonesText, setFireMilestonesText] = useState(
    (initialSettings?.fire_expiry_notify_milestones ?? [30, 15, 7]).join(',')
  )
  const [fireTesting, setFireTesting] = useState(false)
  // 8 大作业票卡片通知的目标输入
  const [permitChatIdsText, setPermitChatIdsText] = useState(
    (initialSettings?.permit_notify_chat_ids ?? []).join('\n')
  )
  const [permitUserIdsText, setPermitUserIdsText] = useState(
    (initialSettings?.permit_notify_user_ids ?? []).join('\n')
  )
  // 特种作业证件到期提醒的目标/节点输入
  const [certChatIdsText, setCertChatIdsText] = useState(
    (initialSettings?.cert_expiry_notify_chat_ids ?? []).join('\n')
  )
  const [certUserIdsText, setCertUserIdsText] = useState(
    (initialSettings?.cert_expiry_notify_user_ids ?? []).join('\n')
  )
  const [certMilestonesText, setCertMilestonesText] = useState(
    (initialSettings?.cert_expiry_notify_milestones ?? [30, 15, 7]).join(',')
  )
  // 安全承诺填报：填报人员（open_id）选择器的远程候选项
  const [commitmentTesting, setCommitmentTesting] = useState(false)
  const [personOptions, setPersonOptions] = useState<
    { label: string; value: string }[]
  >([])
  const [wsStatus, setWsStatus] = useState<WsStatus | null>(
    (initialWsStatus as WsStatus | null) ?? null
  )

  /** 远程搜索人员：只把已绑定飞书的人员作为可选项（value = open_id）。 */
  const searchPersonnel = useCallback(async (keyword: string) => {
    const query = new URLSearchParams({ limit: '50' })
    if (keyword.trim()) query.set('keyword', keyword.trim())
    try {
      const res = await fetch(`/api/v1/identity/personnel?${query.toString()}`)
      if (!res.ok) return
      const body = (await res.json()) as {
        data?: {
          items?: {
            name?: string
            department_name?: string | null
            feishu_open_id?: string | null
          }[]
        }
      }
      const items = body.data?.items ?? []
      setPersonOptions(
        items
          .filter((item) => item.feishu_open_id)
          .map((item) => ({
            label: `${item.name ?? ''}${item.department_name ? `（${item.department_name}）` : ''}`,
            value: String(item.feishu_open_id),
          }))
      )
    } catch {
      // 搜索失败保持手动粘贴 open_id 的能力
    }
  }, [])

  /** 把多行/逗号分隔的目标输入解析为数组。 */
  const parseIds = (text: string) =>
    text.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean)

  const buildDuePayload = useCallback(
    (): UpdateSafetyFeishuAppSettingsRequest => ({
      ...form,
      radar_scan_enabled: form.radar_scan_enabled,
      radar_notify_chat_ids: parseIds(notifyChatIdsText),
      radar_notify_user_ids: parseIds(notifyUserIdsText),
      hazard_due_notify_enabled: form.hazard_due_notify_enabled,
      hazard_due_notify_milestones: milestonesText
        .split(/[,，\s]+/)
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isInteger(n) && n > 0 && n <= 365),
      hazard_due_notify_chat_ids: parseIds(dueChatIdsText),
      hazard_due_notify_user_ids: parseIds(dueUserIdsText),
      fire_expiry_notify_enabled: form.fire_expiry_notify_enabled,
      fire_expiry_notify_milestones: fireMilestonesText
        .split(/[,，\s]+/)
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isInteger(n) && n >= 0 && n <= 365),
      fire_expiry_notify_chat_ids: parseIds(fireChatIdsText),
      fire_expiry_notify_user_ids: parseIds(fireUserIdsText),
      permit_notify_enabled: form.permit_notify_enabled,
      permit_notify_chat_ids: parseIds(permitChatIdsText),
      permit_notify_user_ids: parseIds(permitUserIdsText),
      cert_expiry_notify_enabled: form.cert_expiry_notify_enabled,
      cert_expiry_notify_milestones: certMilestonesText
        .split(/[,，\s]+/)
        .map((s) => parseInt(s, 10))
        .filter((n) => Number.isInteger(n) && n >= 0 && n <= 365),
      cert_expiry_notify_chat_ids: parseIds(certChatIdsText),
      cert_expiry_notify_user_ids: parseIds(certUserIdsText),
      commitment_notify_enabled: form.commitment_notify_enabled,
      commitment_push_time: form.commitment_push_time,
      commitment_user_ids: form.commitment_user_ids,
    }),
    [form, notifyChatIdsText, notifyUserIdsText, dueChatIdsText, dueUserIdsText, milestonesText, fireChatIdsText, fireUserIdsText, fireMilestonesText]
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
    const payload: UpdateSafetyFeishuAppSettingsRequest = buildDuePayload()
    const res = await saveSafetyFeishuSettings(payload)
    setSaving(false)
    if (res.code === 200 && res.data) {
      message.success('飞书配置已保存')
      setSettings(res.data)
      setForm((current) => ({ ...current, app_secret: '' }))
    } else {
      message.error(res.message || '保存失败')
    }
  }, [buildDuePayload, form, message, settings])

  const handleTestDueNotify = useCallback(async () => {
    if (!form.app_id.trim()) {
      message.warning('请先填写飞书应用 App ID')
      return
    }
    setDueTesting(true)
    try {
      // 先保存当前提醒配置，再发测试卡片
      const saveRes = await saveSafetyFeishuSettings(buildDuePayload())
      if (saveRes.code !== 200) {
        message.error(saveRes.message || '保存配置失败')
        return
      }
      setSettings(saveRes.data ?? null)
      const res = await testHazardDueNotify()
      if (res.code === 200 && res.data) {
        const d = res.data as { sent?: number; errors?: string[] }
        if ((d.sent ?? 0) > 0) {
          message.success(`测试提醒已发送（${d.sent} 个目标）`)
        } else {
          message.error((d.errors ?? []).join('；') || '发送失败')
        }
      } else {
        message.error(res.message || '测试发送失败')
      }
    } finally {
      setDueTesting(false)
    }
  }, [buildDuePayload, form.app_id, message])

  const handleTestFireExpiryNotify = useCallback(async () => {
    if (!form.app_id.trim()) {
      message.warning('请先填写飞书应用 App ID')
      return
    }
    setFireTesting(true)
    try {
      // 先保存当前提醒配置，再发测试卡片
      const saveRes = await saveSafetyFeishuSettings(buildDuePayload())
      if (saveRes.code !== 200) {
        message.error(saveRes.message || '保存配置失败')
        return
      }
      setSettings(saveRes.data ?? null)
      const res = await testFireExpiryNotify()
      if (res.code === 200 && res.data) {
        const d = res.data as { sent?: number; errors?: string[] }
        if ((d.sent ?? 0) > 0) {
          message.success(`测试提醒已发送（${d.sent} 个目标）`)
        } else {
          message.error((d.errors ?? []).join('；') || '发送失败')
        }
      } else {
        message.error(res.message || '测试发送失败')
      }
    } finally {
      setFireTesting(false)
    }
  }, [buildDuePayload, form.app_id, message])

  const handleTestNotify = useCallback(async () => {
    // 先保存当前通知配置，再发测试卡片
    if (!form.app_id.trim()) {
      message.warning('请先填写飞书应用 App ID')
      return
    }
    setNotifyTesting(true)
    try {
      const saveRes = await saveSafetyFeishuSettings(buildDuePayload())
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
  }, [buildDuePayload, form.app_id, message])

  const handleTestCommitment = useCallback(async () => {
    if (!form.app_id.trim()) {
      message.warning('请先填写飞书应用 App ID')
      return
    }
    if ((form.commitment_user_ids ?? []).length === 0) {
      message.warning('请先选择至少一名填报人员')
      return
    }
    setCommitmentTesting(true)
    try {
      // 先保存当前填报配置，再向第一个填报人员发样例卡
      const saveRes = await saveSafetyFeishuSettings(buildDuePayload())
      if (saveRes.code !== 200) {
        message.error(saveRes.message || '保存配置失败')
        return
      }
      setSettings(saveRes.data ?? null)
      const res = await testCommitmentNotify()
      if (res.code === 200 && res.data?.success) {
        message.success(res.data.message || '测试卡片已发送')
      } else {
        message.error(res.data?.message || res.message || '测试发送失败')
      }
    } finally {
      setCommitmentTesting(false)
    }
  }, [buildDuePayload, form.app_id, form.commitment_user_ids, message])

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
              aria-label="启用飞书集成"
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
      <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <Card title="法规雷达通知（扫描结果推送到飞书）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space size={12} wrap>
            <Typography.Text>自动扫描（每周一 08:00）</Typography.Text>
            <Switch
              aria-label="自动扫描法规"
              checked={form.radar_scan_enabled}
              onChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  radar_scan_enabled: checked,
                }))
              }
            />
            <Typography.Text type="secondary">
              关闭后定时任务不再自动扫描（手动「立即扫描」仍可用）
            </Typography.Text>
          </Space>
          <Space size={12} wrap>
            <Typography.Text>启用扫描结果通知</Typography.Text>
            <Switch
              aria-label="推送扫描结果通知"
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
      <Card title="隐患到期提醒（按目标完成日期的提醒节点推送）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space size={12} wrap>
            <Typography.Text>启用到期提醒</Typography.Text>
            <Switch
              aria-label="启用隐患到期提醒"
              checked={form.hazard_due_notify_enabled}
              onChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  hazard_due_notify_enabled: checked,
                }))
              }
            />
            <Typography.Text type="secondary">
              每天 08:00 检查隐患台账：隐患「目标完成日期」进入下方某个提醒节点
              或已逾期时，推送到下方群和个人；同一节点只推一次，不重复打扰
            </Typography.Text>
          </Space>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              提醒节点（天）
            </Button>
            <Input
              value={milestonesText}
              placeholder="提醒提前天数，如 7（只填一个数 = 只在该时间点提醒一次；多个如 30,15,7 = 层层递进）"
              onChange={(event) => setMilestonesText(event.target.value)}
            />
          </Space.Compact>
          <Typography.Text type="secondary">
            逗号分隔的天数列表，可按需设置任意节点（如 60,30,15,7）；
            隐患进入某节点当天推送一次，越接近到期节点越靠后提醒。
          </Typography.Text>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              群 chat_id
            </Button>
            <Input
              value={dueChatIdsText}
              placeholder="提醒群 chat_id，多个用英文逗号分隔（oc_ 开头）"
              onChange={(event) => setDueChatIdsText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              个人 open_id
            </Button>
            <Input
              value={dueUserIdsText}
              placeholder="提醒个人 open_id，多个用英文逗号分隔（ou_ 开头）"
              onChange={(event) => setDueUserIdsText(event.target.value)}
            />
          </Space.Compact>
          <Typography.Text type="secondary">
            推送对象与法规雷达通知相互独立；同样需先把本应用的机器人拉进目标群。
            修改后先「保存配置」，再点「发送测试提醒」验证。
          </Typography.Text>
          <div>
            <Button
              icon={<SendOutlined />}
              onClick={() => void handleTestDueNotify()}
              loading={dueTesting}
            >
              发送测试提醒
            </Button>
          </div>
        </Space>
      </Card>
      <Card title="消防器材有效期提醒（灭火器/消防栓到期推送）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space size={12} wrap>
            <Typography.Text>启用有效期提醒</Typography.Text>
            <Switch
              aria-label="启用消防器材有效期提醒"
              checked={form.fire_expiry_notify_enabled}
              onChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  fire_expiry_notify_enabled: checked,
                }))
              }
            />
            <Typography.Text type="secondary">
              每天 08:20 检查消防器材台账：器材「有效日期」进入下方某个提醒节点
              或已过期时，推送到下方群和个人；同一台器材同一节点只推一次。
              节点填 0 表示过期后再推一次。
            </Typography.Text>
          </Space>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              提醒节点（天）
            </Button>
            <Input
              value={fireMilestonesText}
              placeholder="到期前提醒天数，如 30,15,7；填 0 表示过期后再提醒一次"
              onChange={(event) => setFireMilestonesText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              群 chat_id
            </Button>
            <Input
              value={fireChatIdsText}
              placeholder="提醒群 chat_id，多个用英文逗号分隔（oc_ 开头）"
              onChange={(event) => setFireChatIdsText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              个人 open_id
            </Button>
            <Input
              value={fireUserIdsText}
              placeholder="提醒个人 open_id，多个用英文逗号分隔（ou_ 开头）"
              onChange={(event) => setFireUserIdsText(event.target.value)}
            />
          </Space.Compact>
          <Typography.Text type="secondary">
            提醒内容包含器材编号、部门、位置、责任人与到期天数；
            数据来自飞书台账的「有效日期」列（同步后自动更新）。
            修改后先「保存配置」，再点「发送测试提醒」验证。
          </Typography.Text>
          <div>
            <Button
              icon={<SendOutlined />}
              onClick={() => void handleTestFireExpiryNotify()}
              loading={fireTesting}
            >
              发送测试提醒
            </Button>
          </div>
        </Space>
      </Card>
      <Card title="8 大作业票通知（提交/审批/验票/完工/复检催办卡片）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Switch
            checked={form.permit_notify_enabled}
            aria-label="启用作业票飞书通知"
            onChange={(checked) =>
              setForm((current) => ({
                ...current,
                permit_notify_enabled: checked,
              }))
            }
          />
          <Typography.Text type="secondary">
            启用后作业票待办节点会向指派审批人发送互动卡片（可直接同意/驳回），
            状态变化与动火/受限空间复检到期会通知相关人员；非生产环境自动推送被护栏拦截。
          </Typography.Text>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              群 chat_id
            </Button>
            <Input
              value={permitChatIdsText}
              placeholder="抄送群 chat_id，多个用英文逗号分隔（oc_ 开头）"
              onChange={(event) => setPermitChatIdsText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              个人 open_id
            </Button>
            <Input
              value={permitUserIdsText}
              placeholder="抄送个人 open_id，多个用英文逗号分隔（ou_ 开头）"
              onChange={(event) => setPermitUserIdsText(event.target.value)}
            />
          </Space.Compact>
        </Space>
      </Card>
      <Card title="特种作业证件到期提醒">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Switch
            checked={form.cert_expiry_notify_enabled}
            aria-label="启用证件到期提醒"
            onChange={(checked) =>
              setForm((current) => ({
                ...current,
                cert_expiry_notify_enabled: checked,
              }))
            }
          />
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              提醒节点
            </Button>
            <Input
              value={certMilestonesText}
              placeholder="提醒节点天数，如 30,15,7；0 表示已过期也提醒"
              onChange={(event) => setCertMilestonesText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              群 chat_id
            </Button>
            <Input
              value={certChatIdsText}
              placeholder="提醒群 chat_id，多个用英文逗号分隔（oc_ 开头）"
              onChange={(event) => setCertChatIdsText(event.target.value)}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              个人 open_id
            </Button>
            <Input
              value={certUserIdsText}
              placeholder="提醒个人 open_id，多个用英文逗号分隔（ou_ 开头）"
              onChange={(event) => setCertUserIdsText(event.target.value)}
            />
          </Space.Compact>
          <Typography.Text type="secondary">
            每天自动检查证件有效期，进入提醒节点才推送，同一证件同一节点只提醒一次。
          </Typography.Text>
        </Space>
      </Card>
      <Card title="安全承诺填报（应急〔2018〕74号 每日承诺公告）">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space size={12} wrap>
            <Typography.Text>启用每日填报推送</Typography.Text>
            <Switch
              aria-label="启用安全承诺填报推送"
              checked={form.commitment_notify_enabled}
              onChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  commitment_notify_enabled: checked,
                }))
              }
            />
            <Typography.Text type="secondary">
              到达下方推送时间后，向填报人员推送当日「企业状态 + 承诺确认」
              分步填报卡；同一自然日只推一次（非生产环境自动跳过）
            </Typography.Text>
          </Space>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 140 }}>
              推送时间
            </Button>
            <Input
              value={form.commitment_push_time}
              placeholder="每天推送时间，格式 HH:mm（如 08:30）"
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  commitment_push_time: event.target.value,
                }))
              }
            />
          </Space.Compact>
          <Space orientation="vertical" size={4} style={{ display: 'flex' }}>
            <Typography.Text>填报人员（可搜索姓名，也可直接粘贴 open_id）</Typography.Text>
            <Select
              mode="tags"
              showSearch
              style={{ width: '100%' }}
              placeholder="输入姓名搜索并选择填报人员；名单上的人员将收到每日填报卡片"
              value={form.commitment_user_ids}
              onSearch={(keyword) => void searchPersonnel(keyword)}
              onFocus={() => void searchPersonnel('')}
              options={personOptions}
              onChange={(values) =>
                setForm((current) => ({
                  ...current,
                  commitment_user_ids: values,
                }))
              }
              notFoundContent="无匹配人员（可直接粘贴 open_id 回车）"
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              仅显示已绑定飞书账号的人员；人员填写后数据自动落库到当日安全承诺日报。
            </Typography.Text>
          </Space>
          <Typography.Text type="secondary">
            修改后先「保存配置」，再点「发送测试填报卡」验证；填报人员在飞书卡片里
            提交后数据自动回填平台日报。
          </Typography.Text>
          <div>
            <Button
              icon={<SendOutlined />}
              onClick={() => void handleTestCommitment()}
              loading={commitmentTesting}
            >
              发送测试填报卡
            </Button>
          </div>
        </Space>
      </Card>
      </Space>
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
          {
            key: 'page-tables',
            label: '页面数据表映射',
            children: (
              <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
                <PlatformNotice
                  type="info"
                  title="页面 ↔ 飞书多维表格绑定"
                  description="镜像页（如「24小时值班隐患」）展示哪张飞书表在这里配置，不写死在代码里；页面列与数据来自飞书实时表结构，页面上的修改会写回该多维表格。"
                />
                <PageFeishuTableConfigCard />
              </Space>
            ),
          },
        ]}
      />
    </Space>
  )
}
