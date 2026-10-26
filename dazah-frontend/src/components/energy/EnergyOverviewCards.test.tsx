/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, expect, it } from 'vitest'
import type { Report } from '@/lib/api/energy-ledger'
import { EnergyOverviewCards } from './EnergyOverviewCards'

const water: Report['totals'][number] = { category: 'chilled_water', unit: 'm³', quantity_kind: 'volume', temperature: '7℃', value: '586027', expected_count: 62, available_count: 38, basis: { usage_date: '2026-07-19', nodes: [
  { node_id: '0', name: '7℃冰水总量', operation: 'sum', status: 'complete', value: '28010', calculated_value: '28010', coefficient: '1', multiplier: '1', note: '', reading_type: '', source_sheet: '', source_column: '' },
  { node_id: '0.0', parent_id: '0', name: '103一车间（7°）', source_sheet: '冰水码', source_column: 'E', reading_type: 'counter', reading_dates: ['2026-07-19', '2026-07-20'], reading_values: ['100', '28110'], multiplier: '1', coefficient: '1', status: 'complete', value: '28010', note: '', operation: '' },
] } }
const air: Report['totals'][number] = { ...water, category: 'air', temperature: '', value: '53070', unit: '万m³' }
function report(overrides: Partial<Report> = {}): Report {
  return {
    start_date: '2026-07-01', end_date: '2026-07-31', status: 'partial', rows: [], total_count: 62,
    totals: [water, air], latest_complete_date: '2026-07-17', entry_completed: 2322, entry_total: 2322,
    trend: [
      { ...water, usage_date: '2026-07-19', expected_count: 2, available_count: 2, value: '28010' },
      { ...water, usage_date: '2026-07-20', expected_count: 2, available_count: 1, value: '500' },
      { ...water, usage_date: '2026-07-17', expected_count: 2, available_count: 2, value: '20000' },
      { ...water, usage_date: '2026-08-01', expected_count: 2, available_count: 2, value: '90000' },
      { ...air, usage_date: '2026-07-17', expected_count: 1, available_count: 1, value: '2752' },
    ], ...overrides,
  }
}

let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.innerHTML = '' })
async function render(data: Report, dark = false) {
  const node = document.createElement('div'); document.body.append(node)
  root = createRoot(node)
  await act(async () => root?.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyOverviewCards report={data} /></App></ConfigProvider>))
  return node
}

it.each([false, true])('shows dated daily usage, partial totals and actual complete days without guessing units (dark=%s)', async dark => {
  const node = await render(report(), dark)
  const card = node.querySelector('[aria-label="冰水 7℃用量摘要"]')!
  expect(card.classList.contains('ant-card')).toBe(true)
  expect(card.textContent).toContain('用量日期 2026-07-19（本项最近完整日）')
  expect(card.querySelector('.ant-statistic-title')?.textContent).toBe('当日用量')
  expect(card.querySelector('.ant-statistic-content-value')?.textContent).toBe('28,010')
  expect(card.textContent).toContain('m³')
  expect(card.textContent).toContain('统计范围：103一车间（7°）')
  expect(card.textContent).toContain('期间累计（已有数值）586,027')
  expect(card.textContent).toContain('有效天数2 / 31 天')
  expect(card.textContent).toContain('期间尚未完整，累计仅供参考')
  expect(node.querySelector('[aria-label="压缩空气用量摘要"]')?.textContent).toContain('用量日期 2026-07-17')
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(node.textContent).not.toContain('了解访问规则')
  expect(node.textContent).not.toContain('原表数值单位')
  expect(node.textContent).toContain('万m³')
  expect(node.textContent).not.toContain('原始读数填报进度')
  expect(node.textContent).not.toContain('已有值记录 / 已生成记录')
  expect(node.textContent).not.toContain('已有值占比')
})

it('keeps missing daily usage distinct from zero usage', async () => {
  const node = await render(report({ trend: [{ ...water, usage_date: '2026-07-19', value: null, available_count: 0 }], entry_completed: 0, entry_total: 0 }))
  const card = node.querySelector('[aria-label="冰水 7℃用量摘要"]')!
  expect(card.textContent).toContain('尚无完整日用量')
  expect(card.querySelector('.ant-statistic-content-value')?.textContent).toBe('—')
  expect(card.textContent).toContain('有效天数0 / 31 天')
  expect(node.textContent).not.toContain('100.0%')
})

it('accepts zero as valid usage and counts a full day only when all results are valid', async () => {
  const node = await render(report({ end_date: '2026-07-02', totals: [water], trend: [
    { ...water, usage_date: '2026-07-01', expected_count: 2, available_count: 2, value: '12' },
    { ...water, usage_date: '2026-07-02', expected_count: 2, available_count: 2, value: '0' },
  ], entry_completed: 1, entry_total: 2 }))
  const card = node.querySelector('[aria-label="冰水 7℃用量摘要"]')!
  expect(card.querySelector('.ant-statistic-content-value')?.textContent).toBe('0')
  expect(card.textContent).toContain('有效天数2 / 2 天')
  expect(card.textContent).toContain('期间完整')
  expect(node.querySelector('[role=alert]')).toBeNull()
  expect(node.textContent).not.toContain('了解访问规则')
})

it.each([false, true])('omits entry progress when the energy filter has no results (dark=%s)', async dark => {
  const node = await render(report({ totals: [], trend: [] }), dark)
  expect(node.querySelectorAll('[aria-label$="用量摘要"]')).toHaveLength(0)
  expect(node.querySelector('[aria-label="原始读数填报进度"]')).toBeNull()
  expect(node.textContent).not.toContain('已有值占比')
})

it('keeps different measurement groups separate and preserves decimal precision', async () => {
  const heat = { ...water, unit: 'kJ', quantity_kind: 'heat', value: '9007199254740993.12345678' }
  const node = await render(report({ totals: [water, heat], trend: [
    { ...water, usage_date: '2026-07-19', expected_count: 1, available_count: 1, value: '28010' },
    { ...heat, usage_date: '2026-07-18', expected_count: 1, available_count: 1, value: '9007199254740993.12345678' },
  ] }))
  const volumeCard = node.querySelector('[aria-label="冰水 7℃ · 口径 1用量摘要"]')!
  const heatCard = node.querySelector('[aria-label="冰水 7℃ · 口径 2用量摘要"]')!
  expect(volumeCard.textContent).toContain('用量日期 2026-07-19')
  expect(heatCard.textContent).toContain('用量日期 2026-07-18')
  expect(heatCard.querySelector('.ant-statistic-content-value')?.textContent).toBe('9,007,199,254,740,993.12345678')
  expect(heatCard.querySelector('dd')?.textContent).toContain('9,007,199,254,740,993.12345678')
})

it('opens dated calculation evidence with original fields, location usage and intermediate sums', async () => {
  const node = await render(report())
  const card = node.querySelector('[aria-label="冰水 7℃用量摘要"]')!
  await act(async () => (card.querySelector('button') as HTMLButtonElement).click())
  const drawer = document.querySelector('[role="dialog"]')!
  expect(drawer.querySelector('[role=alert]')).toBeNull()
  expect(drawer.textContent).not.toContain('了解访问规则')
  expect(drawer.textContent).toContain('冰水 7℃ · 计算依据')
  expect(drawer.textContent).toContain('依据日期：2026-07-19')
  expect(drawer.textContent).toContain('冰水码!E列')
  expect(drawer.textContent).toContain('2026-07-19：100')
  expect(drawer.textContent).toContain('2026-07-20：28110')
  expect(drawer.textContent).toContain('次日读数 − 当日读数')
  expect(drawer.textContent).toContain('1 × 103一车间（7°）')
})

it('renders both chilled-water temperatures separately and uses the confirmed electricity unit', async () => {
  const cold = { ...water, temperature: '-5℃', value: '80' }
  const electricity = { ...water, category: 'electricity' as const, temperature: '', quantity_kind: 'electricity', unit: '千瓦时' }
  const node = await render(report({ totals: [water, cold, electricity] }))
  expect(node.querySelector('[aria-label="冰水 7℃用量摘要"]')).not.toBeNull()
  expect(node.querySelector('[aria-label="冰水 -5℃用量摘要"]')?.textContent).toContain('m³')
  expect(node.querySelector('[aria-label="电量用量摘要"]')?.textContent).toContain('千瓦时')
})

it('keeps missing calculation evidence explicit and disables the entry', async () => {
  const node = await render(report({ totals: [{ ...water, basis: null }] }))
  const card = node.querySelector('[aria-label="冰水 7℃用量摘要"]')!
  expect(card.textContent).toContain('统计范围：来源未取得，请核对配置')
  expect(card.querySelector('button')?.disabled).toBe(true)
})
