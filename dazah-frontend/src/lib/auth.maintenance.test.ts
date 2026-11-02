import { expect, it, vi } from 'vitest'
vi.mock('next/headers', () => ({
  cookies: vi.fn().mockResolvedValue({ get: () => ({ value: 'fixture-session' }) }),
  headers: vi.fn().mockResolvedValue(new Headers({ 'X-Dazah-Operation-ID': '12345678-1234-1234-1234-123456789abc', 'X-Dazah-Page-Path': '/quality/deviations' })),
}))
import { getAuthHeaders } from './auth'
import { headers } from 'next/headers'
it('forwards the stable operation ID alongside existing authentication and page context', async () => {
  expect(await getAuthHeaders()).toMatchObject({
    'X-Dazah-Operation-ID': '12345678-1234-1234-1234-123456789abc',
    'X-Dazah-Page-Path': '/quality/deviations', Authorization: 'Bearer fixture-session',
  })
})

it.each(['198.51.100.23, 172.19.0.2', '2001:db8::23', null])('preserves the client IP chain for server-side API calls (%s)', async (ip) => {
  vi.mocked(headers).mockResolvedValueOnce(new Headers(ip ? { 'x-forwarded-for': ip } : {}))
  const authHeaders = await getAuthHeaders()
  expect(authHeaders['X-Forwarded-For']).toBe(ip ?? undefined)
  expect(authHeaders.Authorization).toBe('Bearer fixture-session')
})
