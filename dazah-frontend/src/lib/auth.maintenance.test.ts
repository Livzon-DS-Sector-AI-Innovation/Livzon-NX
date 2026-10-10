import { expect, it, vi } from 'vitest'
vi.mock('next/headers', () => ({
  cookies: vi.fn().mockResolvedValue({ get: () => ({ value: 'fixture-session' }) }),
  headers: vi.fn().mockResolvedValue(new Headers({ 'X-Dazah-Operation-ID': '12345678-1234-1234-1234-123456789abc', 'X-Dazah-Page-Path': '/quality/deviations' })),
}))
import { getAuthHeaders } from './auth'
it('forwards the stable operation ID alongside existing authentication and page context', async () => {
  expect(await getAuthHeaders()).toMatchObject({
    'X-Dazah-Operation-ID': '12345678-1234-1234-1234-123456789abc',
    'X-Dazah-Page-Path': '/quality/deviations', Authorization: 'Bearer fixture-session',
  })
})
