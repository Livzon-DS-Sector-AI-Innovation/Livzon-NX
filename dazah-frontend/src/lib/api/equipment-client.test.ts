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
