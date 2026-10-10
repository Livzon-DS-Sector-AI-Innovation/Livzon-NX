import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchWarehouseInspectionProgressOverview,
  fetchWarehousePageFeishuConfigTables,
  fetchWarehouseRecordDetail,
} from './warehouse'

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

describe('warehouse client - record detail page context', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it.each([
    ['inbound-ledger', 'warehouse:materials:inbound-ledger'],
    ['raw-detail', 'warehouse:materials:raw-detail'],
    ['packaging-detail', 'warehouse:materials:packaging-detail'],
    ['product-summary', 'warehouse:product-inventory:product-summary'],
    ['product-inbound-detail', 'warehouse:product-inventory:product-inbound-detail'],
    ['product-detail-l-phenylalanine', 'warehouse:product-inventory:product-details:product-detail-l-phenylalanine'],
    ['product-detail-fumaric-acid', 'warehouse:product-inventory:product-details:product-detail-fumaric-acid'],
    ['product-detail-l-tryptophan', 'warehouse:product-inventory:product-details:product-detail-l-tryptophan'],
    ['product-detail-mevastatin', 'warehouse:product-inventory:product-details:product-detail-mevastatin'],
    ['product-detail-kitasamycin-hcl', 'warehouse:product-inventory:product-details:product-detail-kitasamycin-hcl'],
    ['product-detail-doramectin', 'warehouse:product-inventory:product-details:product-detail-doramectin'],
    ['product-detail-lovastatin', 'warehouse:product-inventory:product-details:product-detail-lovastatin'],
    ['product-detail-florfenicol-premix', 'warehouse:product-inventory:product-details:product-detail-florfenicol-premix'],
    ['product-detail-demeclocycline-hcl', 'warehouse:product-inventory:product-details:product-detail-demeclocycline-hcl'],
    ['product-detail-fenbendazole-powder', 'warehouse:product-inventory:product-details:product-detail-fenbendazole-powder'],
    ['hardware-summary', 'warehouse:hardware:hardware-hardware-summary'],
    ['hardware-101-1-workshop', 'warehouse:hardware:hardware-hardware-101-1-workshop'],
  ])('uses the target permission page for %s', async (pageKey, permissionPageKey) => {
    const detail = { record_id: 'rec-pending', fields: [] }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ code: 200, data: detail }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchWarehouseRecordDetail(pageKey, 'rec-pending')).resolves.toEqual(detail)
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/warehouse/material-pages/${pageKey}/records/rec-pending`,
      { headers: { 'X-Dazah-Page-Key': permissionPageKey } },
    )
  })

  it('rejects an unregistered target without sending a request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchWarehouseRecordDetail('unknown-page', 'rec-pending'))
      .rejects.toThrow('仓储记录所属页面未登记，无法获取详情')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('retains the timeout when adding page context', async () => {
    const signal = new AbortController().signal
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(signal)
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: { record_id: 'r1', fields: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchWarehouseRecordDetail('inbound-ledger', 'r1', 5000)
    expect(timeout).toHaveBeenCalledWith(5000)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/warehouse/material-pages/inbound-ledger/records/r1',
      { headers: { 'X-Dazah-Page-Key': 'warehouse:materials:inbound-ledger' }, signal },
    )
  })

  it('reports denied access without retrying under another page identity', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ code: 403 }, 403))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchWarehouseRecordDetail('inbound-ledger', 'rec-pending'))
      .rejects.toThrow('无权查看该仓储记录详情，请确认所属台账的查询权限和数据范围')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('keeps the request failure distinct from permission denial', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 502)))

    await expect(fetchWarehouseRecordDetail('inbound-ledger', 'rec-pending'))
      .rejects.toThrow('获取仓储记录详情失败')
  })
})

describe('warehouse client - page feishu config tables', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches tables bundle with encoded app_token and returns data', async () => {
    const tables = { app_token: 'AppRealToken', tables: [{ table_id: 'tbl1', name: '台账' }] }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ code: 200, data: tables }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchWarehousePageFeishuConfigTables('WikiBaseToken123')
    ).resolves.toEqual(tables)
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toBe(
      '/api/v1/warehouse/page-feishu-configs/tables?app_token=WikiBaseToken123',
    )
  })

  it('throws backend message when tables request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ message: 'wiki 链接无法解析出 app_token' }, 400),
      ),
    )

    await expect(fetchWarehousePageFeishuConfigTables('bad')).rejects.toThrow(
      'wiki 链接无法解析出 app_token',
    )
  })
})
