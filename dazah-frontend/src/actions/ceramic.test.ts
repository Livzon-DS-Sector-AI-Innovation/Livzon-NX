import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({
    'Content-Type': 'application/json',
    Authorization: 'Bearer test-token',
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  ceramicFeed,
  ceramicOps,
  ceramicClean,
  ceramicSep,
  ceramicEquip,
} from './ceramic'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const REVALIDATE = '/production/batches/workshop/203'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ceramic actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists ceramic feeds with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(ceramicFeed.list({ page: 1, page_size: 10 })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/ceramic-feeds?page=1&page_size=10`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a ceramic feed and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'cf-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { feed_type: '陶瓷粉', amount: 5 }
    await expect(ceramicFeed.create(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/ceramic-feeds`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates a ceramic feed and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'cf-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(ceramicFeed.update('cf-1', { amount: 6 })).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/ceramic-feeds/cf-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('deletes a ceramic feed and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: null }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(ceramicFeed.delete('cf-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/ceramic-feeds/cf-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('all ceramic sub-models share the same CRUD endpoints', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(ceramicOps.list({})).resolves.toMatchObject({ code: 200 })
    await expect(ceramicClean.list({})).resolves.toMatchObject({ code: 200 })
    await expect(ceramicSep.list({})).resolves.toMatchObject({ code: 200 })
    await expect(ceramicEquip.list({})).resolves.toMatchObject({ code: 200 })

    // All four should target the same /api/v1/production/ceramic-* prefix
    const urls = fetchMock.mock.calls.map((c) => String((c as unknown[])[0]))
    expect(urls[0]).toContain('ceramic-membrane-ops')
    expect(urls[1]).toContain('ceramic-membrane-cleans')
    expect(urls[2]).toContain('ceramic-material-separations')
    expect(urls[3]).toContain('ceramic-equipment-logs')
  })
})