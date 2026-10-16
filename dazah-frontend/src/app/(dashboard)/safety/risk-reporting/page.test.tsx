import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  SafetyPageFeishuMirror: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/components/safety', () => ({
  SafetyPageFeishuMirror: mocks.SafetyPageFeishuMirror,
}))
vi.mock('@/lib/safety-page-tables', () => ({
  SAFETY_PAGE_TABLE_KEYS: {
    dailyRiskReport: 'safety:ops-safety:daily-risk-report',
  },
}))

import RiskReportingPage from './page'

describe('safety risk reporting page', () => {
  it('renders the feishu mirror for the daily-risk-report page table', () => {
    const element = RiskReportingPage()
    renderToStaticMarkup(element)

    expect(
      (mocks.SafetyPageFeishuMirror.mock.calls.at(-1) as unknown as [
        Record<string, unknown>,
      ])[0]
    ).toMatchObject({
      pageKey: 'safety:ops-safety:daily-risk-report',
      pageName: '关键风险作业报备',
    })
    expect(element).toBeTruthy()
  })
})
