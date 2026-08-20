import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchDocuments, fetchSummary, fetchSyncJobs } from './regulatory-tracker-client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('regulatory tracker client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches the summary', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { total: 3 } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchSummary()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/regulatory-tracker/summary')
    expect(result).toMatchObject({ total: 3 })
  })

  it('fetches documents with search params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchDocuments({ page: 1, pageSize: 20, keyword: 'GMP' })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/regulatory-documents?'),
    )
  })

  it('fetches sync jobs with pagination', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [] } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchSyncJobs(2, 50)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/sync-jobs?page=2&pageSize=50')
  })
})
