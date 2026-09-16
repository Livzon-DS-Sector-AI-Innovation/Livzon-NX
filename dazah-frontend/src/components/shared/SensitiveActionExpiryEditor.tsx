"use client"

import dayjs from "dayjs"
import { Button, DatePicker, Space } from "antd"

export function sensitiveActionExpiryFromDays(days: number): string {
  return dayjs().add(days, "day").endOf("day").toISOString()
}

export function SensitiveActionExpiryEditor({ value, disabled, onChange, onRevoke }: {
  value?: string | null
  disabled?: boolean
  onChange: (value: string | null) => void
  onRevoke?: () => void
}) {
  return <Space wrap className="mt-3">
    <DatePicker showTime className="w-64" aria-label="高风险权限到期时间"
      placeholder="设置高风险权限到期时间" disabled={disabled}
      value={value ? dayjs(value) : null}
      disabledDate={(date) => date.endOf("day").isBefore(dayjs())}
      onChange={(date) => onChange(date?.toISOString() || null)} />
    {[7, 30, 90].map((days) => <Button key={days} size="small" disabled={disabled}
      onClick={() => onChange(sensitiveActionExpiryFromDays(days))}>{days} 天</Button>)}
    {onRevoke && <Button size="small" danger disabled={disabled} onClick={onRevoke}>撤销高风险动作</Button>}
  </Space>
}
