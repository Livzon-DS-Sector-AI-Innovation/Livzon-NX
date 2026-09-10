import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchWarehouseInspectionProgressOverview } from './warehouse'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('warehouse client - inspection progress', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches raw-material overview with default 30 days window', async () => {
    const overview = { total: 12, avg_days: 2.5 }
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: overview })
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchWarehouseInspectionProgressOverview('raw')
    ).resolves.toEqual(overview)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/warehouse/inspection-progress/overview?scope=raw&days=30'
    )
  })

  it('passes explicit days for product scope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { total: 0, avg_days: 0 } })
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchWarehouseInspectionProgressOverview('product', 7)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/warehouse/inspection-progress/overview?scope=product&days=7'
    )
  })

  it('throws business error when request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 500)))
    await expect(
      fetchWarehouseInspectionProgressOverview('raw', 30)
    ).rejects.toThrow('获取检验进度数据失败')
  })
})
