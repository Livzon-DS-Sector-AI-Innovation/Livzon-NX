/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import { expect, it } from 'vitest'
import { EnergyEvidence } from './EnergyEvidence'

it.each([false, true])('shows review reason alongside unchanged original readings (dark=%s)', async dark => {
  const host = document.createElement('div'); document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><EnergyEvidence value={{
      reading_dates: ['2026-07-26', '2026-07-27'], reading_values: ['316278', '2365593'],
      review: [{ reason: '底码跳变与手填冲突', source: '飞书N31', reported_value: '28674' }],
    }} /></ConfigProvider>))
    expect(host.textContent).toContain('316278 → 2365593')
    expect(host.textContent).toContain('待确认：底码跳变与手填冲突')
    expect(host.textContent).toContain('原表值：28674')
    expect(host.textContent).toContain('已排除在有效汇总和占比之外')
  } finally { await act(async () => root.unmount()); host.remove() }
})

it.each([false, true])('separates system formulas from imported manual reference values (dark=%s)', async dark => {
  const host = document.createElement('div'); document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><EnergyEvidence value={{
      calculation_policy: 'same-day-formulas-v1', calculation_date: '2028-02-29', formula: '1 × 设备',
      reference: { source_sheet: '101车间', source_cell: 'C3', reported_value: '999' },
    }} /></ConfigProvider>))
    expect(host.textContent).toContain('系统公式：1 × 设备')
    expect(host.textContent).toContain('2028-02-29（按当天业务日期关联）')
    expect(host.textContent).toContain('101车间!C3；手填值 999')
    expect(host.textContent).toContain('仅供核对，不参与系统计算')
  } finally { await act(async () => root.unmount()); host.remove() }
})

it('shows the comparison of this field instead of a dependency value', async () => {
  const host = document.createElement('div'); document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<EnergyEvidence value={{ source_comparison: { reported_value: '322673', difference: null, calculation_status: 'abnormal_dependency', source: '日用量!J7' } }} />))
    expect(host.textContent).toContain('待核对：原表值 322673')
    expect(host.textContent).toContain('差异（原表－系统）：无法计算（来源存在异常）')
    expect(host.textContent).toContain('日用量!J7')
  } finally { await act(async () => root.unmount()); host.remove() }
})
