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
  createSeedCulture,
  deleteSeedCulture,
  getPersonMonthly,
  getSeedCultures,
  updateSeedCulture,
} from './seed-culture'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const REVALIDATE = '/production/batches/workshop/101-1'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('seed-culture actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('lists seed cultures with query params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: [] }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      getSeedCultures({ page: 2, page_size: 20, batch_no: 'SC-1' }),
    ).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/seed-cultures?page=2&page_size=20&batch_no=SC-1`,
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
      }),
    )
  })

  it('creates a seed culture and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'sc-new' } }),)
    vi.stubGlobal('fetch', fetchMock)

    const payload = { batch_no: 'SC-002', product_name: 'FA' }
    await expect(createSeedCulture(payload)).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/seed-cultures`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('updates a seed culture and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: { id: 'sc-1' } }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateSeedCulture('sc-1', { product_name: 'LV' })).resolves.toMatchObject({
      code: 200,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/seed-cultures/sc-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })

  it('deletes a seed culture and revalidates', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, message: 'success', data: null }),)
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteSeedCulture('sc-1')).resolves.toMatchObject({ code: 200 })
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/production/seed-cultures/sc-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith(REVALIDATE)
  })
})
describe('person monthly stats action', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches person monthly stats with month and product params', async () => {
    const fetchMock = vi.fn(() =>
      jsonResponse({
        code: 200,
        message: 'success',
        data: [
          {
            key: 'ou_z',
            name: '张三',
            open_id: 'ou_z',
            avatar_url: 'https://avatar/z.png',
            total_batches: 2,
            role_counts: { 配制: 2, 接种: 1 },
            details: [{ date: '2026-11-03', batch_no: 'SC-1', role: '配制' }],
          },
        ],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const rows = await getPersonMonthly({ month: '2026-11', product_name: '盐酸林可霉素' })
    expect(rows.code).toBe(200)
    expect(rows.data?.[0]).toMatchObject({ name: '张三', total_batches: 2 })
    const url = fetchMock.mock.calls[0]?.[0] as string
    expect(url).toContain('/api/v1/production/seed-cultures/person-monthly')
    expect(url).toContain('month=2026-11')
    expect(url).toContain('product_name=')
  })
})
