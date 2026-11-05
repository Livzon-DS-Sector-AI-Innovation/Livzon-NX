import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchCalibrationPlansClient,
  fetchEquipmentStatisticsClient,
  fetchEquipmentsClient,
  fetchMaintenancePlansClient,
  fetchSparePartsClient,
  fetchStockWarningsClient,
  fetchWorkOrderMaterialsClient,
  fetchWorkOrderStatisticsClient,
  fetchWorkOrdersClient,
  fetchWorkOrderEventsClient,
  fetchHealthBoardClient,
  fetchRepairProfileClient,
  fetchLaborRatesClient,
  fetchCostReportClient,
  fetchKnowledgeCasesClient,
  fetchMonthlyReportsClient,
} from './equipment-client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function lastUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls.at(-1)?.[0] ?? '')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('equipment-client workshop scoping', () => {
  it('fetches equipments with workshop filter and maps pagination meta', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [{ id: 'e1' }], meta: { total: 3, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchEquipmentsClient({ workshop: '101-2', keyword: '泵', page: 1 })
    const url = lastUrl(fetchMock)
    expect(url.startsWith('/api/v1/equipment/equipments?')).toBe(true)
    expect(url).toContain('workshop=101-2')
    expect(url).toContain('keyword=')
    expect(result).toMatchObject({ total: 3 })
  })

  it('fetches equipment statistics with workshop query', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: { total: 0, by_status: {}, by_category: {}, by_location: {} } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchEquipmentStatisticsClient('101-2')
    expect(lastUrl(fetchMock)).toBe('/api/v1/equipment/equipments/statistics?workshop=101-2')
  })

  it('fetches work orders on the maintenance path with workshop filter', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchWorkOrdersClient({ workshop: '103', status: '待处理' })
    const url = lastUrl(fetchMock)
    expect(url.startsWith('/api/v1/equipment/maintenance/work-orders?')).toBe(true)
    expect(url).toContain('workshop=103')
  })

  it('fetches work order statistics on the corrected path with workshop query', async () => {
    // 回归：原实现拼成 work-ordersstatistics（缺斜杠）导致统计一直静默为空
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: { total: 1, by_status: {}, by_type: {}, by_priority: {} } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const stats = await fetchWorkOrderStatisticsClient('103')
    expect(lastUrl(fetchMock)).toBe(
      '/api/v1/equipment/maintenance/work-orders/statistics?workshop=103',
    )
    expect(stats).toMatchObject({ total: 1 })
  })

  it('fetches spare parts and stock warnings with workshop scoping', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchSparePartsClient({ workshop: '201-1', keyword: '滤芯' })
    expect(lastUrl(fetchMock)).toContain('/api/v1/equipment/spare-parts/?')
    expect(lastUrl(fetchMock)).toContain('workshop=201-1')

    await fetchStockWarningsClient('201-1')
    expect(lastUrl(fetchMock)).toBe(
      '/api/v1/equipment/spare-parts/stock/warnings?workshop=201-1',
    )
  })

  it('fetches calibration and maintenance plans with workshop filter', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchCalibrationPlansClient({ workshop: '201-1' })
    expect(lastUrl(fetchMock)).toContain('/api/v1/equipment/maintenance/calibration/plans?')
    expect(lastUrl(fetchMock)).toContain('workshop=201-1')

    await fetchMaintenancePlansClient({ workshop: '202' })
    expect(lastUrl(fetchMock)).toContain('/api/v1/equipment/maintenance/plans/')
    expect(lastUrl(fetchMock)).toContain('workshop=202')
  })

  it('omits workshop when not provided (跨车间查询)', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [], meta: { total: 0, page: 1, page_size: 20 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchEquipmentsClient({ page: 1 })
    expect(lastUrl(fetchMock)).not.toContain('workshop')
  })
})

describe('equipment-client work order materials', () => {
  it('fetches materials with the work order path segment separated', async () => {
    // 回归：历史实现把工单号直接拼在 work-orders 后（缺斜杠）导致 404
    const fetchMock = vi.fn(() =>
      jsonResponse({ code: 200, data: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchWorkOrderMaterialsClient('wo-1')
    expect(lastUrl(fetchMock)).toBe('/api/v1/equipment/maintenance/work-orders/wo-1/materials')
  })
})


describe('fetchWorkOrderEventsClient（方案E 转派事件）', () => {
  it('按工单ID请求事件并返回 data 数组', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        code: 200,
        data: [
          {
            id: 'ev-1',
            work_order_id: 'wo-1',
            event_type: 'transferred',
            operator_id: null,
            operator_name: '王五',
            source: 'feishu',
            detail: { from: '李四', to: '王五' },
            created_at: '2026-11-04T08:00:00Z',
          },
        ],
      }),
    )
    const events = await fetchWorkOrderEventsClient('wo-1')
    expect(lastUrl(fetchMock)).toBe(
      '/api/v1/equipment/maintenance/work-orders/wo-1/events',
    )
    expect(events).toHaveLength(1)
    expect(events[0].event_type).toBe('transferred')
  })

  it('接口失败时抛出含状态码的错误', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: 500, message: 'err' }, 500),
    )
    await expect(fetchWorkOrderEventsClient('wo-2')).rejects.toThrow('500')
  })

  it('空数据返回空数组', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(jsonResponse({ code: 200, data: null }))
    expect(await fetchWorkOrderEventsClient('wo-3')).toEqual([])
  })
})


describe('方案B/C client 函数（健康/成本/知识/月报）', () => {
  it('fetchHealthBoardClient 组装 workshop/grade 参数并返回 data', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        code: 200,
        data: { items: [], summary: { total: 0, G: 0, Y: 0, R: 0 } },
      }),
    )
    const board = await fetchHealthBoardClient('201-1', 'R')
    expect(lastUrl(fetchMock)).toBe(
      '/api/v1/equipment/health/board?workshop=201-1&grade=R',
    )
    expect(board?.summary.total).toBe(0)
  })

  it('fetchRepairProfileClient 失败抛错', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: 500, message: 'err' }, 500),
    )
    await expect(fetchRepairProfileClient('eq-1')).rejects.toThrow('500')
  })

  it('fetchLaborRatesClient 返回费率数组', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: 200, data: [{ id: 'r1', scope: 'person', hourly_rate: 60, effective_from: '2026-11-01' }] }),
    )
    const rates = await fetchLaborRatesClient()
    expect(lastUrl(fetchMock)).toContain('/labor-rates')
    expect(rates[0].hourly_rate).toBe(60)
  })

  it('fetchCostReportClient 透传 group_by 并返回报表', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        code: 200,
        data: {
          month: '2026-11',
          workshop: null,
          group_by: 'equipment',
          totals: { orders: 0, spare_cost: 0, labor_cost: 0, external_cost: 0, total_cost: 0 },
          top: [],
        },
      }),
    )
    const rep = await fetchCostReportClient({ group_by: 'equipment', month: '2026-11' })
    expect(lastUrl(fetchMock)).toContain('group_by=equipment')
    expect(rep?.month).toBe('2026-11')
  })

  it('fetchKnowledgeCasesClient 组装状态与分页', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: 200, data: [], meta: { total: 0 } }),
    )
    const res = await fetchKnowledgeCasesClient({ status: 'draft', page: 1, page_size: 20 })
    expect(lastUrl(fetchMock)).toContain('status=draft')
    expect(res.total).toBe(0)
  })

  it('fetchMonthlyReportsClient 返回报告列表', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: 200, data: [{ id: 'm1', report_month: '2026-10' }] }),
    )
    const reports = await fetchMonthlyReportsClient()
    expect(lastUrl(fetchMock)).toContain('/monthly-reports')
    expect(reports[0].report_month).toBe('2026-10')
  })
})
