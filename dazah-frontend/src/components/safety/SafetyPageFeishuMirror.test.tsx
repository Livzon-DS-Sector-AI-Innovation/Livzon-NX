import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getSafetyPageTableRecords: vi.fn(),
  PageFeishuTable: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyPageTableRecords: mocks.getSafetyPageTableRecords,
}))

vi.mock('@/components/safety', () => ({ PageFeishuTable: mocks.PageFeishuTable }))
vi.mock('@/lib/safety-page-tables', () => ({
  SAFETY_PAGE_TABLE_KEYS: {
    dailyRiskReport: 'safety:ops-safety:daily-risk-report',
    riskWorkRegistration: 'safety:ops-safety:risk-work-registration',
  },
  // 报备表不在“默认当天”名单内：数据量小、历史全量展示
  SAFETY_PAGE_TABLE_DEFAULT_TODAY: new Set([
    'safety:ops-safety:daily-risk-report',
  ]),
  pickDefaultDateColumn: (
    columns: Array<{ kind: string; name: string }> | undefined | null
  ) => (columns ?? []).find((column) => column.kind === 'date') ?? null,
  toRecordRows: (rows: unknown) => ({ rows } as never),
}))

import SafetyPageFeishuMirror from './SafetyPageFeishuMirror'

const PAGE_KEY = 'safety:ops-safety:daily-risk-report'

function recordsResponse(columns: Array<Record<string, unknown>>) {
  return {
    code: 200,
    data: {
      columns,
      records: [{ record_id: 'r1', fields: {} }],
      total: 1,
      page: 1,
      page_size: 20,
      truncated: false,
    },
  }
}

describe('safety page feishu mirror shell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to today on the date column and passes the filter to the table', async () => {
    mocks.getSafetyPageTableRecords
      .mockResolvedValueOnce(
        recordsResponse([
          { field_id: 'f1', name: '申请编号', kind: 'text' },
          { field_id: 'f2', name: '作业开始时间', kind: 'date' },
        ])
      )
      .mockResolvedValueOnce(
        recordsResponse([
          { field_id: 'f1', name: '申请编号', kind: 'text' },
          { field_id: 'f2', name: '作业开始时间', kind: 'date' },
        ])
      )

    const element = await SafetyPageFeishuMirror({
      pageKey: PAGE_KEY,
      pageName: '关键风险作业报备',
    })
    renderToStaticMarkup(element)

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledTimes(2)
    expect(mocks.getSafetyPageTableRecords).toHaveBeenNthCalledWith(1, {
      pageKey: PAGE_KEY,
      page: 1,
      pageSize: 20,
    })
    const secondCall = mocks.getSafetyPageTableRecords.mock.calls[1]?.[0] as {
      conditions?: Array<{ field: string; value: string }>
    }
    expect(secondCall.conditions).toEqual([
      {
        field: '作业开始时间',
        value: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      },
    ])
    const props = (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
      Record<string, unknown>,
    ])[0]
    expect(props).toMatchObject({
      pageKey: PAGE_KEY,
      pageName: '关键风险作业报备',
      showStats: false,
      summarizeColumns: true,
      initialError: null,
    })
    expect(props.initialDateFilter).toEqual({
      field: '作业开始时间',
      value: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    })
  })

  it('skips the today filter when the table has no date column', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce(
      recordsResponse([{ field_id: 'f1', name: '申请编号', kind: 'text' }])
    )

    const element = await SafetyPageFeishuMirror({
      pageKey: PAGE_KEY,
      pageName: '关键风险作业报备',
    })
    renderToStaticMarkup(element)

    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledTimes(1)
    expect(
      (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
        Record<string, unknown>,
      ])[0].initialDateFilter
    ).toBeNull()
  })

  it('shows all records by default for pages outside the default-today set', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce(
      recordsResponse([
        { field_id: 'f1', name: '日期', kind: 'date' },
      ])
    )

    const element = await SafetyPageFeishuMirror({
      pageKey: 'safety:ops-safety:risk-work-registration',
      pageName: '关键风险作业报备表',
    })
    renderToStaticMarkup(element)

    // 有日期列但页面不在“默认当天”名单内：不做第二次过滤请求
    expect(mocks.getSafetyPageTableRecords).toHaveBeenCalledTimes(1)
    expect(
      (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
        Record<string, unknown>,
      ])[0].initialDateFilter
    ).toBeNull()
  })

  it('passes the backend failure through as the initial error', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce({
      code: 502,
      message: '多维表格绑定未配置',
    })

    const element = await SafetyPageFeishuMirror({
      pageKey: PAGE_KEY,
      pageName: '关键风险作业报备',
    })
    renderToStaticMarkup(element)

    expect(
      (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
        Record<string, unknown>,
      ])[0]
    ).toMatchObject({
      initialData: null,
      initialError: '多维表格绑定未配置',
    })
  })

  it('forwards the preferred column names to the table', async () => {
    mocks.getSafetyPageTableRecords.mockResolvedValueOnce(
      recordsResponse([{ field_id: 'f1', name: '申请编号', kind: 'text' }])
    )
    const preferred = ['申请编号', '发起时间', '变更级别']

    const element = await SafetyPageFeishuMirror({
      pageKey: PAGE_KEY,
      pageName: 'EHS变更审批',
      preferredColumnNames: preferred,
    })
    renderToStaticMarkup(element)

    expect(
      (mocks.PageFeishuTable.mock.calls.at(-1) as unknown as [
        Record<string, unknown>,
      ])[0]
    ).toMatchObject({
      summarizeColumns: true,
      preferredColumnNames: preferred,
    })
  })
})
