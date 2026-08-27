import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchSuppliers } from './quality-external'

describe('external quality API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the supplier list request on the authenticated quality proxy', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: [], meta: { total: 0 } }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchSuppliers()).resolves.toMatchObject({ data: [] })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/suppliers?page=1&page_size=50',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
