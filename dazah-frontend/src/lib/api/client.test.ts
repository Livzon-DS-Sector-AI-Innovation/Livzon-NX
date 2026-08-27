/* @vitest-environment happy-dom */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchPermissions } from './client/admin'
import { fetchDepartments } from './client/hr'
import { fetchModuleInfo } from './client/registration'
import { fetchRegulatoryTrackerSummaryClient } from './client/regulatoryTracker'
import { fetchProductQualityProducts } from './client/quality'
import { fetchWarehousePageFeishuConfigs } from './client/warehouse'

describe('migrated browser API clients', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the six migrated client domains under their application proxies', async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({ data: [] }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchPermissions()
    await fetchDepartments({ page: 1, page_size: 10 })
    await fetchProductQualityProducts()
    await fetchModuleInfo()
    await fetchRegulatoryTrackerSummaryClient()
    await fetchWarehousePageFeishuConfigs()

    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(urls).toEqual([
      '/api/v1/identity/admin/permissions',
      '/api/v1/hr/departments?page=1&page_size=10',
      '/api/v1/quality/product-quality-standards',
      '/api/v1/registration/',
      '/api/v1/regulatory-tracker/summary',
      '/api/v1/warehouse/page-feishu-configs',
    ])
  })
})
