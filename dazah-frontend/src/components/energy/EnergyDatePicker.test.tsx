/* @vitest-environment happy-dom */
import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import { afterEach, expect, it, vi } from 'vitest'
import { getAntdTheme } from '@/lib/antd-theme'
import { EnergyDatePicker } from './EnergyDatePicker'

let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.replaceChildren() })

it.each(['light', 'dark'] as const)('selects calendar days and shortcuts as ISO dates with the %s theme', async mode => {
  const change = vi.fn()
  function Picker() {
    const [value, setValue] = useState('2026-10-20')
    return <EnergyDatePicker id="date" label="数据日期" value={value} onChange={date => { setValue(date); change(date) }} />
  }
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<ConfigProvider locale={zhCN} theme={getAntdTheme(mode)}><Picker /></ConfigProvider>))
  const input = host.querySelector('input')!
  expect(input.type).toBe('text')
  expect(input.value).toBe('2026年10月20日')
  await act(async () => input.click())
  expect(document.querySelector('.ant-picker-dropdown')).not.toBeNull()
  await act(async () => document.querySelector<HTMLElement>('td[title="2026-10-22"] .ant-picker-cell-inner')!.click())
  expect(change).toHaveBeenLastCalledWith('2026-10-22')
  for (const [label, value] of [['今天', dayjs()], ['昨天', dayjs().subtract(1, 'day')], ['本月初', dayjs().startOf('month')]] as const) {
    await act(async () => input.click())
    const shortcut = [...document.querySelectorAll<HTMLButtonElement>('.ant-picker-dropdown button')].find(button => button.textContent === label)!
    await act(async () => shortcut.click())
    expect(change).toHaveBeenLastCalledWith(value.format('YYYY-MM-DD'))
    expect(input.value).toBe(value.format('YYYY年MM月DD日'))
  }
  await act(async () => host.querySelector<HTMLElement>('.ant-picker-clear')!.click())
  expect(change).toHaveBeenLastCalledWith('')
  expect(input.value).toBe('')
})

it('disables date edits and prevents clearing required dates', async () => {
  const change = vi.fn()
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<EnergyDatePicker id="date" label="数据日期" value="2026-10-20" disabled allowClear={false} onChange={change} />))
  expect(host.querySelector('input')?.disabled).toBe(true)
  expect(host.querySelector('.ant-picker-clear')).toBeNull()
  await act(async () => host.querySelector('input')!.click())
  expect(document.querySelector('.ant-picker-dropdown')).toBeNull()
  expect(change).not.toHaveBeenCalled()
})
