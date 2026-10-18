import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getSafetyPageTableRecords: vi.fn(),
  getSafetyPageTableStats: vi.fn(),
  getSafetyPageTableTabs: vi.fn(),
  PageFeishuTable: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyPageTableRecords: mocks.getSafetyPageTableRecords,
  getSafetyPageTableStats: mocks.getSafetyPageTableStats,
  getSafetyPageTableTabs: mocks.getSafetyPageTableTabs,
}))

vi.mock('@/components/safety', () => ({ PageFeishuTable: mocks.PageFeishuTable }))
vi.mock('@/lib/safety-page-tables', () => ({
  SAFETY_PAGE_TABLE_KEYS: {
    hazardQuickReport:
      'safety:risk-hazard:hazard-inspection:hazard-quick-report',
  },
  toPageTableStats: (stats: unknown) => (stats ? ({ wrapped: stats } as never) : null),
  toPageTableTabs: (tabs: unknown) =>
    (tabs as Array<Record<string, unknown>> | null ?? []).map((tab) => ({
      table_id: String(tab.table_id),
      tab_name: String(tab.tab_name),
      is_primary: Boolean(tab.is_primary),
      record_count: Number(tab.record_count ?? 0),
    })),
  toRecordRows: (rows: unknown) => ({ rows } as never),
}))

import SafetyHazardQuickReportPage from './page'

const PAGE_KEY = 'safety:risk-hazard:hazard-inspection:hazard-quick-report'

describe('safety hazard quick report page', () => {
  it('loads records/stats/tabs with explicit groupBy and passes multi-table tabs', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce({
      code: 200,
      data: {
        columns: [{ field_id: 'f1', name: '部门/车间' }],
        records: [['r']],
        total: 1,
        page: 1,
        page_size: 20,
        truncated: false,
      },
    })
    mocks.getSafetyPageTableStats.mockResolvedValueOnce({
      code: 200,
      data: { page_key: PAGE_KEY, total: 1, groups: [] },
    })
    mocks.getSafetyPageTableTabs.mockResolvedValueOnce({
      code: 200,
      data: {
        page_key: PAGE_KEY,
        page_name: '隐患台账',
        tabs: [
          { table_id: 'tblMain', tab_name: '隐患台账', is_primary: true, record_count: 1480 },
          { table_id: 'tblSub', tab_name: '2024年公司级检查', is_primary: false, record_count: 442 },
        ],
      },
    })

    const element = await SafetyHazardQuickReportPage()
    renderToStaticMarkup(element)

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      page: 1,
      pageSize: 20,
      sortField: '部门/车间',
    })
    // 首屏统计与客户端默认选中（主表）同口径：带主表 table_id，
    // 统计维度含负责人（台账口径）与到期分布，不传筛选条件（首屏无筛选）
    expect(mocks.getSafetyPageTableStats).toHaveBeenCalledWith({
      pageKey: PAGE_KEY,
      groupBy: ['检查内容', '部门/车间', '负责人', '关闭状态'],
      tableId: 'tblMain',
      dueField: '目标完成日期',
      closeField: '关闭状态',
    })
    expect(mocks.getSafetyPageTableTabs).toHaveBeenCalledWith({ pageKey: PAGE_KEY })
    const tableProps = (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
      Record<string, unknown>,
    ] | undefined)?.[0]
    expect(tableProps).toMatchObject({
      pageName: '隐患台账',
      statsGroupBy: ['检查内容', '部门/车间', '负责人', '关闭状态'],
      defaultSortField: '部门/车间',
      filterFields: ['部门/车间', '负责人', '关闭状态'],
      filterDateField: '检查内容',
      dueField: '目标完成日期',
      allowCreate: true,
      initialError: null,
      tabs: [
        { table_id: 'tblMain', tab_name: '隐患台账', is_primary: true, record_count: 1480 },
        { table_id: 'tblSub', tab_name: '2024年公司级检查', is_primary: false, record_count: 442 },
      ],
    })
    expect(element).toBeTruthy()
  })

  it('passes the load error through when the backend fails', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce({
      code: 500,
      message: '飞书不可用',
    })
    mocks.getSafetyPageTableStats.mockResolvedValueOnce({ code: 500, data: null })
    mocks.getSafetyPageTableTabs.mockResolvedValueOnce({ code: 500, data: null })

    renderToStaticMarkup(await SafetyHazardQuickReportPage())

    expect(
      (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
        Record<string, unknown>,
      ] | undefined)?.[0],
    ).toMatchObject({
      initialData: null,
      initialStats: null,
      initialError: '飞书不可用',
    })
  })
})
