import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getCommitmentToday: vi.fn(),
  getCommitmentCards: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getCommitmentToday: mocks.getCommitmentToday,
  getCommitmentCards: mocks.getCommitmentCards,
}))

const panelProps = vi.hoisted(() => ({ last: vi.fn() }))

vi.mock('@/components/safety', () => ({
  SafetyCommitmentPanel: (props: Record<string, unknown>) => {
    panelProps.last(props)
    return null
  },
}))

import SafetyCommitmentPage from './page'

const REPORT = {
  id: 'r-1',
  report_date: '2026-11-09',
  enterprise_status: { workshop_total: 6 },
  status: 'draft',
}

describe('安全承诺页装配', () => {
  it('加载成功时把当日日报与信息卡传给面板', async () => {
    mocks.getCommitmentToday.mockResolvedValue({
      code: 200,
      data: { report: REPORT, created_today: true },
    })
    mocks.getCommitmentCards.mockResolvedValue({
      code: 200,
      data: { cards: [{ id: 'c-1', card_type: 'commitment', title: 't', content: 'c', sort_order: 0 }] },
    })
    await SafetyCommitmentPage().then((element) => renderToStaticMarkup(element))
    expect(mocks.getCommitmentToday).toHaveBeenCalledWith('safety:safety-commitment')
    expect(mocks.getCommitmentCards).toHaveBeenCalledWith(undefined, 'safety:safety-commitment')
    expect(panelProps.last).toHaveBeenCalledWith({
      initialReport: REPORT,
      initialCreatedToday: true,
      initialCards: [{ id: 'c-1', card_type: 'commitment', title: 't', content: 'c', sort_order: 0 }],
      initialError: null,
    })
  })

  it('加载失败时传错误提示给面板', async () => {
    mocks.getCommitmentToday.mockResolvedValue({ code: 500, message: '数据库不可用' })
    mocks.getCommitmentCards.mockResolvedValue({ code: 500, message: 'x' })
    await SafetyCommitmentPage().then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith({
      initialReport: null,
      initialCreatedToday: false,
      initialCards: [],
      initialError: '数据库不可用',
    })
  })
})
