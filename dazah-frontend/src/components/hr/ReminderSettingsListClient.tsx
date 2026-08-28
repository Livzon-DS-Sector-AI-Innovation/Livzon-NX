'use client'

import { useEffect, useState, useMemo } from 'react'
import { App, Card, Collapse, Switch, Button, Space, Tag, Typography } from 'antd'
import { SettingOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import { fetchReminderConfigs, type ReminderConfigVM as ReminderConfig } from '@/lib/api/client/hr'
import { updateReminderConfig } from '@/actions/hr'

export default function ReminderSettingsListClient() {
  const { message } = App.useApp()
  const router = useRouter()
  const [configs, setConfigs] = useState<ReminderConfig[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    (async () => {
      setLoading(true)
      try {
        const data = await fetchReminderConfigs()
        setConfigs(data || [])
      } catch { message.error('加载失败') }
      finally { setLoading(false) }
    })()
  }, [message])

  const grouped = useMemo(() => {
    const groups: Record<string, ReminderConfig[]> = {}
    for (const c of configs) {
      if (!groups[c.module_group]) groups[c.module_group] = []
      groups[c.module_group].push(c)
    }
    return Object.entries(groups)
  }, [configs])

  const handleToggle = async (config: ReminderConfig, enabled: boolean) => {
    try {
      await updateReminderConfig(config.id, {
        reminder_days: config.reminder_days,
        recipient_open_ids: config.recipient_open_ids,
        dept_notify_enabled: config.dept_notify_enabled,
        trigger_frequency: config.trigger_frequency,
        trigger_day: config.trigger_day,
        trigger_hour: config.trigger_hour,
        is_enabled: enabled,
      })
      setConfigs(configs.map(c => c.id === config.id ? { ...c, is_enabled: enabled } : c))
    } catch { message.error('操作失败') }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-[22px] font-semibold">提醒设置</h1>
      <Card loading={loading}>
        <Collapse
          defaultActiveKey={grouped.map(([g]) => g)}
          items={grouped.map(([group, items]) => ({
            key: group,
            label: <Space><Typography.Text strong>{group}</Typography.Text><Tag color="blue">{items.length}</Tag></Space>,
            children: (
              <div className="space-y-2">
                {items.map(c => (
                  <div key={c.id} className="flex items-center justify-between py-2 px-3 rounded" style={{ background: '#fafafa' }}>
                    <Space>
                      <Typography.Text>{c.reminder_label}</Typography.Text>
                      {c.reminder_days && c.reminder_days.length > 0 && <Tag>{c.reminder_days.join('/')}天</Tag>}
                    </Space>
                    <Space>
                      <Switch checked={c.is_enabled} onChange={(v) => handleToggle(c, v)} />
                      <Button size="small" icon={<SettingOutlined />} onClick={() => router.push(`/hr/settings/reminder/${c.entity_code}`)}>配置</Button>
                    </Space>
                  </div>
                ))}
              </div>
            ),
          }))}
        />
      </Card>
    </div>
  )
}
