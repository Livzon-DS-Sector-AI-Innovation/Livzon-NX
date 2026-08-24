import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'quality-token' }),
  }),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))

import { actionFetch } from './quality-shared'

describe('quality action request boundary', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('adds the server auth header and unwraps the API envelope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: { accepted: true } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(actionFetch('http://backend.test/api/v1/quality/capas')).resolves.toEqual({
      accepted: true,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/quality/capas',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer quality-token' }),
      }),
    )
  })
})
