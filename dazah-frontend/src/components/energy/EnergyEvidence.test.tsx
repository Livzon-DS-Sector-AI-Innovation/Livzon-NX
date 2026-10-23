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
