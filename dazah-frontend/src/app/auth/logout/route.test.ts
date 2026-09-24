import { NextRequest } from 'next/server'
import { afterEach, expect, it, vi } from 'vitest'

import { GET } from './route'

vi.mock('@/lib/server-api', () => ({
  getBackendFallbackUrls: () => ['http://backend.test'],
}))

afterEach(() => vi.unstubAllGlobals())

it('revokes the server session before clearing the cookie', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const request = new NextRequest('http://factory.test/auth/logout', {
    headers: { cookie: 'auth_token=test-token' },
  })

  const response = await GET(request)

  expect(fetchMock).toHaveBeenCalledWith(
    'http://backend.test/api/v1/identity/auth/session/logout',
    expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer test-token' } }),
  )
  expect(response.status).toBe(307)
  expect(response.headers.get('set-cookie')).toContain('auth_token=')
  expect(response.headers.get('set-cookie')).toContain('Max-Age=0')
})

it('keeps the cookie when revocation fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))
  const request = new NextRequest('http://factory.test/auth/logout', {
    headers: { cookie: 'auth_token=test-token' },
  })

  const response = await GET(request)

  expect(response.status).toBe(503)
  expect(response.headers.get('set-cookie')).toBeNull()
})
