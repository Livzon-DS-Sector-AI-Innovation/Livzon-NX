'use client'

import { Select } from 'antd'
import { useId } from 'react'
import styles from './EnergyWorkspace.module.css'

export function EnergyPeriodSelect({ year, month, onYear, onMonth }: { year: number; month: number; onYear: (year: number) => void; onMonth: (month: number) => void }) {
  const id = useId()
  return <><label className={`${styles.filterField} ${styles.filterFieldCompact}`} htmlFor={`${id}-year`}>年份<Select id={`${id}-year`} aria-label="年份" showSearch value={year} onChange={onYear} options={Array.from({ length: 101 }, (_, index) => ({ value: 2000 + index, label: `${2000 + index}年` }))} /></label><label className={`${styles.filterField} ${styles.filterFieldCompact}`} htmlFor={`${id}-month`}>月份<Select id={`${id}-month`} aria-label="月份" value={month} onChange={onMonth} options={Array.from({ length: 12 }, (_, index) => ({ value: index + 1, label: `${index + 1}月` }))} /></label></>
}
