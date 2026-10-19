import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  SafetyPageFeishuMirror: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/components/safety', () => ({
  SafetyPageFeishuMirror: mocks.SafetyPageFeishuMirror,
}))

import Page from './page'

describe('关键风险作业报备表 mirror page', () => {
  it('renders the mirror with the riskWorkRegistration page key', () => {
    renderToStaticMarkup(Page())

    expect((mocks.SafetyPageFeishuMirror.mock.calls.at(-1) as unknown as [Record<string, unknown>] | undefined)?.[0]).toMatchObject({
      pageKey: 'safety:ops-safety:risk-work-registration',
      pageName: '关键风险作业报备表',
    })
  })
})
