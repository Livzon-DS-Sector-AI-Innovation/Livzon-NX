/* @vitest-environment happy-dom */

import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'server-api-token' }),
  }),
  headers: vi.fn().mockResolvedValue(new Headers()),
}))

vi.mock('next/headers', () => ({
  cookies: mocks.cookies,
  headers: mocks.headers,
}))

import { serverFetchRoles } from './server/admin'
import { serverApiGet } from './server/registration'
import { fetchFeishuValidationDashboardStatsServer } from './server/quality'
import { fetchWarehouseMaterialPage } from './server/warehouse'

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

  it('wraps non-2xx registration responses in ServerApiError with status', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('record not found', { status: 404 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(serverApiGet('/api/v1/registration/whatever')).rejects.toMatchObject({
      name: 'ServerApiError',
      status: 404,
      message: 'record not found',
    })
  })

  it('passes days and year_from to validation dashboard stats query', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ total: 0 }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchFeishuValidationDashboardStatsServer(7, 2025)

    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/api/v1/quality/feishu/statistics/validations')
    expect(url).toContain('days=7')
    expect(url).toContain('year_from=2025')
  })

  it('forwards incremental flag when refreshing warehouse material page', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await fetchWarehouseMaterialPage('records', { incremental: true })

    expect(String(fetchMock.mock.calls[0][0])).toContain('incremental=1')
  })
})
