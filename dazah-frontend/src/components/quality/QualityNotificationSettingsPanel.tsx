'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Alert, Button, Card, Input, InputNumber, Select, Space, Switch, TimePicker, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'

import {
  fetchQualityNotificationSettings,
  updateQualityNotificationSetting,
} from '@/actions/quality'
import { pushItemsLowStockTest } from '@/actions/quality-inspection'
import { searchChangeActionPlanPersons, fetchQaPersonOptions } from '@/lib/api/client/quality'
import type {
  QualityNotificationRecipient,
  QualityNotificationSettingItem,
} from '@/types/quality'

const CHANGE_ACTION_PLAN_DUE = 'change_action_plan_due'
const INSPECTION_TREND_ALERT = 'inspection_trend_alert'
const INSPECTION_TREND_ALERT_ESCALATION = 'inspection_trend_alert_escalation'
const ITEMS_STOCK_ALERT = 'items_stock_alert'

type RecipientOption = {
  label: string
  value: string
  name: string
}

// 无 open_id 的历史收件人（仅姓名）也要回显：value 用姓名伪键，避免选择器显示为空
function recipientKey(item: QualityNotificationRecipient): string {
  return item.open_id ? String(item.open_id) : `name:${item.name}`
}

function toOptions(recipients: QualityNotificationRecipient[]): RecipientOption[] {
  return recipients.map((item) => ({
    label: item.name || String(item.open_id),
    value: recipientKey(item),
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
  preloadOptions,
}: {
  value: QualityNotificationRecipient[]
  onChange: (next: QualityNotificationRecipient[]) => void
  placeholder?: string
  style?: React.CSSProperties
  /** 预载候选（如 QA 部门人员），与搜索结果合并 */
  preloadOptions?: RecipientOption[]
}) {
  const [searchedOptions, setSearchedOptions] = useState<RecipientOption[]>([])
  const [searching, setSearching] = useState(false)
  const timerRef = useRef<number | null>(null)

  // 回填值 + 预载候选 + 搜索结果合并为选项；回填值始终参与合并以保证回显有名称
  const options = useMemo(
    () =>
      mergeOptions(
        mergeOptions(toOptions(value), preloadOptions ?? []),
        searchedOptions
      ),
    [value, preloadOptions, searchedOptions]
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

  const selected = value.map(recipientKey)

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
      value={selected.map((key) => {
        const known = options.find((option) => option.value === key)
        return { value: key, label: known?.name ?? key.replace(/^name:/, '') }
      })}
      options={options}
      onSearch={handleSearch}
      onChange={(
        _,
        optionList: RecipientOption | RecipientOption[] | undefined
      ) => {
        const list = Array.isArray(optionList) ? optionList : optionList ? [optionList] : []
        // 按唯一键（open_id / 姓名伪键）保留每一项；同名时"仅姓名"项让位于带 open_id 项，
        // 既避免历史姓名标签与搜索重选并存，又不吞同名不同人
        const byId = new Map<string, QualityNotificationRecipient>()
        const nameOnly: QualityNotificationRecipient[] = []
        for (const option of list) {
          if (option.value.startsWith('name:')) {
            nameOnly.push({ open_id: null, name: option.name })
          } else {
            byId.set(option.value, { open_id: option.value, name: option.name })
          }
        }
        const named = new Set(
          Array.from(byId.values())
            .map((item) => item.name)
            .filter(Boolean)
        )
        for (const item of nameOnly) {
          if (item.name && named.has(item.name)) continue
          byId.set(`name:${item.name}`, item)
        }
        onChange(Array.from(byId.values()))
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
  const [monthlyDay, setMonthlyDay] = useState<number | null>(
    setting.monthly_day ?? 25
  )
  const [manualRerunSend, setManualRerunSend] = useState<boolean>(
    setting.manual_rerun_send ?? true
  )
  // QA 部门人员预载候选（产品QA 默认可直接选）
  const [qaOptions, setQaOptions] = useState<RecipientOption[]>([])
  useEffect(() => {
    let cancelled = false
    fetchQaPersonOptions()
      .then((people) => {
        if (cancelled) return
        setQaOptions(
          people
            .filter((person) => person.open_id)
            .map((person) => ({
              label: person.name,
              value: person.open_id,
              name: person.name,
            }))
        )
      })
      .catch(() => {
        // 预载失败不影响手填/搜索
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleSave = async () => {
    if (!monthlyDay || monthlyDay < 1 || monthlyDay > 31) {
      message.warning('请填写月度分析日（1-31，月底不足则取当月最后一天）')
      return
    }
    setSaving(true)
    try {
      const next = await updateQualityNotificationSetting(INSPECTION_TREND_ALERT, {
        is_enabled: enabled,
        monthly_day: monthlyDay,
        manual_rerun_send: manualRerunSend,
        inspection_lines: lines.map((line) => ({
          entity_code: line.entity_code,
          enabled: line.enabled,
          recipients: line.recipients,
          qa_recipients: line.qa_recipients ?? [],
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
          <Space wrap size={12} style={{ display: 'flex', alignItems: 'center' }}>
            <Typography.Text>趋势 AI 月度分析</Typography.Text>
            <Typography.Text type="secondary">每月</Typography.Text>
            <InputNumber
              min={1}
              max={31}
              value={monthlyDay}
              onChange={(value) => setMonthlyDay(value ?? null)}
              style={{ width: 90 }}
            />
            <Typography.Text type="secondary">日全量分析并发送（月底不足则当月最后一天）</Typography.Text>
            <Typography.Text type="secondary">手动重新分析发送消息</Typography.Text>
            <Switch checked={manualRerunSend} onChange={setManualRerunSend} />
          </Space>
          <Typography.Text type="secondary">
            打开趋势仪表盘时，检验值超出控制限/限度线的批次会自动发飞书卡片。关闭某条产品线后该线不再发送；启用但未配置接收人的产品线沿用系统默认通知对象。每条产品线可单独设置「产品QA」（候选默认为
            QA 部门人员，可搜索替换），QA 将与接收人一并收到通知。
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
                style={{ minWidth: 280, flex: 1, maxWidth: 400 }}
              />
              <Typography.Text type="secondary">产品QA</Typography.Text>
              <RecipientSelect
                value={line.qa_recipients ?? []}
                onChange={(next) =>
                  updateLine(line.entity_code, { qa_recipients: next })
                }
                placeholder="QA 部门人员（可搜索）"
                style={{ minWidth: 240, flex: 1, maxWidth: 360 }}
                preloadOptions={qaOptions}
              />
            </Space>
          ))}
        </Space>
      </Space>
    </Card>
  )
}

function AnomalyEscalationCard({
  setting,
  onSaved,
}: {
  setting: QualityNotificationSettingItem
  onSaved: (next: QualityNotificationSettingItem) => void
}) {
  const { message } = App.useApp()
  const [enabled, setEnabled] = useState(setting.is_enabled)
  const [firstRecipients, setFirstRecipients] = useState(
    setting.first_recipients ?? []
  )
  const [escalationHours, setEscalationHours] = useState<number | null>(
    setting.escalation_hours ?? 2
  )
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!escalationHours || escalationHours < 1) {
      message.warning('请填写升级复检间隔（≥1 小时）')
      return
    }
    if (!firstRecipients.length) {
      message.warning('请至少选择一位首推接收人')
      return
    }
    setSaving(true)
    try {
      const next = await updateQualityNotificationSetting(
        INSPECTION_TREND_ALERT_ESCALATION,
        {
          is_enabled: enabled,
          first_recipients: firstRecipients,
          escalation_hours: escalationHours,
        }
      )
      onSaved(next)
      message.success('成品/纯化水异常升级推送设置已保存')
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
      title="成品/纯化水异常升级推送"
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
          成品与纯化水页面的异常消息：首波推送给产品线收件人和下方首推接收人；发生
          {' '}
          {escalationHours ?? 2}{' '}
          小时后系统自动复检，若仍异常则升级推送各部门负责人（提炼部门负责人 +
          该产品QA），已恢复正常则自动取消，不会重复打扰。
        </Typography.Text>
        {!enabled ? (
          <Alert type="warning" showIcon title="总开关已关闭，异常不再升级推送" />
        ) : null}
        <Space wrap size={12} style={{ display: 'flex', alignItems: 'center' }}>
          <Typography.Text>首推接收人</Typography.Text>
          <RecipientSelect
            value={firstRecipients}
            onChange={setFirstRecipients}
            placeholder="搜索首推接收人（默认李文昊）"
            style={{ minWidth: 280 }}
          />
          <Typography.Text>复检间隔（小时）</Typography.Text>
          <InputNumber
            min={1}
            max={72}
            value={escalationHours}
            onChange={(value) => setEscalationHours(value ?? null)}
            style={{ width: 100 }}
          />
        </Space>
      </Space>
    </Card>
  )
}

function ItemsStockAlertCard({
  setting,
  onSaved,
}: {
  setting: QualityNotificationSettingItem
  onSaved: (next: QualityNotificationSettingItem) => void
}) {
  const { message } = App.useApp()
  const [enabled, setEnabled] = useState(setting.is_enabled)
  const [recipients, setRecipients] = useState<QualityNotificationRecipient[]>(
    setting.stock_recipients ?? []
  )
  const [warningSource, setWarningSource] = useState(
    setting.stock_warning_source ?? 'feishu'
  )
  const [headerTemplate, setHeaderTemplate] = useState(
    setting.stock_header_template ?? ''
  )
  const [footerTemplate, setFooterTemplate] = useState(
    setting.stock_footer_template ?? ''
  )
  const [sendTime, setSendTime] = useState<Dayjs>(
    dayjs(setting.send_time || '09:00', 'HH:mm')
  )
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const handleSave = async () => {
    if (enabled && recipients.length === 0) {
      message.warning('开启定时推送时请至少选择一位接收人')
      return
    }
    setSaving(true)
    try {
      const next = await updateQualityNotificationSetting(ITEMS_STOCK_ALERT, {
        is_enabled: enabled,
        send_time: sendTime.format('HH:mm'),
        stock_recipients: recipients,
        stock_warning_source: warningSource,
        stock_header_template: headerTemplate || null,
        stock_footer_template: footerTemplate || null,
      })
      onSaved(next)
      message.success('物品库存不足预警推送设置已保存')
    } catch (error) {
      message.error(`保存失败：${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const result = await pushItemsLowStockTest()
      if (result.status === 'no_data') message.info('当前没有库存不足的物料，未发送测试')
      else if (result.status === 'unmapped') message.warning(result.message || '未配置有效接收人')
      else message.success(`测试推送完成：成功 ${result.sent} 位`)
    } catch (error) {
      message.error(`测试失败：${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card
      title="物品库存不足预警推送"
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
      <Space direction="vertical" size={12} style={{ display: 'flex' }}>
        <Typography.Text type="secondary">
          定时（每天到点）+ 手动（物品管理页「推送库存不足」按钮）向接收人推送库存不足物料清单。
          文案支持 {'{date}'} {'{count}'} 占位符。
        </Typography.Text>
        <Space wrap size={12} style={{ display: 'flex', alignItems: 'center' }}>
          <Typography.Text>接收人</Typography.Text>
          <RecipientSelect
            value={recipients}
            onChange={setRecipients}
            placeholder="搜索接收人（人事-飞书联系人）"
            style={{ minWidth: 280 }}
          />
          <Typography.Text>判定口径</Typography.Text>
          <Select
            value={warningSource}
            onChange={setWarningSource}
            style={{ width: 220 }}
            options={[
              { label: '飞书「库存报警」列', value: 'feishu' },
              { label: '当前库存 ≤ 警戒库存', value: 'local_threshold' },
            ]}
          />
          <Typography.Text>发送时间</Typography.Text>
          <TimePicker
            format="HH:mm"
            value={sendTime}
            onChange={(value) => value && setSendTime(value)}
            allowClear={false}
          />
        </Space>
        <Space wrap size={12} style={{ display: 'flex' }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <Typography.Text>抬头文案</Typography.Text>
            <Input.TextArea
              rows={2}
              value={headerTemplate}
              placeholder="留空使用默认：物品库存不足预警（{date}）"
              onChange={(e) => setHeaderTemplate(e.target.value)}
            />
          </div>
          <div style={{ flex: 1, minWidth: 260 }}>
            <Typography.Text>结尾文案</Typography.Text>
            <Input.TextArea
              rows={2}
              value={footerTemplate}
              placeholder="留空使用默认：共 {count} 种物资库存不足…"
              onChange={(e) => setFooterTemplate(e.target.value)}
            />
          </div>
        </Space>
        <Button loading={testing} onClick={() => void handleTest()}>
          发送测试推送
        </Button>
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
  const escalationItem = settings.find(
    (item) => item.notification_type === INSPECTION_TREND_ALERT_ESCALATION
  )
  const stockAlertItem = settings.find(
    (item) => item.notification_type === ITEMS_STOCK_ALERT
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
      {escalationItem ? (
        <AnomalyEscalationCard
          key={JSON.stringify(escalationItem)}
          setting={escalationItem}
          onSaved={handleSaved}
        />
      ) : null}
      {stockAlertItem ? (
        <ItemsStockAlertCard
          key={JSON.stringify(stockAlertItem)}
          setting={stockAlertItem}
          onSaved={handleSaved}
        />
      ) : null}
    </Space>
  )
}

export default QualityNotificationSettingsPanel
