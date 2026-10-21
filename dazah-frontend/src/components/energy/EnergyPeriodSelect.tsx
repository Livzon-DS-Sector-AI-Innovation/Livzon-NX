'use client'

import { Select } from 'antd'

export function EnergyPeriodSelect({ year, month, onYear, onMonth }: { year: number; month: number; onYear: (year: number) => void; onMonth: (month: number) => void }) {
  return <><label>年份 <Select aria-label="年份" showSearch value={year} onChange={onYear} style={{ width: 110 }} options={Array.from({ length: 101 }, (_, index) => ({ value: 2000 + index, label: `${2000 + index}年` }))} /></label><label>月份 <Select aria-label="月份" value={month} onChange={onMonth} style={{ width: 95 }} options={Array.from({ length: 12 }, (_, index) => ({ value: index + 1, label: `${index + 1}月` }))} /></label></>
}
