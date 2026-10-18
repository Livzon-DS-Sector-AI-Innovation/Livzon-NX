'use client'

import { Button, Card, Segmented, Typography } from 'antd'

import type { PageTableDueSummary } from '@/lib/safety-page-tables'

const WINDOWS = [7, 15, 30]

/** 仪表盘「到期提醒」卡：未关闭隐患按目标完成日期的临期/逾期汇总。
 * 时间窗（7/15/30 天）即点即切（计数已预计算，无需重新请求）；
 * 点击「筛选明细」把窗口条件应用到下方列表（含逾期）。 */
export default function PageDueReminderCard({
  summary,
  window: activeWindow,
  drilling,
  onWindowChange,
  onToggleDrill,
}: {
  summary: PageTableDueSummary
  window: number
  drilling: boolean
  onWindowChange: (days: number) => void
  onToggleDrill: () => void
}) {
  const within =
    summary[`within_${activeWindow}` as keyof PageTableDueSummary] ?? 0
  const total = summary.overdue + within

  return (
    <Card
      size="small"
      title="到期提醒"
      extra={
        <Segmented
          size="small"
          value={activeWindow}
          options={WINDOWS.map((days) => ({ label: `${days}天`, value: days }))}
          onChange={(value) => onWindowChange(value as number)}
        />
      }
      style={{ width: 300, flex: 'none' }}
      styles={{ body: { paddingBlock: 10 } }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 28, fontWeight: 600, lineHeight: 1 }}>
          {total}
        </span>
        <Typography.Text type="secondary">项未关闭临期/逾期</Typography.Text>
      </div>
      <Typography.Text
        type={summary.overdue > 0 ? 'danger' : 'secondary'}
        style={{ fontSize: 12 }}
      >
        已逾期 {summary.overdue} 项 · {activeWindow} 天内到期 {within} 项
      </Typography.Text>
      <div style={{ marginTop: 8 }}>
        <Button size="small" type={drilling ? 'default' : 'primary'} onClick={onToggleDrill}>
          {drilling ? '取消筛选' : '筛选明细'}
        </Button>
      </div>
    </Card>
  )
}
