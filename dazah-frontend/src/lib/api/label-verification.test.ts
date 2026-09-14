import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchLabelVerificationStatistics,
  fetchLabelVerifications,
} from './label-verification'

function okResponse(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('label verification API routes', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the list from the production module endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchLabelVerifications({ batch_number: 'B-1', page: 2, page_size: 10 })

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/production/label-verifications?'),
      expect.objectContaining({ cache: 'no-store' }),
    )
  })

  it('reads statistics from the production module endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ code: 200, data: {} }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchLabelVerificationStatistics()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/production/label-verifications/statistics',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
