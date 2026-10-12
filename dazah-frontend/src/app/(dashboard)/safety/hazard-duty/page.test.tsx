import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getSafetyPageTableRecords: vi.fn(),
  getSafetyPageTableStats: vi.fn(),
  PageFeishuTable: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyPageTableRecords: mocks.getSafetyPageTableRecords,
  getSafetyPageTableStats: mocks.getSafetyPageTableStats,
}))

vi.mock('@/components/safety', () => ({ PageFeishuTable: mocks.PageFeishuTable }))
vi.mock('@/lib/safety-page-tables', () => ({
  SAFETY_PAGE_TABLE_KEYS: { hazardDuty: 'safety:risk-hazard:hazard-inspection:hazard-duty' },
  toPageTableStats: (stats: unknown) => (stats ? ({ wrapped: stats } as never) : null),
  toRecordRows: (rows: unknown) => ({ rows } as never),
}))

import SafetyHazardDutyPage from './page'

describe('safety hazard duty page', () => {
  it('loads records and stats for the hazard-duty page table', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce({
      code: 200,
      data: {
        columns: [{ field_id: 'f1', name: '记录编号' }],
        records: [['r']],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    mocks.getSafetyPageTableStats.mockResolvedValueOnce({
      code: 200,
      data: { page_key: 'k', total: 1, groups: [] },
    })

    const element = await SafetyHazardDutyPage()
    renderToStaticMarkup(element)

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith({
      pageKey: 'safety:risk-hazard:hazard-inspection:hazard-duty',
      page: 1,
      pageSize: 20,
    })
    expect(mocks.getSafetyPageTableStats).toHaveBeenCalledWith({
      pageKey: 'safety:risk-hazard:hazard-inspection:hazard-duty',
    })
    expect((mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [Record<string, unknown>] | undefined)?.[0]).toMatchObject({
      pageName: '24小时值班隐患',
      initialError: null,
    })
    expect(element).toBeTruthy()
  })

  it('passes the load error through when the backend fails', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce({
      code: 500,
      message: '飞书不可用',
    })
    mocks.getSafetyPageTableStats.mockResolvedValueOnce({ code: 500, data: null })

    renderToStaticMarkup(await SafetyHazardDutyPage())

    expect((mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [Record<string, unknown>] | undefined)?.[0]).toMatchObject({
      initialData: null,
      initialStats: null,
      initialError: '飞书不可用',
    })
  })
})
