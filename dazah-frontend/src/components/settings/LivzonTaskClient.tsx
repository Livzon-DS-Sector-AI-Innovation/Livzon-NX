'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { EditOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'

import {
  cancelLivzonTaskConfirmation,
  executeLivzonTaskConfirmation,
  requestLivzonTaskTool,
} from '@/actions/livzon-task'
import {
  fetchLivzonTasks,
  fetchLivzonTaskVersions,
  type LivzonTaskItem,
  type LivzonTaskVersion,
} from '@/lib/api/agent'

const { Text, Paragraph } = Typography
const { TextArea } = Input

type TaskKind = 'automation' | 'scheduled'

type EditValues = {
  name: string
  description?: string
  cron?: string
  timezone?: string
}

type ScheduleSummary = {
  period: string
  days: string
  time: string
  repetitions: string
  valid: boolean
}

const statusMeta: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  enabled: { color: 'success', label: '已启用' },
  paused: { color: 'warning', label: '已禁用' },
  disabled: { color: 'warning', label: '已禁用' },
  suspended_policy: { color: 'error', label: '策略暂停' },
  quarantined: { color: 'error', label: '已隔离' },
  archived: { color: 'default', label: '已归档' },
}

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

function taskKindOf(item: LivzonTaskItem): TaskKind {
  return item.triggers.some((trigger) => trigger.trigger_type === 'schedule')
    ? 'scheduled'
    : 'automation'
}

function isEnabled(item: LivzonTaskItem) {
  return item.status === 'enabled'
}

function latestVersion(versions: LivzonTaskVersion[]) {
  return [...versions].sort((left, right) => right.version - left.version)[0]
}

const weekdayNames: Record<number, string> = {
  0: '周日',
  1: '周一',
  2: '周二',
  3: '周三',
  4: '周四',
  5: '周五',
  6: '周六',
  7: '周日',
}

function parseNumberList(value: string, minimum: number, maximum: number) {
  const result = new Set<number>()
  for (const part of value.split(',')) {
    if (/^\d+$/.test(part)) {
      const number = Number(part)
      if (number < minimum || number > maximum) return null
      result.add(number)
      continue
    }
    const match = part.match(/^(\d+)-(\d+)$/)
    if (!match) return null
    const start = Number(match[1])
    const end = Number(match[2])
    if (start < minimum || end > maximum || start > end) return null
    for (let number = start; number <= end; number += 1) result.add(number)
  }
  return [...result]
}

function formatWeekdays(value: string) {
  if (value === '1-5') return { label: '周一至周五（5天）', count: 5 }
  if (value === '0,6' || value === '6,0') return { label: '周六、周日（2天）', count: 2 }
  const days = parseNumberList(value, 0, 7)
  if (!days?.length) return null
  const labels = [...new Set(days.map((day) => weekdayNames[day]))]
  return { label: `${labels.join('、')}（${labels.length}天）`, count: labels.length }
}

function formatClock(hour: string, minute: string) {
  if (!/^\d+$/.test(hour) || !/^\d+$/.test(minute)) return null
  const hourNumber = Number(hour)
  const minuteNumber = Number(minute)
  if (hourNumber > 23 || minuteNumber > 59) return null
  return `${String(hourNumber).padStart(2, '0')}:${String(minuteNumber).padStart(2, '0')}`
}

function describeCron(expression?: string): ScheduleSummary {
  const fields = (expression || '').trim().split(/\s+/)
  const invalid: ScheduleSummary = {
    period: '自定义计划',
    days: '请核对 Cron',
    time: '-',
    repetitions: '-',
    valid: false,
  }
  if (fields.length !== 5) return invalid

  const [minute, hour, dayOfMonth, month, dayOfWeek] = fields
  if (month !== '*' || (dayOfMonth !== '*' && dayOfWeek !== '*')) return invalid

  const fixedTime = formatClock(hour, minute)
  const hourStep = hour.match(/^\*\/(\d+)$/)
  const minuteNumber = /^\d+$/.test(minute) ? Number(minute) : -1
  let time = fixedTime
  let runsPerDay = fixedTime ? 1 : 0
  if (!time && hourStep && minuteNumber >= 0 && minuteNumber <= 59) {
    const step = Number(hourStep[1])
    if (step < 1 || step > 23) return invalid
    time = `每${step}小时（${String(minuteNumber).padStart(2, '0')}分）`
    runsPerDay = Math.ceil(24 / step)
  }
  if (!time) return invalid

  if (dayOfMonth === '*' && dayOfWeek === '*') {
    return {
      period: '每天',
      days: '每天（1天周期）',
      time,
      repetitions: `${runsPerDay}次/天`,
      valid: true,
    }
  }

  if (dayOfMonth === '*') {
    const weekdays = formatWeekdays(dayOfWeek)
    if (!weekdays) return invalid
    return {
      period: '每周',
      days: weekdays.label,
      time,
      repetitions: `${weekdays.count * runsPerDay}次/周`,
      valid: true,
    }
  }

  const monthDays = parseNumberList(dayOfMonth, 1, 31)
  if (!monthDays?.length) return invalid
  return {
    period: '每月',
    days: `${monthDays.map((day) => `${day}日`).join('、')}（${monthDays.length}天）`,
    time,
    repetitions: `${monthDays.length * runsPerDay}次/月`,
    valid: true,
  }
}

function ScheduleDescription({ cron, timezone }: { cron?: string; timezone?: string }) {
  const summary = describeCron(cron)
  return (
    <div className="min-w-[260px] text-xs leading-5">
      <div className="font-medium text-[var(--color-text-primary)]">
        {summary.period} · {summary.days} · {summary.time}
      </div>
      <div className="text-[var(--color-text-secondary)]">
        重复 {summary.repetitions} · {timezone === 'Asia/Shanghai' ? '北京时间' : timezone || '未设置时区'}
      </div>
      <div className="font-mono text-[11px] text-[var(--color-text-tertiary)]">Cron {cron || '未配置'}</div>
    </div>
  )
}

export default function LivzonTaskClient() {
  const { message, modal } = App.useApp()
  const [items, setItems] = useState<LivzonTaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [activeKind, setActiveKind] = useState<TaskKind>('automation')
  const [detailItem, setDetailItem] = useState<LivzonTaskItem | null>(null)
  const [detailVersion, setDetailVersion] = useState<LivzonTaskVersion | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [editingItem, setEditingItem] = useState<LivzonTaskItem | null>(null)
  const [editingKind, setEditingKind] = useState<TaskKind>('automation')
  const [saving, setSaving] = useState(false)
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null)
  const [form] = Form.useForm<EditValues>()
  const editingCron = Form.useWatch('cron', form)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchLivzonTasks()
      setItems(result.items)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载 Livzon Task 失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void Promise.resolve().then(loadTasks)
  }, [loadTasks])

  const automations = useMemo(
    () => items.filter((item) => !item.legacy_source_workflow_id && taskKindOf(item) === 'automation'),
    [items],
  )
  const scheduled = useMemo(
    () => items.filter((item) => !item.legacy_source_workflow_id && taskKindOf(item) === 'scheduled'),
    [items],
  )

  const confirmToolExecution = useCallback(async (
    operation: string,
    body: Record<string, unknown>,
    successText: string,
  ) => {
    const response = await requestLivzonTaskTool({
      operation,
      body,
      params: {},
      context: { source: 'settings_livzon_task' },
      reason: '用户在系统设置的 Livzon Task 页签发起操作',
    })
    if (!response.requires_confirmation || !response.confirmation) {
      if (response.ok) {
        message.success(successText)
        await loadTasks()
      }
      return
    }
    const confirmation = response.confirmation
    modal.confirm({
      title: confirmation.summary || '确认执行 Livzon Task 操作',
      width: 520,
      okText: '确认执行',
      cancelText: '取消',
      content: (
        <div className="mt-3 space-y-2 text-[13px]">
          <div>风险等级：<Tag color="warning">{confirmation.risk_level}</Tag></div>
          <div className="text-[var(--color-text-secondary)]">请核对目标和修改内容，确认后系统才会执行。</div>
          <div className="rounded-lg bg-[var(--color-bg-secondary)] px-3 py-2 text-[var(--color-text-secondary)]">
            确认后将保存本次修改并记录审计信息。确认项将在 10 秒后失效。
          </div>
        </div>
      ),
      onOk: async () => {
        try {
          await executeLivzonTaskConfirmation(confirmation.id)
          message.success(successText)
          await loadTasks()
        } catch (error) {
          message.error(error instanceof Error ? error.message : '执行失败')
          throw error
        }
      },
      onCancel: () => cancelLivzonTaskConfirmation(confirmation.id),
    })
  }, [loadTasks, message, modal])

  const handleToggle = async (item: LivzonTaskItem) => {
    setActionLoadingId(item.id)
    try {
      await confirmToolExecution(
        'agent.set_automation_enabled',
        { automation_id: item.id, enabled: !isEnabled(item) },
        isEnabled(item) ? 'Livzon Task 已禁用' : 'Livzon Task 已启用',
      )
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleDetail = async (item: LivzonTaskItem) => {
    setDetailItem(item)
    setDetailVersion(null)
    setDetailLoading(true)
    try {
      const versions = await fetchLivzonTaskVersions(item.id)
      setDetailVersion(latestVersion(versions) || null)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleEdit = async (item: LivzonTaskItem, kind: TaskKind) => {
    setEditingItem(item)
    setEditingKind(kind)
    form.resetFields()
    try {
      const versions = await fetchLivzonTaskVersions(item.id)
      const version = latestVersion(versions)
      const definition = version?.definition || {}
      const scheduleTrigger = item.triggers.find((trigger) => trigger.trigger_type === 'schedule')
      form.setFieldsValue({
        name: String(definition.name || item.name),
        description: String(definition.description || item.description || ''),
        cron: String(scheduleTrigger?.schedule?.cron || ''),
        timezone: scheduleTrigger?.timezone || 'Asia/Shanghai',
      })
      setDetailVersion(version || null)
    } catch (error) {
      setEditingItem(null)
      message.error(error instanceof Error ? error.message : '加载修改数据失败')
    }
  }

  const handleSave = async () => {
    if (!editingItem) return
    try {
      const values = await form.validateFields()
      setSaving(true)
      const versions = await fetchLivzonTaskVersions(editingItem.id)
      const definition = { ...(latestVersion(versions)?.definition || {}) }
      definition.name = values.name
      definition.description = values.description || null
      const body: Record<string, unknown> = {
        automation_id: editingItem.id,
        definition,
        change_summary: editingKind === 'scheduled' ? '在 Livzon Task 中修改定时任务' : '在 Livzon Task 中修改自动化',
      }
      if (editingKind === 'scheduled') {
          const scheduledTrigger = editingItem.triggers.find(
            (trigger) => trigger.trigger_type === 'schedule',
          )
          body.triggers = editingItem.triggers.map((trigger) => (
            trigger.id === scheduledTrigger?.id
              ? {
                  trigger_type: trigger.trigger_type,
                  schedule: { cron: values.cron },
                  event_type: trigger.event_type,
                  event_filter: trigger.event_filter || {},
                  timezone: values.timezone || 'Asia/Shanghai',
                }
              : {
                  trigger_type: trigger.trigger_type,
                  schedule: trigger.schedule,
                  event_type: trigger.event_type,
                  event_filter: trigger.event_filter || {},
                  timezone: trigger.timezone,
                }
          ))
      }
      await confirmToolExecution('agent.update_automation', body, editingKind === 'scheduled' ? '定时任务已修改' : '自动化已修改')
      setEditingItem(null)
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSaving(false)
    }
  }

  const columns: TableColumnsType<LivzonTaskItem> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 260,
      render: (value: string, record) => (
        <div className="min-w-0">
          <div className="font-medium text-[var(--color-text-primary)]">{value}</div>
          <div className="mt-0.5 line-clamp-1 text-xs text-[var(--color-text-tertiary)]">
            {record.description || '暂无说明'}
          </div>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (value: string) => {
        const meta = statusMeta[value] || { color: 'default', label: value }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: activeKind === 'scheduled' ? '执行计划' : '触发方式',
      key: 'trigger',
      width: activeKind === 'scheduled' ? 330 : 220,
      render: (_, record) => {
        const schedule = record.triggers.find((trigger) => trigger.trigger_type === 'schedule')
        if (schedule) {
          return <ScheduleDescription cron={String(schedule.schedule.cron || '')} timezone={schedule.timezone} />
        }
        return <Text type="secondary">{record.triggers.map((item) => item.trigger_type).join('、') || '手动'}</Text>
      },
    },
    {
      title: '最近运行',
      key: 'lastRun',
      width: 170,
      render: (_, record) => (
        <div>
          <div>{record.last_run_status || '暂无运行'}</div>
          <div className="text-xs text-[var(--color-text-tertiary)]">{formatTime(record.last_run_at)}</div>
        </div>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updatedAt',
      width: 170,
      render: formatTime,
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 220,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => void handleDetail(record)}>
            详情
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            disabled={record.status === 'archived'}
            onClick={() => void handleEdit(record, activeKind)}
          >
            修改
          </Button>
          <Button
            type="link"
            size="small"
            danger={isEnabled(record)}
            disabled={record.status === 'archived'}
            loading={actionLoadingId === record.id}
            onClick={() => void handleToggle(record)}
          >
            {isEnabled(record) ? '禁用' : '启用'}
          </Button>
        </Space>
      ),
    },
  ]

  const table = (data: LivzonTaskItem[]) => (
    <Table
      rowKey="id"
      loading={loading}
      columns={columns}
      dataSource={data}
      scroll={{ x: 1080 }}
      pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 项` }}
      locale={{ emptyText: '暂无 Livzon Task' }}
    />
  )

  return (
    <section aria-label="Livzon Task 管理">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-[var(--color-text-primary)]">Livzon Task</div>
          <Paragraph className="!mb-0 !mt-1 !text-[13px]" type="secondary">
            管理由 Livzon 助手创建的自动化流程和定时任务。含时间触发的流程统一归入定时任务。
          </Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadTasks()}>
          刷新
        </Button>
      </div>

      <Tabs
        activeKey={activeKind}
        onChange={(key) => setActiveKind(key as TaskKind)}
        items={[
          { key: 'automation', label: `自动化流程 ${automations.length}`, children: table(automations) },
          { key: 'scheduled', label: `定时任务 ${scheduled.length}`, children: table(scheduled) },
        ]}
      />

      <Drawer
        title="Livzon Task 详情"
        width={680}
        open={Boolean(detailItem)}
        loading={detailLoading}
        onClose={() => setDetailItem(null)}
      >
        {detailItem && (
          <div className="space-y-5">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="名称">{detailItem.name}</Descriptions.Item>
              <Descriptions.Item label="说明">{detailItem.description || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">{statusMeta[detailItem.status]?.label || detailItem.status}</Descriptions.Item>
              <Descriptions.Item label="类型">{taskKindOf(detailItem) === 'scheduled' ? '定时任务' : '自动化流程'}</Descriptions.Item>
              <Descriptions.Item label="最近运行">{detailItem.last_run_status || '-'}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{formatTime(detailItem.updated_at)}</Descriptions.Item>
              {detailItem.triggers
                .filter((trigger) => trigger.trigger_type === 'schedule')
                .map((trigger) => (
                  <Descriptions.Item key={trigger.id} label="执行计划">
                    <ScheduleDescription
                      cron={String(trigger.schedule.cron || '')}
                      timezone={trigger.timezone}
                    />
                  </Descriptions.Item>
                ))}
            </Descriptions>
            <div>
              <div className="mb-2 text-sm font-medium">触发配置</div>
              <pre className="max-h-64 overflow-auto rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs leading-5">
                {JSON.stringify(detailItem.triggers, null, 2)}
              </pre>
            </div>
            <div>
              <div className="mb-2 text-sm font-medium">流程定义</div>
              <pre className="max-h-80 overflow-auto rounded-lg bg-[var(--color-bg-secondary)] p-3 text-xs leading-5">
                {JSON.stringify(detailVersion?.definition || {}, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </Drawer>

      <Modal
        title={editingKind === 'scheduled' ? '修改定时任务' : '修改自动化流程'}
        width={680}
        open={Boolean(editingItem)}
        okText="提交修改"
        cancelText="取消"
        confirmLoading={saving}
        onOk={() => void handleSave()}
        onCancel={() => setEditingItem(null)}
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <TextArea rows={3} maxLength={4000} showCount />
          </Form.Item>
          {editingKind === 'scheduled' && (
            <>
              <Form.Item
                name="cron"
                label="执行规则（Cron）"
                extra="五段格式：分钟 小时 日期 月份 星期，例如 0 9 * * 1-5"
                rules={[{ required: true, message: '请输入 Cron 表达式' }]}
              >
                <Input className="font-mono" placeholder="0 9 * * 1-5" />
              </Form.Item>
              {editingCron && (
                <div className="mb-5 rounded-lg bg-[var(--color-bg-secondary)] px-4 py-3">
                  <div className="mb-1 text-xs font-medium text-[var(--color-text-secondary)]">计划预览</div>
                  <ScheduleDescription cron={editingCron} timezone={form.getFieldValue('timezone')} />
                </div>
              )}
              <Form.Item name="timezone" label="时区" rules={[{ required: true, message: '请输入时区' }]}>
                <Input placeholder="Asia/Shanghai" />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </section>
  )
}
