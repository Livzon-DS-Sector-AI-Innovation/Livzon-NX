import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'server-token' }),
  }),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))

import { ServerApiError, serverApiGet, serverApiPost } from './registration'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('registration server api client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('posts to the backend with the server auth cookie and unwraps data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'ok', data: { sent: true } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      serverApiPost<{ sent: boolean }>('/certificates/reminder/test', {
        recipient_ids: ['ou-1'],
      }),
    ).resolves.toEqual({ sent: true })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/certificates/reminder/test')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>).Authorization).toBe(
      'Bearer server-token',
    )
    expect(init.body).toBe(JSON.stringify({ recipient_ids: ['ou-1'] }))
  })

  it('gets the raw envelope from the backend', async () => {
    const envelope = {
      code: 200,
      message: 'ok',
      data: { items: [] },
      meta: { total: 0 },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(envelope)))

    await expect(serverApiGet('/certificates/ledger?page=1')).resolves.toEqual(
      envelope,
    )
  })

  it('throws ServerApiError on get failures and plain Error on post failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('证书提醒配置缺失', { status: 400 })),
    )
    await expect(serverApiPost('/certificates/reminder/test', {})).rejects.toThrow(
      '证书提醒配置缺失',
    )
    await expect(serverApiGet('/certificates/reminder/test')).rejects.toThrow(
      ServerApiError,
    )
  })
})