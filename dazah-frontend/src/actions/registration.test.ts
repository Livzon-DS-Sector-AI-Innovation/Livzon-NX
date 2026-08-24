import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  deleteAuthorizationLetter,
  fetchAuthorizationLettersServer,
  fetchProductsServer,
  fetchReferenceStandardsServer,
  generateReferenceStandard,
} from './registration'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('registration actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('fetches authorization letters server-side', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [], total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchAuthorizationLettersServer({ page: 1, page_size: 20 })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/registration/authorization-letters'),
      expect.anything(),
    )
  })

  it('fetches products server-side', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await fetchProductsServer()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/registration/authorization-letters/products'),
      expect.anything(),
    )
    expect(res).toEqual([])
  })

  it('fetches reference standards server-side with params', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { items: [], total: 0 } }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchReferenceStandardsServer({ page: 2, page_size: 10 })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('page=2'),
      expect.anything(),
    )
  })

  it('deletes an authorization letter', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteAuthorizationLetter('al-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/registration/authorization-letters/al-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('generates a reference standard document', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'rs-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await generateReferenceStandard(new FormData(), { drug_name: '霉酚酸' } as never)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/registration/reference-standards/generate'),
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
