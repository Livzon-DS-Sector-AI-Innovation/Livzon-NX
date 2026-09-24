'use client'

import dayjs from 'dayjs'
import { Space, Tag } from 'antd'
import { ClockCircleOutlined } from '@ant-design/icons'
import type { WarehouseInspectionCycle } from '@/types/warehouse'

// ── 检验进度周期（只读统计，详情弹窗展示） ────────────────────
// 台账页记录详情弹窗与仪表盘检验进度面板共用。
export const INSPECTION_CYCLE_STATUS_COLORS: Record<string, string> = {
  completed: 'green',
  pending: 'gold',
  not_counted: 'default',
  not_applicable: 'default',
  no_data: 'default',
}

export function formatInspectionHours(hours?: number | null): string {
  if (hours == null) {
    return '—'
  }
  if (hours < 48) {
    return `${hours.toFixed(1)} 小时`
  }
  return `${(hours / 24).toFixed(1)} 天（${Math.round(hours)} 小时）`
}

export function formatInspectionTime(value?: string | null): string {
  if (!value) {
    return '—'
  }
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : String(value)
}

export function renderInspectionCycleBlock(cycle?: WarehouseInspectionCycle | null) {
  if (!cycle) {
    return null
  }
  return (
    <div className="mt-3 rounded-lg border border-[var(--color-hairline)] bg-white p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <ClockCircleOutlined className="text-[var(--color-primary)]" />
        <span className="text-[13px] font-semibold text-[var(--color-charcoal)]">
          检验进度周期
        </span>
        <Tag color="default">只读统计</Tag>
        <Tag color={INSPECTION_CYCLE_STATUS_COLORS[cycle.status] ?? 'default'}>
          {cycle.status_label}
        </Tag>
        {cycle.result ? (
          <Tag color={cycle.result === '合格' ? 'green' : 'red'}>{cycle.result}</Tag>
        ) : null}
      </div>
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--color-steel)]">
          <span>入库日期：{cycle.inbound_date ?? '—'}</span>
          {cycle.pending_since ? (
            <span>待验开始：{formatInspectionTime(cycle.pending_since)}</span>
          ) : null}
          {cycle.result_at ? (
            <span>出结果时间：{formatInspectionTime(cycle.result_at)}</span>
          ) : null}
          <span className="font-semibold text-[var(--color-charcoal)]">
            总时长：{formatInspectionHours(cycle.total_hours)}
          </span>
        </div>
        {cycle.stages.length > 0 ? (
          <div className="flex flex-col gap-1">
            {cycle.stages.map((stage) => (
              <div
                key={stage.label}
                className="flex items-center justify-between rounded border border-dashed border-[var(--color-hairline)] px-2.5 py-1 text-[12px]"
              >
                <span className="text-[var(--color-steel)]">{stage.label}</span>
                <Space size={8}>
                  <span className="text-[var(--color-muted)]">
                    {formatInspectionTime(stage.from_at)} → {formatInspectionTime(stage.to_at)}
                  </span>
                  <span className="font-semibold text-[var(--color-primary)]">
                    {formatInspectionHours(stage.hours)}
                  </span>
                </Space>
              </div>
            ))}
          </div>
        ) : null}
        {cycle.note ? (
          <div className="text-[11px] text-[var(--color-muted)]">{cycle.note}</div>
        ) : null}
      </div>
    </div>
  )
}
