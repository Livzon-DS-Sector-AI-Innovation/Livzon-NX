import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test-token' }),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))

import { fetchDocumentDepartmentsServer } from './quality'

describe('document department server fetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('sends the documents page key and server authentication', async () => {
    const departments = [{ id: 'dept-1', name: '质量部' }]
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 200, message: 'ok', data: departments }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchDocumentDepartmentsServer()).resolves.toEqual(departments)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/quality/document-departments')
    expect(init.cache).toBe('no-store')
    expect(init.headers).toMatchObject({
      Authorization: 'Bearer test-token',
      'X-Dazah-Page-Key': 'quality:documents',
    })
  })

  it('propagates permission failures instead of showing an empty list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 403 })))

    await expect(fetchDocumentDepartmentsServer()).rejects.toThrow('Server API error: 403')
  })
})
