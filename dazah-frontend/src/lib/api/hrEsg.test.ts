import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchEsgFilterOptions, fetchEsgRecordsByDept } from './hr'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('hr esg record client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('builds query params with date range and enum filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { items: [], total: 0 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchEsgRecordsByDept('质量部', 2, 50, '2026-08-01', '2026-08-31', {
      training_type: '质量培训',
      apply_company_no: '',
      training_method: '线上',
    })
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('department=%E8%B4%A8%E9%87%8F%E9%83%A8')
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=50')
    expect(url).toContain('date_from=2026-08-01')
    expect(url).toContain('date_to=2026-08-31')
    expect(url).toContain('training_type=%E8%B4%A8%E9%87%8F%E5%9F%B9%E8%AE%AD')
    expect(url).toContain('training_method=')
    expect(url).not.toContain('apply_company_no=')
  })

  it('clamps oversized page size and surfaces fetch failures', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: { items: [], total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)
    await fetchEsgRecordsByDept('生产部', 1, 5000)
    expect(String(fetchMock.mock.calls[0][0])).toContain('page_size=1000')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 500)))
    await expect(fetchEsgRecordsByDept('生产部')).rejects.toThrow('获取 ESG 培训记录失败')
  })

  it('fetches filter options with defaults on missing data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      fetchEsgFilterOptions('质量部', '2026-08-01', '2026-08-31'),
    ).resolves.toEqual({})
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/api/v1/hr/esg-training-records/filter-options?department=')
    expect(url).toContain('date_from=2026-08-01')
    expect(url).toContain('date_to=2026-08-31')

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 502)))
    await expect(fetchEsgFilterOptions('质量部')).rejects.toThrow('获取 ESG 筛选选项失败')
  })
})
