/* @vitest-environment happy-dom */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchMaterialCatalog, fetchMaterialOptions } from './purchasing'

describe('purchasing API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches material options and the material catalog through the client fetch helper', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: 200, message: 'success', data: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: 200, message: 'success', data: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchMaterialOptions({ keyword: '钢', limit: 20 })).resolves.toMatchObject({
      code: 200,
    })
    await expect(fetchMaterialCatalog({ page: 1, page_size: 20 })).resolves.toMatchObject({
      code: 200,
    })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/procurement/material-options?keyword=%E9%92%A2&limit=20',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/procurement/material-catalog?page=1&page_size=20',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
