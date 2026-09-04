/* @vitest-environment happy-dom */

import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'server-api-token' }),
  }),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))

import { serverFetchRoles } from './server/admin'
import { ServerApiError, serverApiGet, serverApiPost } from './server/registration'

describe('migrated server API clients', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('forwards the server auth token while reading system roles', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: [] }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(serverFetchRoles()).resolves.toEqual([])

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v1/identity/admin/roles')
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        headers: { Authorization: 'Bearer server-api-token' },
        cache: 'no-store',
      }),
    )
  })

  it('registration serverApiGet resolves the envelope data on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ data: [{ code: 'C-1' }] }), { status: 200 }),
      ),
    )
    await expect(serverApiGet('/api/v1/registration/overview')).resolves.toEqual({
      data: [{ code: 'C-1' }],
    })
  })

  it('registration serverApiGet surfaces the HTTP status via ServerApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('飞书未授权', { status: 403, statusText: 'Forbidden' }),
      ),
    )
    const error = await serverApiGet('/api/v1/registration/overview').catch((e) => e)
    expect(error).toBeInstanceOf(ServerApiError)
    expect(error).toBeInstanceOf(Error)
    expect((error as ServerApiError).status).toBe(403)
    expect((error as ServerApiError).name).toBe('ServerApiError')
    expect((error as ServerApiError).message).toBe('飞书未授权')
  })

  it('registration serverApiGet falls back to status text when body is empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('', { status: 500, statusText: 'Internal Server Error' })),
    )
    const error = await serverApiGet('/api/v1/registration/overview').catch((e) => e)
    expect((error as ServerApiError).status).toBe(500)
    expect((error as ServerApiError).message).toContain('500')
  })

  it('registration serverApiPost rejects with a plain error on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('保存失败', { status: 400 })),
    )
    await expect(serverApiPost('/api/v1/registration/items', { name: 'x' })).rejects.toThrow(
      '保存失败',
    )
  })
})
