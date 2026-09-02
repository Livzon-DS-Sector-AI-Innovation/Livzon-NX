import { afterEach, describe, expect, it, vi } from 'vitest'

import {
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
