/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  reviews: [{
    dataset: '冰水量',
    column: 14,
    periods: [{
      start_date: '2026-07-26',
      end_date: '2026-07-26',
      reason: '底码跳变',
      source: '原表 N31',
      reported_values: { '2026-07-26': '28674' },
    }],
    updated_at: '2026-07-27T00:00:00Z',
    updated_by: 'user-1',
  }],
  datasets: [{ name: '冰水量', kind: 'usage' }],
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: string[] }) => {
    if (queryKey[1] === 'usage-reviews') return { data: state.reviews, error: null, isFetching: false }
    if (queryKey[1] === 'datasets') return { data: state.datasets, error: null, isLoading: false }
    return { data: { columns: [{ key: '14', label: '冰水', unit: 'm³' }] }, error: null, isLoading: false }
  },
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))
vi.mock('@/actions/energy-ledger', () => ({ saveUsageReviews: vi.fn(async () => ({ ok: true, data: [] })) }))
vi.mock('./EnergyPeriodSelect', () => ({ EnergyPeriodSelect: () => <div>期间选择</div> }))
vi.mock('./EnergyDatePicker', () => ({ EnergyDatePicker: ({ label }: { label: string }) => <span>{label}</span> }))

import { saveUsageReviews } from '@/actions/energy-ledger'
import { EnergyReviewClient } from './EnergyReviewClient'

let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.replaceChildren(); vi.clearAllMocks() })

it('lists current reviews and clears a field with an audited empty period set', async () => {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<App><EnergyReviewClient /></App>))
  expect(document.body.textContent).toContain('冰水量')
  expect(document.body.textContent).toContain('底码跳变')
  expect(document.body.textContent).toContain('原表 N31')
  const clear = [...document.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent === '清除')
  expect(clear).toBeDefined()
  await act(async () => clear!.click())
  expect(saveUsageReviews).toHaveBeenCalledWith({
    reviews: [{ dataset: '冰水量', column: 14, periods: [] }],
    reason: '确认完成',
  })
})

it('keeps the review and its draft after save and clear requests fail', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  await act(async () => root?.render(<App><EnergyReviewClient /></App>))
  const button = (text: string) => [...host.querySelectorAll('button')]
    .find(node => node.textContent?.replace(/\s/g, '') === text)
  const savedReview = state.reviews[0]
  vi.mocked(saveUsageReviews).mockRejectedValueOnce(new Error('TypeError: review save adapter failed'))
  await act(async () => button('编辑')!.click())
  await act(async () => button('保存待确认区间')!.click())
  expect(saveUsageReviews).toHaveBeenCalledWith({
    reviews: [{ dataset: savedReview.dataset, column: savedReview.column, periods: savedReview.periods }],
    reason: 'Web 复核',
  })
  expect(host.textContent).toContain('待确认区间未保存')
  expect(host.querySelector<HTMLInputElement>('#energy-review-reason')?.value).toBe('底码跳变')

  vi.mocked(saveUsageReviews).mockRejectedValueOnce(new Error('TypeError: review clear adapter failed'))
  await act(async () => button('清除')!.click())
  expect(saveUsageReviews).toHaveBeenLastCalledWith({
    reviews: [{ dataset: savedReview.dataset, column: savedReview.column, periods: [] }],
    reason: '确认完成',
  })
  expect(host.textContent).toContain('待确认标记未清除')
  expect(host.querySelector('tbody')?.textContent).toContain('底码跳变')
})
