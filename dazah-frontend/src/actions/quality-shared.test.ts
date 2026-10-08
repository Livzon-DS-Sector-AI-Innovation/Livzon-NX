import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'quality-token' }),
  }),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies,
  headers: vi.fn(async () => new Headers({ 'X-Dazah-Page-Path': '/quality/capas' })),
}))

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
        headers: expect.objectContaining({ Authorization: 'Bearer quality-token',
          'X-Dazah-Page-Path': '/quality/capas',
        }),
      }),
    )
  })

  it('classifies public authorization failures and hides server failure bodies', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '未获得当前高风险业务动作授权' }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'private database parameters' }), { status: 500 })))
    await expect(actionFetch('/api/v1/quality/changes/import/confirm')).rejects.toMatchObject({
      status: 403, message: '未获得当前高风险业务动作授权',
    })
    await expect(actionFetch('/api/v1/quality/changes/import/confirm')).rejects.toMatchObject({
      status: 500, message: '服务暂时不可用，请稍后重试',
    })
  })
})
