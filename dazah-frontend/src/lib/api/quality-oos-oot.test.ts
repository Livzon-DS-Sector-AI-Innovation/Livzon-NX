import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchOosOotRecords } from './quality-oos-oot'

describe('quality OOS/OOT API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends typed OOS/OOT filters and pagination to the migrated route', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: [], meta: { total: 0 } }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchOosOotRecords({ recordType: 'OOS', status: 'open', page: 2, pageSize: 10 })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/oos-oot/records?record_type=OOS&status=open&page=2&page_size=10',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
