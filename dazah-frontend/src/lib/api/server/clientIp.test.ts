import { afterEach, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  cookies: async () => ({ get: () => ({ value: 'fixture-session' }) }),
  headers: async () => new Headers({ 'x-forwarded-for': '198.51.100.23' }),
}))

import { serverFetchRoles } from './admin'
import { fetchRegulatoryTrackerSummaryServer } from './regulatoryTracker'

afterEach(() => vi.unstubAllGlobals())

it.each([serverFetchRoles, fetchRegulatoryTrackerSummaryServer])('forwards the user IP for server-side reads (%s)', async (read) => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [] })))
  vi.stubGlobal('fetch', fetcher)
  await read()
  expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
    headers: expect.objectContaining({ 'X-Forwarded-For': '198.51.100.23', Authorization: 'Bearer fixture-session' }),
  }))
})
