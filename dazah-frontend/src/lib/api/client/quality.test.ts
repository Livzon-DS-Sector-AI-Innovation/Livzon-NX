import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchAnomalyAnalysisStatus,
  fetchAnomalyDashboard,
  fetchAnomalyReportFields,
  fetchAnomalyReportRecords,
  fetchAnomalyReportShareLinks,
  fetchAnomalyReportYears,
  fetchQcValidationFields,
  fetchQcValidationRecords,
  fetchQcValidationShareLinks,
  fetchQcValidationYears,
} from './quality'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('quality client - qc validation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches qc validation years from data envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: { years: [{ year: 2026, status: 'in_progress' }] },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchQcValidationYears()).resolves.toEqual([
      { year: 2026, status: 'in_progress' },
    ])
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/quality/validation-qc/years')
  })

  it('returns empty years when data missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ code: 200 })))
    await expect(fetchQcValidationYears()).resolves.toEqual([])
  })

  it('fetches qc validation fields with year query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { fields: [{ field_name: '检验项目' }] } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchQcValidationFields(2026)).resolves.toEqual({
      fields: [{ field_name: '检验项目' }],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/validation-qc/fields?year=2026',
    )
  })

  it('fetches qc validation records with keyword and pagination params', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { items: [], total: 0 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchQcValidationRecords(2026, { keyword: '含量', page: 2, page_size: 10 }),
    ).resolves.toEqual({ items: [], total: 0 })
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/api/v1/quality/validation-qc/records?')
    expect(url).toContain('year=2026')
    expect(url).toContain('keyword=%E5%90%AB%E9%87%8F')
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=10')
  })

  it('builds share links via POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: { record_share_links: { 'rec-1': 'https://feishu.example/r1' } },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchQcValidationShareLinks(2026, ['rec-1']),
    ).resolves.toEqual({ 'rec-1': 'https://feishu.example/r1' })
    const [, init] = fetchMock.mock.calls[0]
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({
      fields: { record_ids: ['rec-1'] },
    })
  })

  it('throws parseError on failure responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: '服务不可用' }, 500)))
    await expect(fetchQcValidationRecords(2026)).rejects.toThrow('服务不可用')
  })
})

describe('quality client - finished product anomaly', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches anomaly report years from data envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: { years: [{ year: 2026, status: 'in_progress' }] },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAnomalyReportYears()).resolves.toEqual([
      { year: 2026, status: 'in_progress' },
    ])
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/finished-product-anomaly/years'
    )
  })

  it('fetches anomaly dashboard with and without year query', async () => {
    const dashboard = { year: 2026, totals: { records: 3 } }
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(jsonResponse({ code: 200, data: dashboard })))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAnomalyDashboard(2026)).resolves.toEqual(dashboard)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/finished-product-anomaly/dashboard?year=2026'
    )

    await expect(fetchAnomalyDashboard()).resolves.toEqual(dashboard)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/quality/finished-product-anomaly/dashboard'
    )
  })

  it('encodes anomaly analysis job id in status query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { job_id: 'job 1', status: 'running' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAnomalyAnalysisStatus('job 1')).resolves.toEqual({
      job_id: 'job 1',
      status: 'running',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/finished-product-anomaly/analysis/status?job_id=job%201'
    )
  })

  it('fetches anomaly report fields with year query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { fields: [{ field_name: '异常描述' }] } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAnomalyReportFields(2026)).resolves.toEqual({
      fields: [{ field_name: '异常描述' }],
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/finished-product-anomaly/fields?year=2026'
    )
  })

  it('fetches anomaly report records with keyword and pagination params', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, data: { items: [], total: 0 } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchAnomalyReportRecords(2026, { keyword: '色度', page: 2, page_size: 20 })
    ).resolves.toEqual({ items: [], total: 0 })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/finished-product-anomaly/records?year=2026&keyword=%E8%89%B2%E5%BA%A6&page=2&page_size=20'
    )
  })

  it('posts record ids and returns share link map', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        data: { record_share_links: { 'rec-1': 'https://feishu/rec-1' } },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      fetchAnomalyReportShareLinks(2026, ['rec-1'])
    ).resolves.toEqual({ 'rec-1': 'https://feishu/rec-1' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(
      '/api/v1/quality/finished-product-anomaly/records/share-links?year=2026'
    )
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ fields: { record_ids: ['rec-1'] } })
  })

  it('returns empty share link map when data missing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ code: 200 }))
    )
    await expect(fetchAnomalyReportShareLinks(2026, [])).resolves.toEqual({})
  })
})
