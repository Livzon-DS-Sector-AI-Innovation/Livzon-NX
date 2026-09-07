'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Alert, Button, Card, InputNumber, Select, Space, Switch, TimePicker, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

import {
  fetchQualityNotificationSettings,
  updateQualityNotificationSetting,
} from '@/actions/quality'
import { searchChangeActionPlanPersons } from '@/lib/api/client/quality'
import type {
  QualityNotificationRecipient,
  QualityNotificationSettingItem,
} from '@/types/quality'

const CHANGE_ACTION_PLAN_DUE = 'change_action_plan_due'
const INSPECTION_TREND_ALERT = 'inspection_trend_alert'

type RecipientOption = {
  label: string
  value: string
  name: string
}

function toOptions(recipients: QualityNotificationRecipient[]): RecipientOption[] {
  return recipients
    .filter((item) => item.open_id)
    .map((item) => ({
      label: item.name || String(item.open_id),
      value: String(item.open_id),
      name: item.name,
    }))
}

function mergeOptions(
  base: RecipientOption[],
  extra: RecipientOption[]
): RecipientOption[] {
  const merged = new Map(base.map((option) => [option.value, option]))
  for (const option of extra) {
    if (!merged.has(option.value)) merged.set(option.value, option)
  }
  return Array.from(merged.values())
}

function RecipientSelect({
  value,
  onChange,
  placeholder,
  style,
}: {
  value: QualityNotificationRecipient[]
  onChange: (next: QualityNotificationRecipient[]) => void
  placeholder?: string
  style?: React.CSSProperties
}) {
  const [searchedOptions, setSearchedOptions] = useState<RecipientOption[]>([])
  const [searching, setSearching] = useState(false)
  const timerRef = useRef<number | null>(null)

  // 回填值 + 搜索结果合并为选项；回填值始终参与合并以保证回显有名称
  const options = useMemo(
    () => mergeOptions(toOptions(value), searchedOptions),
    [value, searchedOptions]
  )

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
    }
  }, [])

  const handleSearch = useCallback((rawKeyword: string) => {
    const keyword = rawKeyword.trim()
    if (timerRef.current) window.clearTimeout(timerRef.current)
    if (!keyword) {
      setSearching(false)
      return
    }
    setSearching(true)
    timerRef.current = window.setTimeout(async () => {
      try {
        const people = await searchChangeActionPlanPersons(keyword)
        const fetched = people
          .filter((person) => person.open_id)
          .map((person) => ({
            label: person.name,
            value: person.open_id,
            name: person.name,
          }))
        setSearchedOptions((prev) => mergeOptions(prev, fetched))
      } catch {
        // 搜索失败时保留既有选项
      } finally {
        setSearching(false)
      }
    }, 250)
  }, [])

  const selected = value
    .map((item) => item.open_id)
    .filter((openId): openId is string => Boolean(openId))

  return (
    <Select
      mode="multiple"
      allowClear
      showSearch
      filterOption={false}
      labelInValue
      loading={searching}
      placeholder={placeholder ?? '搜索飞书用户姓名'}
      style={style}
      value={selected.map((openId) => {
        const known = options.find((option) => option.value === openId)
        return { value: openId, label: known?.name ?? openId }
      })}
      options={options}
      onSearch={handleSearch}
      onChange={(
        _,
        optionList: RecipientOption | RecipientOption[] | undefined
      ) => {
        const list = Array.isArray(optionList) ? optionList : optionList ? [optionList] : []
        onChange(
          list.map((option) => ({ open_id: option.value, name: option.name }))
        )
      }}
    />
  )
}

function ChangeActionPlanDueCard({
  setting,
  onSaved,
}: {
  setting: QualityNotificationSettingItem
  onSaved: (next: QualityNotificationSettingItem) => void
}) {
  const { message } = App.useApp()
  const [enabled, setEnabled] = useState(setting.is_enabled)
  const [leadDays, setLeadDays] = useState<number>(setting.lead_days)
  const [repeatIntervalDays, setRepeatIntervalDays] = useState<number>(
    setting.repeat_interval_days
  )
  const [sendTime, setSendTime] = useState<Dayjs>(dayjs(setting.send_time, 'HH:mm'))
  const [fallbackRecipients, setFallbackRecipients] = useState<
    QualityNotificationRecipient[]
  >(setting.fallback_recipients)
  const [saving, setSaving] = useState(false)

  // setting 变更（保存回写）由父组件通过 key 重挂载同步，无需 effect

  const handleSave = async () => {
    if (!sendTime) {
      message.warning('请选择每天发送时间')
      return
    }
    setSaving(true)
    try {
      const next = await updateQualityNotificationSetting(CHANGE_ACTION_PLAN_DUE, {
        is_enabled: enabled,
        lead_days: leadDays,
        repeat_interval_days: repeatIntervalDays,
        send_time: sendTime.format('HH:mm'),
        fallback_recipients: fallbackRecipients,
      })
      onSaved(next)
      message.success('变更计划到期提醒设置已保存')
    } catch (error) {
      message.error(
        `保存失败：${error instanceof Error ? error.message : '未知错误'}`
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card
      title="变更计划到期提醒"
      extra={
        <Space>
          <Switch checked={enabled} onChange={setEnabled} />
          <Button type="primary" loading={saving} onClick={() => void handleSave()}>
            保存
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
        <Typography.Text type="secondary">
          到期前自动向变更计划的负责人（负责人未填时向部门负责人）发送飞书卡片提醒，确认后停止提醒。
        </Typography.Text>
        <Space wrap size={24}>
          <Space size={8}>
            <Typography.Text>提前</Typography.Text>
            <InputNumber
              min={0}
              max={365}
              value={leadDays}
              onChange={(next) => setLeadDays(Number(next ?? 3))}
              suffix="天"
              style={{ width: 130 }}
            />
            <Typography.Text type="secondary">进入提醒窗口</Typography.Text>
          </Space>
          <Space size={8}>
            <Typography.Text>重复间隔</Typography.Text>
            <InputNumber
              min={1}
              max={30}
              value={repeatIntervalDays}
              onChange={(next) => setRepeatIntervalDays(Number(next ?? 1))}
              suffix="天"
              style={{ width: 130 }}
            />
            <Typography.Text type="secondary">未确认时再次提醒</Typography.Text>
          </Space>
          <Space size={8}>
            <Typography.Text>每天发送时间</Typography.Text>
            <TimePicker
              format="HH:mm"
              value={sendTime}
              onChange={(next) => next && setSendTime(next)}
            />
          </Space>
        </Space>
        <Space orientation="vertical" size={4} style={{ display: 'flex' }}>
          <Typography.Text>兜底接收人（计划未填负责人与部门负责人时发送给他们）</Typography.Text>
          <RecipientSelect
            value={fallbackRecipients}
            onChange={setFallbackRecipients}
            style={{ width: '100%', maxWidth: 520 }}
          />
        </Space>
      </Space>
    </Card>
  )
}

function InspectionTrendAlertCard({
  setting,
  onSaved,
}: {
  setting: QualityNotificationSettingItem
  onSaved: (next: QualityNotificationSettingItem) => void
}) {
  const { message } = App.useApp()
  const [enabled, setEnabled] = useState(setting.is_enabled)
  const [lines, setLines] = useState(setting.inspection_lines)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      const next = await updateQualityNotificationSetting(INSPECTION_TREND_ALERT, {
        is_enabled: enabled,
        inspection_lines: lines.map((line) => ({
          entity_code: line.entity_code,
          enabled: line.enabled,
          recipients: line.recipients,
        })),
      })
      onSaved(next)
      message.success('成品检验趋势异常提醒设置已保存')
    } catch (error) {
      message.error(
        `保存失败：${error instanceof Error ? error.message : '未知错误'}`
      )
    } finally {
      setSaving(false)
    }
  }

  const updateLine = (
    entityCode: string,
    patch: Partial<(typeof lines)[number]>
  ) => {
    setLines((prev) =>
      prev.map((line) =>
        line.entity_code === entityCode ? { ...line, ...patch } : line
      )
    )
  }

  return (
    <Card
      title="成品检验趋势异常提醒"
      extra={
        <Space>
          <Typography.Text type="secondary">总开关</Typography.Text>
          <Switch checked={enabled} onChange={setEnabled} />
          <Button type="primary" loading={saving} onClick={() => void handleSave()}>
            保存
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
        <Typography.Text type="secondary">
          打开趋势仪表盘时，检验值超出控制限/限度线的批次会自动发飞书卡片。关闭某条产品线后该线不再发送；启用但未配置接收人的产品线沿用系统默认通知对象。
        </Typography.Text>
        {!enabled ? (
          <Alert type="warning" showIcon title="总开关已关闭，所有产品线均不会发送提醒" />
        ) : null}
        <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
          {lines.map((line) => (
            <Space
              key={line.entity_code}
              wrap
              size={12}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '6px 8px',
                background: '#fafafa',
                borderRadius: 8,
              }}
            >
              <Switch
                size="small"
                checked={line.enabled}
                onChange={(next) => updateLine(line.entity_code, { enabled: next })}
              />
              <Typography.Text style={{ minWidth: 150, display: 'inline-block' }}>
                {line.entity_label || line.entity_code}
              </Typography.Text>
              <RecipientSelect
                value={line.recipients}
                onChange={(next) =>
                  updateLine(line.entity_code, { recipients: next })
                }
                placeholder="搜索接收人（不填走系统默认）"
                style={{ minWidth: 280, flex: 1, maxWidth: 460 }}
              />
            </Space>
          ))}
        </Space>
      </Space>
    </Card>
  )
}

export function QualityNotificationSettingsPanel() {
  const queryClient = useQueryClient()
  const settingsQuery = useQuery<QualityNotificationSettingItem[]>({
    queryKey: ['quality-notification-settings'],
    queryFn: fetchQualityNotificationSettings,
  })

  const settings = settingsQuery.data ?? []
  const changeItem = settings.find(
    (item) => item.notification_type === CHANGE_ACTION_PLAN_DUE
  )
  const inspectionItem = settings.find(
    (item) => item.notification_type === INSPECTION_TREND_ALERT
  )

  const handleSaved = (next: QualityNotificationSettingItem) => {
    queryClient.setQueryData<QualityNotificationSettingItem[]>(
      ['quality-notification-settings'],
      (prev) =>
        (prev ?? []).map((item) =>
          item.notification_type === next.notification_type ? next : item
        )
    )
  }

  if (settingsQuery.isLoading) {
    return <Card loading title="通知设置" />
  }

  if (settingsQuery.isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="通知设置加载失败"
        description={
          settingsQuery.error instanceof Error
            ? settingsQuery.error.message
            : '未知错误'
        }
      />
    )
  }

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      {changeItem ? (
        <ChangeActionPlanDueCard
          key={JSON.stringify(changeItem)}
          setting={changeItem}
          onSaved={handleSaved}
        />
      ) : null}
      {inspectionItem ? (
        <InspectionTrendAlertCard
          key={JSON.stringify(inspectionItem)}
          setting={inspectionItem}
          onSaved={handleSaved}
        />
      ) : null}
    </Space>
  )
}

export default QualityNotificationSettingsPanel
