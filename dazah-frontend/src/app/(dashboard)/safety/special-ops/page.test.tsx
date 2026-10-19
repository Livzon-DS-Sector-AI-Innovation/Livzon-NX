/* @vitest-environment happy-dom */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getSpecialOperationLedgerStats: vi.fn(),
  getSpecialOperationReports: vi.fn(),
  SpecialOpsManagement: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/actions/safety', () => ({
  getSpecialOperationLedgerStats: mocks.getSpecialOperationLedgerStats,
  getSpecialOperationReports: mocks.getSpecialOperationReports,
}))

vi.mock('@/components/safety/SpecialOpsManagement', () => ({
  default: mocks.SpecialOpsManagement,
}))

import SpecialOpsPage from './page'

describe('special ops page', () => {
  it('server-renders today-scoped stats and list into the client panel', async () => {
    const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
    mocks.getSpecialOperationLedgerStats.mockResolvedValueOnce({
      code: 200,
      data: [{ date: today, count: 3 }],
    })
    mocks.getSpecialOperationReports.mockResolvedValueOnce({
      code: 200,
      data: [{ id: 'r1' }],
      meta: { total: 1 },
    })

    renderToStaticMarkup(await SpecialOpsPage())

    expect(mocks.getSpecialOperationLedgerStats).toHaveBeenCalledWith({
      date_from: today,
      date_to: today,
    })
    expect(mocks.getSpecialOperationReports).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
      date_from: today,
      date_to: today,
    })
    expect(mocks.SpecialOpsManagement.mock.calls.at(-1)?.[0]).toMatchObject({
      initialStats: [{ date: today, count: 3 }],
      initialTotal: 1,
      initialDateFilter: today,
    })
  })

  it('falls back to client-side retry when the server load fails', async () => {
    mocks.getSpecialOperationLedgerStats.mockRejectedValueOnce(new Error('down'))
    mocks.getSpecialOperationReports.mockRejectedValueOnce(new Error('down'))

    renderToStaticMarkup(await SpecialOpsPage())

    expect(mocks.SpecialOpsManagement.mock.calls.at(-1)?.[0]).toMatchObject({
      initialStats: [],
      initialData: [],
      initialTotal: 0,
    })
  })
})
