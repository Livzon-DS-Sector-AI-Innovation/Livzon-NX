'use client'

import { useState } from 'react'
import { Button, ConfigProvider, DatePicker, theme } from 'antd'
import dayjs from 'dayjs'
import styles from './EnergyWorkspace.module.css'

export function EnergyDatePicker({ id, label, value, onChange, disabled, allowClear = true }: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  allowClear?: boolean
}) {
  const [open, setOpen] = useState(false)
  const { token } = theme.useToken()
  function selectDate(value: string) {
    onChange(value)
    setOpen(false)
  }
  // Keep seven calendar columns within narrow screens using the current theme's compact control size.
  return <ConfigProvider theme={{ components: { DatePicker: { cellWidth: token.controlHeightSM } } }}><DatePicker
    id={id}
    aria-label={label}
    className={styles.datePicker}
    value={value ? dayjs(value) : null}
    format={['YYYY年MM月DD日', 'YYYY-MM-DD']}
    placeholder="选择日期"
    disabled={disabled}
    allowClear={allowClear}
    open={!disabled && open}
    onOpenChange={setOpen}
    onChange={date => selectDate(date?.format('YYYY-MM-DD') ?? '')}
    showNow={false}
    renderExtraFooter={() => <div className={styles.dateShortcuts}>
      <Button type="text" size="small" onClick={() => selectDate(dayjs().format('YYYY-MM-DD'))}>今天</Button>
      <Button type="text" size="small" onClick={() => selectDate(dayjs().subtract(1, 'day').format('YYYY-MM-DD'))}>昨天</Button>
      <Button type="text" size="small" onClick={() => selectDate(dayjs().startOf('month').format('YYYY-MM-DD'))}>本月初</Button>
    </div>}
  /></ConfigProvider>
}
